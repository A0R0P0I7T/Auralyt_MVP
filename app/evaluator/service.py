"""Engine 3: AI Visibility Evaluator Service.

Orchestrates deterministic prompt dispatch, provider integration,
structured visibility evaluation, and persistence.
"""
import asyncio
import logging
import time
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import select, desc
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.config import settings
from app.db.models import (
    Brand,
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

# Concurrency limit per scan run to respect provider rate limits
MAX_SCAN_CONCURRENCY = 3


class VisibilityEvaluatorService:
    """Core orchestration service for Engine 3 AI Visibility Scans."""

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
        Rejects unapproved or out-of-scope prompts.
        """
        close_session = False
        if db is None:
            db = async_session_factory()
            close_session = True

        try:
            brand = await db.get(Brand, brand_id)
            if not brand:
                raise ValueError("Brand not found.")

            # Select approved, non-archived Engine 2 prompts for this brand
            stmt = select(PromptCandidate).where(
                PromptCandidate.brand_id == brand_id,
                PromptCandidate.is_approved == True,
                PromptCandidate.is_archived == False
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
                for pid in prompt_ids:
                    if pid not in approved_map:
                        raise ValueError(
                            f"Prompt '{pid}' is not approved or does not belong to brand '{brand.business_name}'."
                        )
                    selected_prompts.append(approved_map[pid])
            else:
                selected_prompts = approved_prompts[:max_prompts]

            if not selected_prompts:
                raise ValueError("No valid approved prompts selected for scan.")

            # Resolve active provider adapter
            active_provider = get_evaluator_provider(provider)
            selected_model = model_name or active_provider.default_model

            # Create scan record
            scan = VisibilityScan(
                brand_id=brand.id,
                profile_version=brand.profile_version,
                status="pending",
                provider=active_provider.provider_name,
                model_name=selected_model,
                prompts_selected=len(selected_prompts),
                prompts_completed=0,
                prompts_failed=0,
                config_metadata={
                    "prompt_ids": [p.id for p in selected_prompts],
                    "force_rescan": force_rescan,
                    "provider_mode": active_provider.provider_name
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
    async def execute_scan(scan_id: str, db: Optional[AsyncSession] = None) -> None:
        """Worker that dispatches prompts to provider and records evaluations."""
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
            stmt = select(PromptCandidate).where(PromptCandidate.id.in_(prompt_ids))
            res = await db.execute(stmt)
            prompts = res.scalars().all()

            if not prompts:
                scan.status = "failed"
                scan.error_summary = "Prompts selected for scan could not be loaded."
                scan.completed_at = utc_now()
                await db.commit()
                return

            provider = get_evaluator_provider(scan.provider)
            semaphore = asyncio.Semaphore(MAX_SCAN_CONCURRENCY)

            results_to_persist: List[VisibilityResult] = []
            tokens_total = 0
            completed_count = 0
            failed_count = 0

            async def process_prompt(prompt_obj: PromptCandidate) -> Tuple[PromptCandidate, ProviderResponse, Optional[EvaluationResult]]:
                async with semaphore:
                    # Bounded retries for transient failures
                    max_attempts = 2
                    last_resp: Optional[ProviderResponse] = None

                    for attempt in range(max_attempts):
                        try:
                            resp = await provider.query(
                                prompt=prompt_obj.text,
                                model_name=scan.model_name
                            )
                            last_resp = resp
                            if resp.is_success:
                                eval_res = VisibilityResponseEvaluator.evaluate(
                                    response_text=resp.text,
                                    brand_name=brand.business_name,
                                    brand_domain=brand.domain,
                                    known_competitors=None,
                                    provider_metadata=resp.metadata
                                )
                                return prompt_obj, resp, eval_res
                        except Exception as e:
                            logger.warning(f"Error querying provider on attempt {attempt+1}: {e}")
                            if attempt < max_attempts - 1:
                                await asyncio.sleep(0.5)

                    # If all attempts failed
                    if last_resp is None:
                        last_resp = ProviderResponse(
                            text="",
                            provider=scan.provider,
                            model_name=scan.model_name,
                            is_success=False,
                            error_message="All retry attempts failed to query provider."
                        )
                    return prompt_obj, last_resp, None

            # Execute prompts concurrently with bounded semaphore
            tasks = [process_prompt(p) for p in prompts]
            executed = await asyncio.gather(*tasks, return_exceptions=True)

            for item in executed:
                if isinstance(item, Exception):
                    logger.error(f"Unhandled exception in prompt evaluation: {item}")
                    failed_count += 1
                    continue

                prompt_obj, p_resp, eval_res = item

                if p_resp.is_success and eval_res:
                    completed_count += 1
                    if p_resp.tokens_used:
                        tokens_total += p_resp.tokens_used

                    vis_res = VisibilityResult(
                        scan_id=scan.id,
                        brand_id=brand.id,
                        prompt_id=prompt_obj.id,
                        prompt_text=prompt_obj.text,
                        provider=scan.provider,
                        model_name=scan.model_name,
                        execution_status="success",
                        raw_response_text=p_resp.text,
                        raw_response_metadata=p_resp.metadata,
                        latency_ms=p_resp.latency_ms,
                        tokens_used=p_resp.tokens_used,
                        brand_mentioned=eval_res.brand_mentioned,
                        mention_context=eval_res.mention_context,
                        recommendation_status=eval_res.recommendation_status,
                        competitor_mentions=eval_res.competitor_mentions,
                        comparative_position=eval_res.comparative_position,
                        citations=eval_res.citations,
                        sentiment_score=eval_res.sentiment_score,
                        visibility_rank=eval_res.visibility_rank,
                        evaluation_reasoning=eval_res.evaluation_reasoning
                    )
                    results_to_persist.append(vis_res)
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
                        evaluation_reasoning="Provider query failed."
                    )
                    results_to_persist.append(vis_res)

            # Persist results in DB
            for r in results_to_persist:
                db.add(r)

            # Compute aggregate scan metrics
            duration = round(time.time() - start_time, 2)
            scan.prompts_completed = completed_count
            scan.prompts_failed = failed_count
            scan.duration_seconds = duration
            scan.total_tokens_used = tokens_total if tokens_total > 0 else None
            scan.completed_at = utc_now()

            if completed_count > 0:
                mentions = sum(1 for r in results_to_persist if r.brand_mentioned)
                recommendations = sum(1 for r in results_to_persist if r.recommendation_status == "recommended")
                ranked = [r.visibility_rank for r in results_to_persist if r.visibility_rank is not None]

                mention_rate = round(mentions / completed_count, 3)
                recommendation_rate = round(recommendations / completed_count, 3)
                avg_position = round(sum(ranked) / len(ranked), 2) if ranked else None

                # Composite Visibility Score (0 - 100)
                # 50% mention presence + 40% recommendation presence + 10% citation presence
                citation_count = sum(len(r.citations) for r in results_to_persist)
                citation_factor = min(citation_count / (completed_count * 2), 1.0) * 10
                score = round((mention_rate * 50.0) + (recommendation_rate * 40.0) + citation_factor, 1)

                scan.mention_rate = mention_rate
                scan.recommendation_rate = recommendation_rate
                scan.average_position = avg_position
                scan.visibility_score = score
            else:
                scan.visibility_score = 0.0
                scan.mention_rate = 0.0
                scan.recommendation_rate = 0.0

            if failed_count == 0:
                scan.status = "completed"
            elif completed_count > 0:
                scan.status = "completed_with_errors"
                scan.error_summary = f"{failed_count} out of {len(prompts)} prompts failed to evaluate."
            else:
                scan.status = "failed"
                scan.error_summary = "All prompt queries failed."

            await db.commit()
            logger.info(
                f"Completed visibility scan '{scan_id}' for brand '{brand.business_name}': "
                f"score={scan.visibility_score}, mentions={scan.mention_rate}, duration={duration}s"
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
