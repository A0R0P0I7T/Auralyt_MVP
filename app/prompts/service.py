"""Stage F: Prompt Intelligence Service for Engine 2.
Coordinates profile consumption, planning, generation, validation, scoring, persistence, and versioning.
"""
import time
import logging
from typing import List, Optional, Tuple, Dict, Any
from sqlalchemy import select, func, desc, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import async_session_factory
from app.db.models import Brand, PromptRun, PromptCandidate, utc_now
from app.services.profiler_service import ProfilerService
from app.prompts.normalizer import ProfileNormalizer
from app.prompts.classifier import CategoryClassifier, CLASSIFICATION_VERSION
from app.prompts.templates import TEMPLATE_SYSTEM_VERSION
from app.prompts.planner import CoveragePlanner
from app.prompts.generator import get_prompt_generator
from app.prompts.validator import PromptValidator
from app.prompts.scorer import PromptScorer, normalize_prompt_text
from app.prompts.models import GeneratedPromptCandidate

logger = logging.getLogger(__name__)


def select_balanced_candidates(
    candidates: List[GeneratedPromptCandidate], target_count: int
) -> List[GeneratedPromptCandidate]:
    """
    Selects a balanced, diverse set of prompt candidates across categories
    rather than truncating sequentially and starving later categories (DEF-E2-DIV).
    """
    if len(candidates) <= target_count:
        return candidates

    by_category: Dict[str, List[GeneratedPromptCandidate]] = {}
    for c in candidates:
        by_category.setdefault(c.category, []).append(c)

    # Sort candidates within each category by quality_score descending
    for cat in by_category:
        by_category[cat].sort(key=lambda x: getattr(x, "quality_score", 0.0), reverse=True)

    selected: List[GeneratedPromptCandidate] = []
    categories = list(by_category.keys())
    cat_idx = 0
    while len(selected) < target_count and any(by_category.values()):
        cat = categories[cat_idx % len(categories)]
        if by_category[cat]:
            selected.append(by_category[cat].pop(0))
        cat_idx += 1

    return selected


class PromptIntelligenceService:
    """Orchestrates Engine 2 Prompt Intelligence operations."""

    @staticmethod
    async def generate_prompts(
        brand_id: str,
        prompt_count: int = 20,
        categories: Optional[List[str]] = None,
        language: Optional[str] = None,
        force_regenerate: bool = False,
        db: Optional[AsyncSession] = None
    ) -> Tuple[PromptRun, List[PromptCandidate]]:
        """
        Generates grounded, structured prompts for a profiled brand.
        Consumes Engine 1's profile summary and enforces caching/idempotency.
        """
        close_session = False
        if db is None:
            db = async_session_factory()
            close_session = True

        try:
            # 1. Verify Brand exists
            brand = await db.get(Brand, brand_id)
            if not brand:
                raise ValueError("Brand not found.")

            # 2. Consume Engine 1's profile summary
            profile_summary = await ProfilerService.get_brand_profile_summary(brand_id, db)
            if not profile_summary:
                raise ValueError("Profile summary not available for brand.")

            # 3. Stage A: Profile Normalization
            normalized_profile = ProfileNormalizer.normalize(profile_summary)
            if language:
                normalized_profile.primary_language = language

            if normalized_profile.is_empty:
                raise ValueError(
                    "Cannot generate prompts for an empty brand profile. "
                    "Please complete website profiling first."
                )
            if not normalized_profile.get_primary_category():
                raise ValueError(
                    "Cannot generate organic prompts: brand profile has insufficient evidence "
                    "(missing industry, category, products, or use cases). "
                    "Please complete website profiling first."
                )

            # 3.5 Stage A.2: Category Classification
            classification = CategoryClassifier.classify(normalized_profile)

            # The mutable brand counter may point at a pending/failed refresh.
            # Generate only from the completed snapshot returned by Engine 1.
            current_version = normalized_profile.profile_version

            CURRENT_STRATEGY_VERSION = "v3_category_grounded"

            # 4. Check for cached generation if not force_regenerate
            if not force_regenerate:
                existing_run_stmt = select(PromptRun).where(
                    PromptRun.brand_id == brand_id,
                    PromptRun.profile_version == current_version,
                    PromptRun.status == "completed"
                ).order_by(desc(PromptRun.created_at))
                res = await db.execute(existing_run_stmt)
                latest_run = res.scalars().first()

                if latest_run:
                    meta = latest_run.config_metadata or {}
                    strat_ver = meta.get("strategy_version")
                    class_ver = meta.get("classification_version")
                    templ_ver = meta.get("template_version")
                    req_count = meta.get("requested_count")

                    if (
                        strat_ver == CURRENT_STRATEGY_VERSION
                        and class_ver == CLASSIFICATION_VERSION
                        and templ_ver == TEMPLATE_SYSTEM_VERSION
                        and req_count == prompt_count
                    ):
                        prompts_stmt = select(PromptCandidate).where(
                            PromptCandidate.prompt_run_id == latest_run.id,
                            PromptCandidate.is_approved.is_(True),
                            PromptCandidate.is_archived.is_(False)
                        ).order_by(desc(PromptCandidate.quality_score))
                        p_res = await db.execute(prompts_stmt)
                        existing_prompts = list(p_res.scalars().all())

                        if len(existing_prompts) >= prompt_count:
                            logger.info(f"Reusing valid cached prompt run {latest_run.id} for brand {brand_id} v{current_version}")
                            return latest_run, existing_prompts[:prompt_count]

            # 5. Archive prior active prompts for this brand and current profile version to guarantee clean versioning and prevent stale prompt contamination
            await db.execute(
                update(PromptCandidate)
                .where(
                    PromptCandidate.brand_id == brand_id,
                    PromptCandidate.profile_version == current_version,
                    PromptCandidate.is_archived.is_(False)
                )
                .values(is_archived=True)
            )

            # Determine whether this is a fresh generation or explicit regeneration
            prior_runs_stmt = select(func.count(PromptRun.id)).where(PromptRun.brand_id == brand_id)
            prior_runs_res = await db.execute(prior_runs_stmt)
            prior_runs_count = prior_runs_res.scalar() or 0
            generation_mode = "regenerated" if prior_runs_count > 0 else "generated"

            # Create new PromptRun
            run = PromptRun(
                brand_id=brand_id,
                profile_version=current_version,
                status="running",
                prompt_count_requested=prompt_count,
                prompts_generated=0,
                provider="deterministic",
                config_metadata={
                    "requested_count": prompt_count,
                    "categories": categories,
                    "language": normalized_profile.primary_language,
                    "force_regenerate": force_regenerate,
                    "generation_mode": generation_mode,
                    "strategy_version": CURRENT_STRATEGY_VERSION,
                    "classification_version": CLASSIFICATION_VERSION,
                    "template_version": TEMPLATE_SYSTEM_VERSION,
                    "primary_industry": classification.primary_industry,
                    "primary_category": classification.primary_category,
                    "business_model": classification.business_model,
                    "classification_confidence": classification.confidence,
                    "archetype": classification.domain_archetype,
                }
            )
            db.add(run)
            await db.commit()
            await db.refresh(run)

            start_time = time.time()

            try:
                # 6. Stage B: Intent & Coverage Planning with surplus
                plan = CoveragePlanner.create_plan(
                    profile=normalized_profile,
                    requested_count=prompt_count,
                    allowed_categories=categories,
                    surplus_ratio=1.75
                )

                # 7. Stage C: Candidate Generation
                generator = get_prompt_generator()
                from app.prompts.generator import GeminiGenerator
                if isinstance(generator, GeminiGenerator) and settings.LLM_API_KEY:
                    run.provider = "gemini"
                    run.model_name = settings.LLM_MODEL
                else:
                    run.provider = "deterministic"
                    run.model_name = "template_engine"

                raw_candidates = await generator.generate(normalized_profile, plan)
                total_generated = len(raw_candidates)

                # 8. Stage D: Quality Validation
                validated_candidates: List[GeneratedPromptCandidate] = []
                rejection_log: List[Dict[str, str]] = []
                for cand in raw_candidates:
                    is_valid, reason = PromptValidator.validate(cand, normalized_profile, reject_brand_mentions=True)
                    if is_valid:
                        cand.is_approved = True
                        validated_candidates.append(cand)
                    else:
                        cand.is_approved = False
                        cand.rejection_reason = reason
                        rejection_log.append({"prompt": cand.text, "reason": reason})
                        logger.debug(f"Candidate rejected by validator: '{cand.text}' -> {reason}")

                # 9. Stage E: Deduplication & Replenishment
                unique_candidates = PromptScorer.deduplicate(validated_candidates)

                # Bounded Replenishment loop if candidates < prompt_count
                replenishment_passes = 0
                while len(unique_candidates) < prompt_count and replenishment_passes < 3:
                    replenishment_passes += 1
                    needed = prompt_count - len(unique_candidates)
                    replenish_plan = CoveragePlanner.create_replenishment_plan(
                        profile=normalized_profile,
                        needed_count=needed,
                        allowed_categories=categories
                    )
                    replenish_cands = await generator.generate(normalized_profile, replenish_plan)
                    total_generated += len(replenish_cands)

                    for cand in replenish_cands:
                        is_valid, reason = PromptValidator.validate(cand, normalized_profile, reject_brand_mentions=True)
                        if is_valid:
                            cand.is_approved = True
                            validated_candidates.append(cand)
                        else:
                            cand.is_approved = False
                            cand.rejection_reason = reason
                            rejection_log.append({"prompt": cand.text, "reason": reason})

                    unique_candidates = PromptScorer.deduplicate(validated_candidates)

                scored_candidates: List[GeneratedPromptCandidate] = []
                accepted_so_far: List[GeneratedPromptCandidate] = []
                for cand in unique_candidates:
                    scored = PromptScorer.score_candidate(cand, normalized_profile, accepted_so_far)
                    scored_candidates.append(scored)
                    accepted_so_far.append(scored)

                # Select balanced candidates across diverse categories
                final_candidates = select_balanced_candidates(scored_candidates, prompt_count)

                # 10. Stage F: Persistence
                # Deduplicate strictly within this run's final candidates without dropping previous run texts
                persisted_models: List[PromptCandidate] = []
                seen_this_run = set()
                for fc in final_candidates:
                    normalized_text = normalize_prompt_text(fc.text)
                    if normalized_text in seen_this_run:
                        continue
                    seen_this_run.add(normalized_text)
                    model = PromptCandidate(
                        brand_id=brand_id,
                        prompt_run_id=run.id,
                        profile_version=current_version,
                        text=fc.text,
                        normalized_text=normalized_text,
                        category=fc.category,
                        intent=fc.intent,
                        buying_stage=fc.buying_stage,
                        target_audience=fc.target_audience,
                        target_product_service=fc.target_product_service,
                        language=fc.language,
                        provenance_fact_ids=fc.provenance_fact_ids,
                        grounding_evidence=fc.grounding_evidence,
                        scores={
                            **(fc.scores or {}),
                            "validation_decision": "approved" if fc.is_approved else "rejected",
                            "rejection_reason": fc.rejection_reason,
                            "template_version": fc.template_version or TEMPLATE_SYSTEM_VERSION,
                            "classification_version": CLASSIFICATION_VERSION,
                            "subcategory": fc.subcategory,
                        },
                        quality_score=fc.quality_score,
                        is_approved=fc.is_approved,
                        lifecycle_status="approved" if fc.is_approved else "rejected",
                        review_notes=fc.rejection_reason,
                        is_archived=False,
                        user_edited=False,
                        edit_history=[]
                    )
                    db.add(model)
                    persisted_models.append(model)

                # Update Run Status with full lifecycle diagnostics
                duration = time.time() - start_time
                run.status = "completed"
                run.prompts_generated = len(persisted_models)
                run.duration_seconds = round(duration, 2)
                run.completed_at = utc_now()
                meta = dict(run.config_metadata or {})
                meta["diagnostics"] = {
                    "requested_count": prompt_count,
                    "generated_count": total_generated,
                    "accepted_count": len(final_candidates),
                    "persisted_count": len(persisted_models),
                    "replenishment_passes": replenishment_passes,
                    "rejections_count": len(rejection_log),
                    "rejections": rejection_log[:10],
                    "shortfall": max(0, prompt_count - len(persisted_models)),
                }
                run.config_metadata = meta

                await db.commit()
                for pm in persisted_models:
                    await db.refresh(pm)
                await db.refresh(run)

                return run, persisted_models

            except Exception as gen_err:
                logger.exception(f"Error during prompt generation for run {run.id}: {gen_err}")
                run.status = "failed"
                run.error_summary = str(gen_err)
                run.completed_at = utc_now()
                await db.commit()
                raise gen_err

        finally:
            if close_session:
                await db.close()

    @staticmethod
    async def list_prompts(
        brand_id: str,
        category: Optional[str] = None,
        intent: Optional[str] = None,
        is_approved: Optional[bool] = None,
        lifecycle_status: Optional[str] = None,
        is_archived: bool = False,
        search: Optional[str] = None,
        profile_version: Optional[int] = None,
        page: int = 1,
        page_size: int = 20,
        db: Optional[AsyncSession] = None
    ) -> Dict[str, Any]:
        """Lists and filters prompts for a brand with pagination and coverage distribution."""
        close_session = False
        if db is None:
            db = async_session_factory()
            close_session = True

        try:
            brand = await db.get(Brand, brand_id)
            if not brand:
                raise ValueError("Brand not found.")

            if profile_version is not None:
                target_version = profile_version
            else:
                current_profile = await ProfilerService.get_brand_profile_summary(brand_id, db)
                target_version = (current_profile or {}).get("profile_version", brand.profile_version)

            base_query = select(PromptCandidate).where(
                PromptCandidate.brand_id == brand_id,
                PromptCandidate.profile_version == target_version,
                PromptCandidate.is_archived.is_(is_archived)
            )

            if category:
                base_query = base_query.where(PromptCandidate.category == category)
            if intent:
                base_query = base_query.where(PromptCandidate.intent == intent)
            if is_approved is not None:
                base_query = base_query.where(PromptCandidate.is_approved.is_(is_approved))
            if lifecycle_status:
                base_query = base_query.where(PromptCandidate.lifecycle_status == lifecycle_status)
            if search:
                base_query = base_query.where(PromptCandidate.text.ilike(f"%{search.strip()}%"))

            # Count total
            count_query = select(func.count()).select_from(base_query.subquery())
            total_res = await db.execute(count_query)
            total = total_res.scalar_one()

            # Pagination
            offset = (page - 1) * page_size
            items_query = base_query.order_by(desc(PromptCandidate.quality_score), desc(PromptCandidate.created_at)).offset(offset).limit(page_size)
            items_res = await db.execute(items_query)
            items = list(items_res.scalars().all())

            total_pages = (total + page_size - 1) // page_size if total > 0 else 1

            # Compute coverage distribution for this version
            coverage_query = select(PromptCandidate.category, func.count()).where(
                PromptCandidate.brand_id == brand_id,
                PromptCandidate.profile_version == target_version,
                PromptCandidate.is_archived.is_(False)
            ).group_by(PromptCandidate.category)
            cov_res = await db.execute(coverage_query)
            category_counts = {row[0]: row[1] for row in cov_res.all()}

            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
                "total_pages": total_pages,
                "profile_version": target_version,
                "coverage_summary": category_counts
            }
        finally:
            if close_session:
                await db.close()

    @staticmethod
    async def get_prompt(prompt_id: str, db: Optional[AsyncSession] = None) -> Optional[PromptCandidate]:
        close_session = False
        if db is None:
            db = async_session_factory()
            close_session = True

        try:
            return await db.get(PromptCandidate, prompt_id)
        finally:
            if close_session:
                await db.close()

    @staticmethod
    async def update_prompt(
        prompt_id: str,
        text: Optional[str] = None,
        is_approved: Optional[bool] = None,
        is_archived: Optional[bool] = None,
        db: Optional[AsyncSession] = None
    ) -> Optional[PromptCandidate]:
        """Edits prompt text or updates approval/archival status with audit trail."""
        close_session = False
        if db is None:
            db = async_session_factory()
            close_session = True

        try:
            prompt = await db.get(PromptCandidate, prompt_id)
            if not prompt:
                return None

            if text is not None and text.strip() != prompt.text:
                history = list(prompt.edit_history or [])
                history.append({
                    "previous_text": prompt.text,
                    "updated_at": utc_now().isoformat()
                })
                prompt.edit_history = history
                prompt.text = text.strip()
                prompt.normalized_text = normalize_prompt_text(text.strip())
                prompt.user_edited = True

            if is_approved is not None:
                prompt.is_approved = is_approved

            if is_archived is not None:
                prompt.is_archived = is_archived

            prompt.updated_at = utc_now()
            await db.commit()
            await db.refresh(prompt)
            return prompt
        finally:
            if close_session:
                await db.close()

    @staticmethod
    async def get_coverage_summary(brand_id: str, db: Optional[AsyncSession] = None) -> Dict[str, Any]:
        """Aggregates prompt coverage and quality metrics for a brand."""
        close_session = False
        if db is None:
            db = async_session_factory()
            close_session = True

        try:
            brand = await db.get(Brand, brand_id)
            if not brand:
                raise ValueError("Brand not found.")

            profile = await ProfilerService.get_brand_profile_summary(brand_id, db)
            version = (profile or {}).get("profile_version", brand.profile_version)

            prompts_query = select(PromptCandidate).where(
                PromptCandidate.brand_id == brand_id,
                PromptCandidate.profile_version == version
            )
            res = await db.execute(prompts_query)
            all_prompts = list(res.scalars().all())

            total = len(all_prompts)
            approved = sum(1 for p in all_prompts if p.is_approved and not p.is_archived)
            archived = sum(1 for p in all_prompts if p.is_archived)

            cats: Dict[str, int] = {}
            stages: Dict[str, int] = {}
            intents: Dict[str, int] = {}
            total_quality = 0.0

            for p in all_prompts:
                if not p.is_archived:
                    cats[p.category] = cats.get(p.category, 0) + 1
                    stages[p.buying_stage] = stages.get(p.buying_stage, 0) + 1
                    intents[p.intent] = intents.get(p.intent, 0) + 1
                    total_quality += p.quality_score

            avg_quality = round(total_quality / total, 2) if total > 0 else 0.0

            return {
                "brand_id": brand_id,
                "profile_version": version,
                "total_prompts": total,
                "approved_prompts": approved,
                "archived_prompts": archived,
                "categories": cats,
                "buying_stages": stages,
                "intents": intents,
                "average_quality_score": avg_quality
            }
        finally:
            if close_session:
                await db.close()

    @staticmethod
    async def review_prompt(
        brand_id: str,
        prompt_id: str,
        lifecycle_status: str,  # "approved", "rejected", "proposed", "tracked"
        text: Optional[str] = None,
        review_notes: Optional[str] = None,
        db: Optional[AsyncSession] = None
    ) -> PromptCandidate:
        """Updates prompt review lifecycle status and text following user review."""
        close_session = False
        if db is None:
            db = async_session_factory()
            close_session = True

        try:
            stmt = select(PromptCandidate).where(
                PromptCandidate.id == prompt_id,
                PromptCandidate.brand_id == brand_id
            )
            res = await db.execute(stmt)
            prompt = res.scalar_one_or_none()
            if not prompt:
                raise ValueError("Prompt not found for this brand.")

            valid_statuses = ("generated", "validated", "proposed", "approved", "rejected", "tracked")
            if lifecycle_status not in valid_statuses:
                raise ValueError(f"Invalid lifecycle_status '{lifecycle_status}'. Allowed: {valid_statuses}")

            prompt.lifecycle_status = lifecycle_status
            prompt.is_approved = (lifecycle_status in ("approved", "tracked"))
            if review_notes is not None:
                prompt.review_notes = review_notes

            if text and text.strip() and text.strip() != prompt.text:
                history = list(prompt.edit_history or [])
                history.append({
                    "previous_text": prompt.text,
                    "updated_at": str(utc_now()),
                    "reason": review_notes or "user_edit"
                })
                prompt.text = text.strip()
                prompt.normalized_text = normalize_prompt_text(text.strip())
                prompt.user_edited = True
                prompt.edit_history = history

            await db.commit()
            await db.refresh(prompt)
            return prompt
        finally:
            if close_session:
                await db.close()

    @staticmethod
    async def batch_review_prompts(
        brand_id: str,
        prompt_ids: List[str],
        lifecycle_status: str,
        review_notes: Optional[str] = None,
        db: Optional[AsyncSession] = None
    ) -> List[PromptCandidate]:
        """Applies lifecycle status to multiple prompts for a brand."""
        updated = []
        for pid in prompt_ids:
            p = await PromptIntelligenceService.review_prompt(
                brand_id=brand_id,
                prompt_id=pid,
                lifecycle_status=lifecycle_status,
                review_notes=review_notes,
                db=db
            )
            updated.append(p)
        return updated

