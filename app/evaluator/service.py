"""Engine 3: AI Visibility Evaluator Service.

Orchestrates deterministic prompt dispatch, provider integration,
structured visibility evaluation, and persistence.
"""
import asyncio
import logging
import random
import time
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.models import (
    Brand,
    PromptRun,
    PromptCandidate,
    VisibilityScan,
    VisibilityResult,
    utc_now,
)
from app.db.session import async_session_factory
from app.evaluator.providers.base import AIModelProvider, ProviderResponse
from app.evaluator.providers.factory import get_evaluator_provider
from app.evaluator.evaluator import VisibilityResponseEvaluator, EvaluationResult

logger = logging.getLogger(__name__)

# Global concurrency semaphores per (event_loop_id, provider) to enforce rate limits across simultaneous scans
_GLOBAL_PROVIDER_SEMAPHORES: Dict[Tuple[int, str], asyncio.Semaphore] = {}


def get_provider_semaphore(provider_name: str, concurrency: Optional[int] = None) -> asyncio.Semaphore:
    """Return shared concurrency semaphore for provider bound to the active event loop."""
    try:
        loop = asyncio.get_running_loop()
        loop_id = id(loop)
    except RuntimeError:
        loop_id = 0
    key = (loop_id, provider_name)
    if key not in _GLOBAL_PROVIDER_SEMAPHORES:
        limit = concurrency or (2 if provider_name == "gemini" else 10)
        _GLOBAL_PROVIDER_SEMAPHORES[key] = asyncio.Semaphore(limit)
    return _GLOBAL_PROVIDER_SEMAPHORES[key]


class ProviderRateLimiter:
    """
    Sliding-window async rate limiter that prevents provider quota exhaustion (e.g. 15 RPM for Gemini free tier).
    Enforces <= 12 RPM (at least 5.0s min interval) shared across all concurrent workers.
    """
    def __init__(self, max_requests: int = 12, window_seconds: float = 60.0, min_interval: float = 5.0):
        self.max_requests = max_requests
        self.window_seconds = window_seconds
        self.min_interval = min_interval
        self._timestamps: List[float] = []
        self._last_dispatch: float = 0.0
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        async with self._lock:
            while True:
                now = time.time()
                # Purge timestamps outside sliding window
                cutoff = now - self.window_seconds
                self._timestamps = [t for t in self._timestamps if t > cutoff]

                # Minimum interval between consecutive request starts
                interval_wait = (self._last_dispatch + self.min_interval) - now

                # Window capacity wait (RPM ceiling)
                capacity_wait = 0.0
                if len(self._timestamps) >= self.max_requests:
                    oldest = self._timestamps[0]
                    capacity_wait = (oldest + self.window_seconds + 0.5) - now

                wait_time = max(interval_wait, capacity_wait)
                if wait_time > 0:
                    await asyncio.sleep(min(wait_time, 60.0))
                else:
                    now = time.time()
                    self._timestamps.append(now)
                    self._last_dispatch = now
                    break


_GLOBAL_PROVIDER_RATE_LIMITERS: Dict[Tuple[int, str], ProviderRateLimiter] = {}


def get_provider_rate_limiter(provider_name: str) -> Optional[ProviderRateLimiter]:
    """Return shared rate limiter for provider bound to active event loop."""
    if (provider_name or "").lower() != "gemini":
        return None
    try:
        loop = asyncio.get_running_loop()
        loop_id = id(loop)
    except RuntimeError:
        loop_id = 0
    key = (loop_id, provider_name.lower())
    if key not in _GLOBAL_PROVIDER_RATE_LIMITERS:
        # Enforce 12 requests per 60 seconds (safely under Gemini 15 RPM free tier), with 5.0s min interval
        _GLOBAL_PROVIDER_RATE_LIMITERS[key] = ProviderRateLimiter(max_requests=12, window_seconds=60.0, min_interval=5.0)
    return _GLOBAL_PROVIDER_RATE_LIMITERS[key]


class VisibilityEvaluatorService:
    """Core orchestration service for Engine 3 AI Visibility Scans."""

    @staticmethod
    def calculate_composite_score(
        mention_rate: float,
        recommendation_rate: float,
        target_citation_count: int,
        total_prompts: int,
        avg_position: Optional[float] = None
    ) -> float:
        """
        Calculates normalized composite visibility score (0.0 to 100.0).
        Methodology & weights (DEF-E3-04):
        - Brand Mention Rate: 40% weight (0 to 40 pts)
        - Recommendation Rate: 35% weight (0 to 35 pts)
        - Rank Factor (Reciprocal Rank): 15% weight (0 to 15 pts, based on 1.0 / avg_position)
        - Target Domain Citation Coverage: 10% weight (0 to 10 pts, based on min(citations / total, 1.0))
        """
        if total_prompts <= 0:
            return 0.0

        mention_component = max(0.0, min(1.0, mention_rate)) * 40.0
        recommendation_component = max(0.0, min(1.0, recommendation_rate)) * 35.0

        citation_ratio = min(max(0, target_citation_count) / total_prompts, 1.0)
        citation_component = citation_ratio * 10.0

        rank_component = 0.0
        if avg_position is not None and avg_position > 0:
            # Reciprocal rank weighting: Rank 1 -> 15.0 pts; Rank 2 -> 7.5 pts; Rank 8 -> 1.88 pts
            reciprocal_rank = 1.0 / float(avg_position)
            rank_component = min(1.0, reciprocal_rank) * 15.0

        composite = mention_component + recommendation_component + citation_component + rank_component
        return round(min(100.0, max(0.0, composite)), 1)


    @staticmethod
    async def reconcile_interrupted_scans(db: Optional[AsyncSession] = None) -> int:
        """
        Reconciles orphaned scans that remained in 'pending' or 'running' status
        following an unexpected process termination or server restart.
        """
        close_session = False
        if db is None:
            db = async_session_factory()
            close_session = True

        try:
            stmt = select(VisibilityScan).where(
                VisibilityScan.status.in_(["pending", "running"])
            )
            res = await db.execute(stmt)
            interrupted = res.scalars().all()
            for scan in interrupted:
                scan.status = "failed"
                scan.error_summary = "Scan execution interrupted by server shutdown or restart."
                scan.completed_at = utc_now()

            if interrupted:
                await db.commit()
                logger.info(f"Reconciled {len(interrupted)} interrupted visibility scan(s) to failed state.")
            return len(interrupted)
        finally:
            if close_session:
                await db.close()

    @staticmethod
    async def create_scan(
        brand_id: str,
        prompt_ids: Optional[List[str]] = None,
        provider: Optional[str] = "mock",
        model_name: Optional[str] = None,
        max_prompts: int = 20,
        force_rescan: bool = False,
        db: Optional[AsyncSession] = None
    ) -> VisibilityScan:
        """
        Creates an AI Visibility scan for approved Engine 2 prompts.
        Rejects unapproved or out-of-scope prompts. Prevents duplicate concurrent runs.
        """
        if (provider or "").lower() == "gemini" and not settings.LLM_API_KEY:
            raise ValueError(
                "Google Gemini is selected but LLM_API_KEY is not configured. "
                "Set LLM_API_KEY in .env or choose the offline mock provider."
            )

        close_session = False
        if db is None:
            db = async_session_factory()
            close_session = True

        try:
            brand = await db.get(Brand, brand_id)
            if not brand:
                raise ValueError("Brand not found.")

            # Idempotency check: if an active scan is already pending/running, return it unless force_rescan is set
            if not force_rescan:
                active_stmt = select(VisibilityScan).where(
                    VisibilityScan.brand_id == brand_id,
                    VisibilityScan.status.in_(["pending", "running"])
                ).order_by(desc(VisibilityScan.created_at))
                active_res = await db.execute(active_stmt)
                existing_active = active_res.scalars().first()
                if existing_active:
                    logger.info(f"Returning active visibility scan '{existing_active.id}' for brand '{brand_id}' (idempotent)")
                    return existing_active

            # Pin the scan to the latest completed prompt run for this brand,
            # ensuring Engine 3 evaluates the exact fresh set of prompts.
            latest_run_stmt = select(PromptRun).where(
                PromptRun.brand_id == brand_id,
                PromptRun.status == "completed"
            ).order_by(PromptRun.created_at.desc()).limit(1)
            latest_run_res = await db.execute(latest_run_stmt)
            latest_run = latest_run_res.scalar_one_or_none()

            if latest_run:
                scan_version = latest_run.profile_version
                stmt = select(PromptCandidate).where(
                    PromptCandidate.prompt_run_id == latest_run.id,
                    PromptCandidate.is_approved.is_(True),
                    PromptCandidate.lifecycle_status.in_(("approved", "tracked")),
                    PromptCandidate.is_archived.is_(False)
                ).order_by(desc(PromptCandidate.quality_score))
            else:
                version_stmt = select(PromptCandidate.profile_version).where(
                    PromptCandidate.brand_id == brand_id,
                    PromptCandidate.is_approved.is_(True),
                    PromptCandidate.lifecycle_status.in_(("approved", "tracked")),
                    PromptCandidate.is_archived.is_(False),
                ).order_by(PromptCandidate.profile_version.desc(), PromptCandidate.created_at.desc()).limit(1)
                version_res = await db.execute(version_stmt)
                scan_version = version_res.scalar_one_or_none()
                if scan_version is None:
                    raise ValueError(
                        "Brand has no approved prompts. Please generate and approve prompts in Engine 2 before scanning."
                    )
                stmt = select(PromptCandidate).where(
                    PromptCandidate.brand_id == brand_id,
                    PromptCandidate.profile_version == scan_version,
                    PromptCandidate.is_approved.is_(True),
                    PromptCandidate.lifecycle_status.in_(("approved", "tracked")),
                    PromptCandidate.is_archived.is_(False)
                ).order_by(desc(PromptCandidate.quality_score))

            res = await db.execute(stmt)
            approved_prompts = res.scalars().all()

            if not approved_prompts:
                raise ValueError(
                    "Brand has no approved prompts. Please generate and approve prompts in Engine 2 before scanning."
                )

            # Filter by specific prompt_ids if requested
            if prompt_ids:
                approved_map = {p.id: p for p in approved_prompts}
                selected_prompts = []
                seen_prompt_ids = set()
                for pid in prompt_ids:
                    if pid not in approved_map:
                        raise ValueError(
                            f"Prompt '{pid}' is not approved or does not belong to brand '{brand.business_name}'."
                        )
                    if pid not in seen_prompt_ids:
                        selected_prompts.append(approved_map[pid])
                        seen_prompt_ids.add(pid)
            else:
                selected_prompts = approved_prompts[:max_prompts]

            if not selected_prompts:
                raise ValueError("No valid approved prompts selected for scan.")

            # ── Quality Gate: validate Engine 2 prompts before Engine 3 dispatch ──
            from app.prompts.quality_gate import QualityGate
            from app.prompts.scorer import normalize_prompt_text as _npt
            from collections import Counter

            # Determine brand's primary category from prompts or brand profile
            known_cats = {"crm", "ai_assistants", "clothing", "footwear", "skincare"}
            brand_primary_category = None
            for p in selected_prompts:
                if p.category and p.category.lower() in known_cats:
                    brand_primary_category = p.category.lower()
                    break
            if not brand_primary_category:
                ind = (brand.industry or "").lower()
                name = (brand.business_name or "").lower()
                if any(k in ind or k in name for k in ("ai", "artificial intelligence", "assistant", "bot", "aurora")):
                    brand_primary_category = "ai_assistants"
                elif any(k in ind or k in name for k in ("shoe", "footwear", "sneaker", "running", "nike")):
                    brand_primary_category = "footwear"
                elif any(k in ind or k in name for k in ("cloth", "apparel", "fashion", "garment", "hm", "h&m")):
                    brand_primary_category = "clothing"
                elif any(k in ind or k in name for k in ("skin", "beauty", "cosmetic", "derma", "vaseline")):
                    brand_primary_category = "skincare"
                else:
                    brand_primary_category = "crm"

            if prompt_ids:
                # Explicit prompt_ids were requested by the caller; keep the exact selected prompts
                final_prompt_objects = selected_prompts
                gate_stats = {
                    "total_evaluated": len(selected_prompts),
                    "generated_passed": len(selected_prompts),
                    "rejected_count": 0,
                    "fallback_count": 0,
                    "shortfall": 0,
                    "generated_pass_rate": 1.0,
                    "fallback_rate": 0.0,
                }
            else:
                gate = QualityGate(
                    brand_category=brand_primary_category,
                    brand_name=brand.business_name,
                    brand_domain=brand.domain,
                )

                prompt_dicts = [
                    {
                        "id": p.id,
                        "text": p.text,
                        "category": p.category,
                        "intent": p.intent,
                        "quality_score": p.quality_score,
                        "is_approved": p.is_approved,
                        "target_product_service": p.target_product_service,
                        "target_audience": p.target_audience,
                    }
                    for p in selected_prompts
                ]

                gate_results = gate.evaluate_batch(prompt_dicts, target_count=len(selected_prompts))
                gate_stats = gate.get_stats()

                # Build final prompt list: keep passed originals, persist gold-fallback PromptCandidates
                final_prompt_objects = []
                passed_original_ids = {r["original_id"] for r in gate_results if r["accepted"] and r["provenance"] == "generated"}
                for p in selected_prompts:
                    if p.id in passed_original_ids:
                        final_prompt_objects.append(p)

                # Persist gold-fallback prompts as PromptCandidate records
                gold_fallbacks = [r for r in gate_results if r["accepted"] and r["provenance"] == "gold_fallback"]
                for fb in gold_fallbacks:
                    fb_model = PromptCandidate(
                        brand_id=brand.id,
                        prompt_run_id=latest_run.id if latest_run else selected_prompts[0].prompt_run_id,
                        profile_version=scan_version,
                        text=fb["text"],
                        normalized_text=_npt(fb["text"]),
                        category=fb.get("category", brand_primary_category),
                        intent=fb.get("intent", "broad_recommendation"),
                        buying_stage="consideration",
                        language="en",
                        provenance_fact_ids=[],
                        grounding_evidence=[],
                        scores={
                            "provenance": "gold_fallback",
                            "gold_id": fb["gold_id"],
                            "quality_gate_source": "auralyt_engine2_prompt_quality_gold.json",
                        },
                        quality_score=0.9,
                        is_approved=True,
                        lifecycle_status="approved",
                        review_notes=f"Gold fallback (ID: {fb['gold_id']}): replaces rejected Engine 2 candidate",
                        is_archived=False,
                        user_edited=False,
                        edit_history=[],
                    )
                    db.add(fb_model)
                    final_prompt_objects.append(fb_model)

                if gold_fallbacks:
                    await db.commit()
                    for fb_obj in final_prompt_objects:
                        try:
                            await db.refresh(fb_obj)
                        except Exception:
                            pass

            if not final_prompt_objects:
                raise ValueError("Quality gate rejected all prompts and no gold fallbacks were available.")

            # Resolve active provider adapter
            active_provider = get_evaluator_provider(provider)
            selected_model = model_name or active_provider.default_model

            # Create scan record
            scan = VisibilityScan(
                brand_id=brand.id,
                profile_version=scan_version,
                status="pending",
                provider=active_provider.provider_name,
                model_name=selected_model,
                prompts_selected=len(final_prompt_objects),
                prompts_completed=0,
                prompts_failed=0,
                config_metadata={
                    "prompt_ids": [p.id for p in final_prompt_objects],
                    "force_rescan": force_rescan,
                    "provider_mode": active_provider.provider_name,
                    "quality_gate": {
                        "enabled": True,
                        "brand_category": brand_primary_category,
                        "total_evaluated": gate_stats["total_evaluated"],
                        "generated_passed": gate_stats["generated_passed"],
                        "rejected_count": gate_stats["rejected_count"],
                        "fallback_count": gate_stats["fallback_count"],
                        "shortfall": gate_stats["shortfall"],
                        "generated_pass_rate": gate_stats["generated_pass_rate"],
                        "fallback_rate": gate_stats["fallback_rate"],
                    }
                }
            )
            db.add(scan)
            await db.commit()
            await db.refresh(scan)

            # Launch background execution task
            asyncio.create_task(VisibilityEvaluatorService.execute_scan(scan.id))

            return scan

        finally:
            if close_session:
                await db.close()

    @staticmethod
    async def execute_scan(
        scan_id: str,
        db: Optional[AsyncSession] = None,
        scan_timeout_seconds: Optional[float] = None
    ) -> None:
        """Worker that dispatches prompts to provider with bounded concurrency, retries, and persistence."""
        close_session = False
        if db is None:
            db = async_session_factory()
            close_session = True

        try:
            scan = await db.get(VisibilityScan, scan_id)
            if not scan:
                logger.error(f"VisibilityScan '{scan_id}' not found.")
                return

            brand = await db.get(Brand, scan.brand_id)
            if not brand:
                logger.error(f"Brand '{scan.brand_id}' not found for scan '{scan_id}'.")
                scan.status = "failed"
                scan.error_summary = "Associated brand record not found."
                await db.commit()
                return

            # Mark scan running
            scan.status = "running"
            scan.started_at = utc_now()
            await db.commit()

            start_time = time.time()
            prompt_ids = scan.config_metadata.get("prompt_ids", [])

            # Fetch prompts
            stmt = select(PromptCandidate).where(
                PromptCandidate.id.in_(prompt_ids),
                PromptCandidate.brand_id == scan.brand_id,
                PromptCandidate.profile_version == scan.profile_version,
            )
            res = await db.execute(stmt)
            prompts = res.scalars().all()

            if len(prompts) != len(set(prompt_ids)):
                scan.status = "failed"
                scan.prompts_failed = max(0, len(set(prompt_ids)) - len(prompts))
                scan.error_summary = "Selected prompts no longer match the scan's brand or profile version."
                scan.completed_at = utc_now()
                await db.commit()
                return

            # Check existing results to prevent duplicate rows on re-runs or retries
            existing_stmt = select(VisibilityResult).where(VisibilityResult.scan_id == scan.id)
            existing_res = await db.execute(existing_stmt)
            existing_results = list(existing_res.scalars().all())
            evaluated_prompt_ids = {r.prompt_id for r in existing_results}

            results_to_persist: List[VisibilityResult] = list(existing_results)
            completed_count = sum(1 for r in existing_results if r.execution_status == "success")
            failed_count = sum(1 for r in existing_results if r.execution_status == "error")
            tokens_total = sum(r.tokens_used or 0 for r in existing_results)

            prompts_to_evaluate = [p for p in prompts if p.id not in evaluated_prompt_ids]

            provider = get_evaluator_provider(scan.provider)
            semaphore = get_provider_semaphore(scan.provider)
            rate_limiter = get_provider_rate_limiter(scan.provider)

            # Reusable pooled client if provider supports it
            shared_client = None
            if hasattr(provider, "create_client"):
                shared_client = provider.create_client()

            timed_out = False

            try:
                if prompts_to_evaluate:
                    async def process_prompt(prompt_obj: PromptCandidate) -> Tuple[PromptCandidate, ProviderResponse, Optional[EvaluationResult]]:
                        max_attempts = 3
                        last_resp: Optional[ProviderResponse] = None

                        for attempt in range(max_attempts):
                            # 1. Pacing rate limit check (enforces sliding window <= 12 RPM for Gemini across all workers)
                            # Applied to every attempt (initial and retries) to strictly govern combined starts across workers
                            if rate_limiter:
                                await rate_limiter.acquire()

                            resp: Optional[ProviderResponse] = None
                            try:
                                # 2. Acquire semaphore ONLY for network call (never while sleeping on retries)
                                async with semaphore:
                                    query_kwargs = {"client": shared_client} if shared_client is not None else {}
                                    try:
                                        query_coro = provider.query(
                                            prompt=prompt_obj.text,
                                            model_name=scan.model_name,
                                            **query_kwargs
                                        )
                                    except TypeError:
                                        query_coro = provider.query(
                                            prompt=prompt_obj.text,
                                            model_name=scan.model_name
                                        )
                                    # Enforce a bounded per-prompt timeout so hanging queries fail fast
                                    resp = await asyncio.wait_for(query_coro, timeout=22.0)
                                last_resp = resp
                            except asyncio.TimeoutError:
                                logger.warning(f"Query timed out for prompt '{prompt_obj.id[:8]}' on attempt {attempt+1}")
                                last_resp = ProviderResponse(
                                    text="",
                                    provider=scan.provider,
                                    model_name=scan.model_name,
                                    is_success=False,
                                    is_retryable=True,
                                    error_message="Query timed out after 22 seconds.",
                                    metadata={"status_code": 408, "timed_out": True}
                                )
                                resp = last_resp
                            except Exception as e:
                                logger.warning(f"Error querying provider on attempt {attempt+1}: {e}")
                                last_resp = ProviderResponse(
                                    text="",
                                    provider=scan.provider,
                                    model_name=scan.model_name,
                                    is_success=False,
                                    is_retryable=True,
                                    error_message=str(e)
                                )
                                resp = last_resp

                            if resp and resp.is_success and resp.text.strip():
                                provider_metadata = dict(resp.metadata or {})
                                if resp.grounding_citations:
                                    provider_metadata["grounding_citations"] = list(resp.grounding_citations)
                                resp.metadata = provider_metadata
                                eval_res = VisibilityResponseEvaluator.evaluate(
                                    response_text=resp.text,
                                    brand_name=brand.business_name,
                                    brand_domain=brand.domain,
                                    known_competitors=None,
                                    provider_metadata=provider_metadata
                                )
                                return prompt_obj, resp, eval_res
                            else:
                                if resp and not resp.is_retryable:
                                    break
                                if attempt < max_attempts - 1:
                                    retry_after = (resp.metadata or {}).get("retry_after") if resp else None
                                    status_code = getattr(resp, "metadata", {}).get("status_code")
                                    is_429 = status_code == 429
                                    is_503 = status_code in (500, 502, 503, 504)
                                    is_timeout = getattr(resp, "metadata", {}).get("timed_out") or "timed out" in (getattr(resp, "error_message", "") or "").lower()

                                    # Bound timeout retries: allow max 1 retry for timeouts to prevent queue stalling
                                    if is_timeout and attempt >= 1:
                                        break

                                    if retry_after is not None and 0 < retry_after <= 60:
                                        delay = min(float(retry_after), 35.0) + random.uniform(0.5, 1.5)
                                    elif is_429:
                                        delay = 14.0 + random.uniform(1.0, 3.0)
                                    elif is_503:
                                        # Bounded exponential backoff with jitter for transient service overloads
                                        delay = min(3.0 * (2 ** attempt) + random.uniform(0.5, 2.0), 12.0)
                                    elif is_timeout:
                                        delay = 4.0 + random.uniform(0.5, 1.5)
                                    else:
                                        base_delay = 1.5 * (2 ** attempt)
                                        jitter = random.uniform(0.2, 0.5)
                                        delay = min(base_delay + jitter, 5.0)
                                    logger.info(f"Retrying prompt '{prompt_obj.id[:8]}' after {delay:.1f}s delay (attempt {attempt+1}/{max_attempts}, status={status_code})")
                                    await asyncio.sleep(delay)

                        if last_resp is None:
                            last_resp = ProviderResponse(
                                text="",
                                provider=scan.provider,
                                model_name=scan.model_name,
                                is_success=False,
                                is_retryable=False,
                                error_message="All retry attempts failed to query provider."
                            )
                        return prompt_obj, last_resp, None

                    # Execution loop with overall deadline and real-time incremental persistence
                    deadline = scan_timeout_seconds or max(240.0, len(prompts_to_evaluate) * 15.0)
                    pending_tasks = {
                        asyncio.create_task(process_prompt(p)): p for p in prompts_to_evaluate
                    }

                    while pending_tasks:
                        elapsed = time.time() - start_time
                        remaining = deadline - elapsed
                        if remaining <= 0:
                            timed_out = True
                            logger.warning(f"Scan '{scan.id}' exceeded deadline of {deadline}s")
                            break

                        done, _ = await asyncio.wait(
                            pending_tasks.keys(),
                            timeout=min(remaining, 1.5),
                            return_when=asyncio.FIRST_COMPLETED
                        )

                        if not done:
                            if time.time() - start_time >= deadline:
                                timed_out = True
                                break
                            continue

                        for finished_task in done:
                            p_orig = pending_tasks.pop(finished_task)
                            try:
                                item = await finished_task
                            except asyncio.CancelledError:
                                item = (p_orig, ProviderResponse(
                                    text="",
                                    provider=scan.provider,
                                    model_name=scan.model_name,
                                    is_success=False,
                                    is_retryable=False,
                                    error_message="Prompt evaluation timed out or was cancelled."
                                ), None)
                            except Exception as ex:
                                logger.exception(f"Unhandled prompt evaluation exception: {ex}")
                                item = (p_orig, ProviderResponse(
                                    text="",
                                    provider=scan.provider,
                                    model_name=scan.model_name,
                                    is_success=False,
                                    is_retryable=False,
                                    error_message=f"Prompt evaluation exception: {str(ex)}"
                                ), None)

                            prompt_obj, p_resp, eval_res = item

                            if p_resp.is_success and eval_res:
                                completed_count += 1
                                if p_resp.tokens_used:
                                    tokens_total += p_resp.tokens_used

                                res_metadata = dict(p_resp.metadata or {})
                                res_metadata["target_brand_citations"] = list(eval_res.target_brand_citations)
                                res_metadata["competitor_citations"] = list(eval_res.competitor_citations)
                                res_metadata["mention_confidence"] = eval_res.mention_confidence

                                vis_res = VisibilityResult(
                                    scan_id=scan.id,
                                    brand_id=brand.id,
                                    prompt_id=prompt_obj.id,
                                    prompt_text=prompt_obj.text,
                                    provider=scan.provider,
                                    model_name=scan.model_name,
                                    execution_status="success",
                                    raw_response_text=p_resp.text,
                                    raw_response_metadata=res_metadata,
                                    latency_ms=p_resp.latency_ms,
                                    tokens_used=p_resp.tokens_used,
                                    brand_mentioned=eval_res.brand_mentioned,
                                    mention_context=eval_res.mention_context,
                                    recommendation_status=eval_res.recommendation_status,
                                    competitor_mentions=eval_res.competitor_mentions,
                                    comparative_position=eval_res.comparative_position,
                                    citations=eval_res.citations,
                                    provider_citations=eval_res.provider_citations,
                                    response_citations=eval_res.response_citations,
                                    sentiment_score=eval_res.sentiment_score,
                                    visibility_rank=eval_res.visibility_rank,
                                    evaluation_reasoning=eval_res.evaluation_reasoning
                                )
                            else:
                                failed_count += 1
                                vis_res = VisibilityResult(
                                    scan_id=scan.id,
                                    brand_id=brand.id,
                                    prompt_id=prompt_obj.id,
                                    prompt_text=prompt_obj.text,
                                    provider=scan.provider,
                                    model_name=scan.model_name,
                                    execution_status="error",
                                    raw_response_text=p_resp.text or "",
                                    raw_response_metadata=p_resp.metadata or {},
                                    latency_ms=p_resp.latency_ms,
                                    error_details=p_resp.error_message or "Unknown provider failure",
                                    brand_mentioned=False,
                                    mention_context=None,
                                    recommendation_status="unknown",
                                    competitor_mentions=[],
                                    comparative_position="unknown",
                                    citations=[],
                                    evaluation_reasoning=f"Provider query failed: {p_resp.error_message or 'Unknown error'}"
                                )

                            db.add(vis_res)
                            results_to_persist.append(vis_res)

                            # Persist real-time progress to DB immediately
                            scan.prompts_completed = completed_count
                            scan.prompts_failed = failed_count
                            await db.commit()

                    # Reconcile any remaining pending tasks that timed out at scan deadline
                    if pending_tasks:
                        logger.warning(
                            f"Scan '{scan.id}' has {len(pending_tasks)} uncompleted tasks at deadline. "
                            f"Persisting terminal timeout records for reconciliation."
                        )
                        for task, p_orig in list(pending_tasks.items()):
                            task.cancel()
                            failed_count += 1
                            vis_res = VisibilityResult(
                                scan_id=scan.id,
                                brand_id=brand.id,
                                prompt_id=p_orig.id,
                                prompt_text=p_orig.text,
                                provider=scan.provider,
                                model_name=scan.model_name,
                                execution_status="timeout",
                                raw_response_text="",
                                raw_response_metadata={"status_code": 408, "timed_out": True},
                                latency_ms=int((time.time() - start_time) * 1000),
                                error_details=f"Evaluation timed out: scan deadline of {deadline:.1f}s exceeded before query completed.",
                                brand_mentioned=False,
                                mention_context=None,
                                recommendation_status="unknown",
                                competitor_mentions=[],
                                comparative_position="unknown",
                                citations=[],
                                evaluation_reasoning="Evaluation timed out before model response was received."
                            )
                            db.add(vis_res)
                            results_to_persist.append(vis_res)

                        pending_tasks.clear()
                        scan.prompts_completed = completed_count
                        scan.prompts_failed = failed_count
                        await db.commit()

            finally:
                if shared_client and hasattr(shared_client, "aclose"):
                    try:
                        await shared_client.aclose()
                    except Exception:
                        pass

            # Compute aggregate scan metrics
            duration = round(time.time() - start_time, 2)
            scan.prompts_completed = completed_count
            scan.prompts_failed = failed_count
            scan.duration_seconds = duration
            scan.total_tokens_used = tokens_total if tokens_total > 0 else None
            scan.completed_at = utc_now()

            total_prompts = scan.prompts_selected or len(prompts)

            if total_prompts > 0 and completed_count > 0:
                mentions = sum(1 for r in results_to_persist if r.brand_mentioned)
                recommendations = sum(1 for r in results_to_persist if r.recommendation_status == "recommended")
                ranked = [r.visibility_rank for r in results_to_persist if r.visibility_rank is not None]

                # Honest denominator: total requested prompts
                mention_rate = round(mentions / total_prompts, 3)
                recommendation_rate = round(recommendations / total_prompts, 3)
                avg_position = round(sum(ranked) / len(ranked), 2) if ranked else None

                target_citation_count = sum(
                    len(r.raw_response_metadata.get("target_brand_citations", []))
                    for r in results_to_persist
                )

                score = VisibilityEvaluatorService.calculate_composite_score(
                    mention_rate=mention_rate,
                    recommendation_rate=recommendation_rate,
                    target_citation_count=target_citation_count,
                    total_prompts=total_prompts,
                    avg_position=avg_position
                )

                scan.mention_rate = mention_rate
                scan.recommendation_rate = recommendation_rate
                scan.average_position = avg_position
                scan.visibility_score = score
            else:
                scan.visibility_score = None
                scan.mention_rate = None
                scan.recommendation_rate = None

            if timed_out:
                if completed_count > 0:
                    scan.status = "completed_with_errors"
                    scan.error_summary = f"Scan timed out after {duration}s: {failed_count} out of {total_prompts} prompts failed or timed out."
                else:
                    scan.status = "failed"
                    scan.error_summary = f"Scan execution timed out after {duration}s (deadline exceeded)."
            elif failed_count == 0:
                scan.status = "completed"
            elif completed_count > 0:
                scan.status = "completed_with_errors"
                scan.error_summary = f"{failed_count} out of {total_prompts} prompts failed to evaluate."
            else:
                scan.status = "failed"
                first_err = next((r.error_details for r in results_to_persist if r.error_details), None)
                if first_err:
                    clean_err = first_err.split("\n")[0].strip()
                    scan.error_summary = f"All prompt queries failed: {clean_err}"
                else:
                    scan.error_summary = "All prompt queries failed."

            await db.commit()
            logger.info(
                f"Completed visibility scan '{scan_id}' for brand '{brand.business_name}': "
                f"score={scan.visibility_score}, status={scan.status}, duration={duration}s"
            )
        finally:
            if close_session:
                await db.close()

    @staticmethod
    async def get_scan(scan_id: str, brand_id: str, db: AsyncSession) -> VisibilityScan:
        """Fetch a specific visibility scan with brand scope validation."""
        scan = await db.get(VisibilityScan, scan_id)
        if not scan or scan.brand_id != brand_id:
            raise ValueError("Visibility scan not found.")
        return scan

    @staticmethod
    async def list_scans(brand_id: str, db: AsyncSession) -> List[VisibilityScan]:
        """List historical visibility scans for a brand."""
        brand = await db.get(Brand, brand_id)
        if not brand:
            raise ValueError("Brand not found.")

        stmt = select(VisibilityScan).where(
            VisibilityScan.brand_id == brand_id
        ).order_by(desc(VisibilityScan.created_at))

        res = await db.execute(stmt)
        return res.scalars().all()

    @staticmethod
    async def get_scan_results(scan_id: str, brand_id: str, db: AsyncSession) -> Tuple[VisibilityScan, List[VisibilityResult]]:
        """Fetch scan and all detailed prompt evaluation results."""
        scan = await VisibilityEvaluatorService.get_scan(scan_id, brand_id, db)

        stmt = select(VisibilityResult).where(
            VisibilityResult.scan_id == scan_id
        ).order_by(desc(VisibilityResult.created_at))

        res = await db.execute(stmt)
        results = res.scalars().all()
        return scan, results
