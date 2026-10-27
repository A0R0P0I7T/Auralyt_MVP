"""Regression tests for Engine 3 incomplete results and false NOT MENTIONED labeling.

Targeting:
1. All prompts must reach terminal VisibilityResult persistence upon deadline timeout (no dropped/missing prompts).
2. Counter reconciliation: prompts_completed + prompts_failed == prompts_selected.
3. Failed/error/timeout queries must be distinctly categorized as failed/error, NEVER falsely labeled as 'NOT MENTIONED' in UI/serialization contracts.
4. Per-prompt timeouts prevent single query hangs from starving the queue.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from sqlalchemy import select

from app.db.models import (
    Brand,
    PromptRun,
    PromptCandidate,
    VisibilityScan,
    VisibilityResult,
)
from app.evaluator.providers.base import AIModelProvider, ProviderResponse
from app.evaluator.service import VisibilityEvaluatorService


async def create_test_brand_and_candidates(test_db_session, count=5):
    """Sets up a test brand and approved prompts in the database."""
    brand = Brand(
        business_name="HubSpot Test",
        domain="hubspot.com",
        industry="CRM Software",
        profile_version=1
    )
    test_db_session.add(brand)
    await test_db_session.commit()
    await test_db_session.refresh(brand)

    run = PromptRun(
        brand_id=brand.id,
        profile_version=1,
        status="completed",
        prompt_count_requested=count,
        prompts_generated=count
    )
    test_db_session.add(run)
    await test_db_session.commit()
    await test_db_session.refresh(run)

    prompts = []
    for i in range(count):
        text_val = f"What is a great CRM for small business sales teams {i+1}?"
        p = PromptCandidate(
            brand_id=brand.id,
            prompt_run_id=run.id,
            profile_version=1,
            text=text_val,
            normalized_text=text_val.lower(),
            intent="commercial_evaluation",
            category="CRM",
            lifecycle_status="approved",
            is_approved=True,
            is_archived=False,
            quality_score=95.0 - i
        )
        test_db_session.add(p)
        prompts.append(p)

    await test_db_session.commit()
    for p in prompts:
        await test_db_session.refresh(p)

    return brand, run, prompts


# =====================================================================
# 1. Regression: Scan deadline must reconcile ALL prompts into terminal
#    VisibilityResult records (none dropped or missing).
# =====================================================================
@pytest.mark.asyncio
async def test_regression_deadline_persists_all_pending_prompts(test_db_session):
    """
    REGRESSION TEST:
    When a scan reaches its deadline, all remaining pending tasks MUST be persisted
    as terminal VisibilityResult records (e.g. execution_status='timeout' or 'error'),
    so that total persisted results equals prompts_selected, and counts reconcile.
    """
    brand, _, prompts = await create_test_brand_and_candidates(test_db_session, count=5)

    async def hanging_query(prompt, model_name=None, **kwargs):
        # First prompt finishes quickly; other 4 hang indefinitely
        if "1" in prompt:
            return ProviderResponse(
                text="HubSpot is an excellent all-in-one CRM for sales teams.",
                provider="mock",
                model_name="mock-v1",
                is_success=True,
                tokens_used=42
            )
        await asyncio.sleep(60.0)
        return ProviderResponse(text="Late", provider="mock", model_name="mock-v1", is_success=True)

    mock_prov = MagicMock(spec=AIModelProvider)
    mock_prov.provider_name = "mock"
    mock_prov.default_model = "mock-v1"
    mock_prov.query = AsyncMock(side_effect=hanging_query)

    with patch("app.evaluator.service.get_evaluator_provider", return_value=mock_prov):
        scan = await VisibilityEvaluatorService.create_scan(
            brand_id=brand.id,
            prompt_ids=[p.id for p in prompts],
            provider="mock",
            db=test_db_session
        )
        # Execute scan with a tight 0.3s deadline
        await VisibilityEvaluatorService.execute_scan(
            scan.id,
            db=test_db_session,
            scan_timeout_seconds=0.3
        )
        await test_db_session.refresh(scan)

        # 1. Scan must be finished in a terminal state
        assert scan.status in ("completed_with_errors", "failed")

        # 2. Query ALL visibility_results for this scan
        stmt = select(VisibilityResult).where(VisibilityResult.scan_id == scan.id)
        res = await test_db_session.execute(stmt)
        results = res.scalars().all()

        # CRITICAL ASSERTION: All 5 prompts must have a VisibilityResult row!
        # On unpatched code, this FAILS because cancelled tasks are dropped without being saved!
        assert len(results) == len(prompts), (
            f"Expected {len(prompts)} VisibilityResult rows, but got {len(results)}. "
            f"The remaining {len(prompts) - len(results)} prompts were dropped at timeout!"
        )

        # 3. Check count reconciliation
        assert scan.prompts_completed + scan.prompts_failed == scan.prompts_selected
        assert scan.prompts_completed == 1
        assert scan.prompts_failed == 4

        # 4. Check timed-out prompt statuses
        timed_out_results = [r for r in results if r.prompt_id != prompts[0].id]
        for r in timed_out_results:
            assert r.execution_status in ("timeout", "error")
            assert not r.brand_mentioned
            assert r.recommendation_status == "unknown"
            assert "timeout" in (r.error_details or "").lower() or "deadline" in (r.error_details or "").lower() or "cancelled" in (r.error_details or "").lower()


# =====================================================================
# 2. Regression: Provider errors must have distinct execution status
#    and never be scored or displayed as valid NOT MENTIONED.
# =====================================================================
@pytest.mark.asyncio
async def test_regression_error_not_marked_valid_not_mentioned(test_db_session):
    """
    REGRESSION TEST:
    A prompt that failed due to provider 503 or network error must have
    execution_status='error' and must be clearly distinguishable from a valid
    non-empty response where the brand was absent (NOT MENTIONED).
    """
    brand, _, prompts = await create_test_brand_and_candidates(test_db_session, count=2)

    async def mock_error_and_absent(prompt, model_name=None, **kwargs):
        if "1" in prompt:
            # Valid response that discusses Salesforce without mentioning HubSpot
            return ProviderResponse(
                text="Salesforce Sales Cloud is popular for enterprise CRM workflows.",
                provider="mock",
                model_name="mock-v1",
                is_success=True,
                tokens_used=35
            )
        # HTTP 503 error
        return ProviderResponse(
            text="",
            provider="mock",
            model_name="mock-v1",
            is_success=False,
            is_retryable=False,
            error_message="Gemini API returned HTTP 503: Model experiencing high demand."
        )

    mock_prov = MagicMock(spec=AIModelProvider)
    mock_prov.provider_name = "mock"
    mock_prov.default_model = "mock-v1"
    mock_prov.query = AsyncMock(side_effect=mock_error_and_absent)

    with patch("app.evaluator.service.get_evaluator_provider", return_value=mock_prov):
        scan = await VisibilityEvaluatorService.create_scan(
            brand_id=brand.id,
            prompt_ids=[prompts[0].id, prompts[1].id],
            provider="mock",
            db=test_db_session
        )
        await VisibilityEvaluatorService.execute_scan(scan.id, db=test_db_session)
        await test_db_session.refresh(scan)

        stmt = select(VisibilityResult).where(VisibilityResult.scan_id == scan.id)
        res = await test_db_session.execute(stmt)
        results = {r.prompt_id: r for r in res.scalars().all()}

        # Prompt 1: Valid response, brand absent -> valid NOT MENTIONED
        res1 = results[prompts[0].id]
        assert res1.execution_status == "success"
        assert res1.brand_mentioned is False
        assert len(res1.raw_response_text) > 0

        # Prompt 2: Provider error -> execution_status MUST be 'error', error_details populated
        res2 = results[prompts[1].id]
        assert res2.execution_status == "error"
        assert res2.brand_mentioned is False
        assert "503" in (res2.error_details or "")
        assert res2.raw_response_text == ""


# =====================================================================
# 3. Regression: Empty/whitespace response in VisibilityResponseEvaluator
#    must return recommendation_status='unknown' and comparative_position='unknown',
#    NEVER 'not_mentioned'.
# =====================================================================
def test_evaluator_empty_response_is_not_labeled_not_mentioned():
    """
    NOT MENTIONED is valid ONLY when a nonempty successful response was received
    and the target brand is absent. Empty or missing responses must be marked 'unknown'.
    """
    from app.evaluator.evaluator import VisibilityResponseEvaluator

    for empty_input in ["", "   ", "\n\t"]:
        eval_res = VisibilityResponseEvaluator.evaluate(
            response_text=empty_input,
            brand_name="HubSpot",
            brand_domain="hubspot.com"
        )
        assert eval_res.brand_mentioned is False
        assert eval_res.recommendation_status == "unknown", (
            f"Expected 'unknown' for empty response, got '{eval_res.recommendation_status}'"
        )
        assert eval_res.comparative_position == "unknown", (
            f"Expected 'unknown' for empty response, got '{eval_res.comparative_position}'"
        )


# =====================================================================
# 4. Regression: Rate limiter parameters and retry pacing
# =====================================================================
def test_rate_limiter_governs_combined_workers_at_safe_rpm():
    """
    Enforce a shared limit of <= 12 RPM (at least 5.0s min interval)
    across all workers to prevent exceeding Google AI Studio free tier limits.
    """
    from app.evaluator.service import get_provider_rate_limiter

    limiter = get_provider_rate_limiter("gemini")
    assert limiter is not None
    assert limiter.max_requests <= 12, f"Expected max_requests <= 12, got {limiter.max_requests}"
    assert limiter.min_interval >= 5.0, f"Expected min_interval >= 5.0, got {limiter.min_interval}"

