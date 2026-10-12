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
from app.prompts.planner import CoveragePlanner
from app.prompts.generator import get_prompt_generator
from app.prompts.validator import PromptValidator
from app.prompts.scorer import PromptScorer, normalize_prompt_text
from app.prompts.models import GeneratedPromptCandidate

logger = logging.getLogger(__name__)


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

            # The mutable brand counter may point at a pending/failed refresh.
            # Generate only from the completed snapshot returned by Engine 1.
            current_version = normalized_profile.profile_version

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
                    prompts_stmt = select(PromptCandidate).where(
                        PromptCandidate.prompt_run_id == latest_run.id,
                        PromptCandidate.is_archived.is_(False)
                    ).order_by(desc(PromptCandidate.quality_score))
                    p_res = await db.execute(prompts_stmt)
                    existing_prompts = list(p_res.scalars().all())

                    if len(existing_prompts) >= prompt_count:
                        logger.info(f"Reusing cached prompt run {latest_run.id} for brand {brand_id} v{current_version}")
                        return latest_run, existing_prompts

            # 5. Create new PromptRun
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
                }
            )
            db.add(run)
            await db.commit()
            await db.refresh(run)

            start_time = time.time()

            try:
                # 6. Stage B: Intent & Coverage Planning
                plan = CoveragePlanner.create_plan(
                    profile=normalized_profile,
                    requested_count=prompt_count,
                    allowed_categories=categories
                )

                # 7. Stage C: Candidate Generation
                generator = get_prompt_generator()
                raw_candidates = await generator.generate(normalized_profile, plan)

                # 8. Stage D: Quality Validation
                validated_candidates: List[GeneratedPromptCandidate] = []
                for cand in raw_candidates:
                    is_valid, reason = PromptValidator.validate(cand, normalized_profile)
                    if is_valid:
                        validated_candidates.append(cand)
                    else:
                        logger.debug(f"Candidate rejected by validator: '{cand.text}' -> {reason}")

                # 9. Stage E: Deduplication & Scoring
                unique_candidates = PromptScorer.deduplicate(validated_candidates)

                scored_candidates: List[GeneratedPromptCandidate] = []
                accepted_so_far: List[GeneratedPromptCandidate] = []
                for cand in unique_candidates:
                    scored = PromptScorer.score_candidate(cand, normalized_profile, accepted_so_far)
                    scored_candidates.append(scored)
                    accepted_so_far.append(scored)

                # Limit to prompt_count requested
                final_candidates = scored_candidates[:prompt_count]

                # 10. Stage F: Persistence
                existing_text_stmt = select(PromptCandidate.normalized_text).where(
                    PromptCandidate.brand_id == brand_id,
                    PromptCandidate.profile_version == current_version,
                )
                existing_text_res = await db.execute(existing_text_stmt)
                existing_texts = set(existing_text_res.scalars().all())
                persisted_models: List[PromptCandidate] = []
                for fc in final_candidates:
                    normalized_text = normalize_prompt_text(fc.text)
                    if normalized_text in existing_texts:
                        continue
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
                        scores=fc.scores,
                        quality_score=fc.quality_score,
                        is_approved=True,
                        is_archived=False,
                        user_edited=False,
                        edit_history=[]
                    )
                    db.add(model)
                    persisted_models.append(model)
                    existing_texts.add(normalized_text)

                # Update Run Status
                duration = time.time() - start_time
                run.status = "completed"
                run.prompts_generated = len(persisted_models)
                run.duration_seconds = round(duration, 2)
                run.completed_at = utc_now()

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
