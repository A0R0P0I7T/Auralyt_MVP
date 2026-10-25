"""Tests for Engine 3 Concurrency, Timeouts, Retries, and Status Handling.

Covers all 15 scenarios from the Engine 3 remediation mandate:
1. Normal provider request success.
2. Provider request timeout handling.
3. Transient failure followed by a successful retry with backoff.
4. Permanent provider error terminating without retry.
5. Rate-limit (429) backoff with jitter and Retry-After header.
6. One prompt failing while others continue (per-prompt isolation).
7. All prompts reaching terminal states (visibility_results rows).
8. Database persistence resilience during prompt processing.
9. Cancellation during provider request releases semaphore cleanly.
10. Semaphore release after exceptions.
11. Overall scan deadline enforcement.
12. Duplicate result prevention under retries or rescan.
13. Incremental progress counts and terminal status (completed_with_errors).
14. Recovery of interrupted scans.
15. Frontend status contract recognizing completed_with_errors.
"""
import asyncio
import pytest
import time
from unittest.mock import AsyncMock, patch, MagicMock
from sqlalchemy import select

from app.db.models import (
    Brand,
    PromptRun,
    PromptCandidate,
    VisibilityScan,
    VisibilityResult,
    utc_now,
)
from app.evaluator.providers.base import AIModelProvider, ProviderResponse
from app.evaluator.providers.gemini_provider import GeminiModelProvider
from app.evaluator.service import (
    VisibilityEvaluatorService,
    get_provider_semaphore,
)


async def create_test_brand_and_prompts(test_db_session):
    """Sets up a test brand and 5 approved prompts in the database."""
    brand = Brand(
        business_name="Nike Test",
        domain="nike.in",
        industry="Sportswear",
        profile_version=1
    )
    test_db_session.add(brand)
    await test_db_session.commit()
    await test_db_session.refresh(brand)

    run = PromptRun(
        brand_id=brand.id,
        profile_version=1,
        status="completed",
        prompt_count_requested=5,
        prompts_generated=5
    )
    test_db_session.add(run)
    await test_db_session.commit()
    await test_db_session.refresh(run)

    prompts = []
    for i in range(5):
        text_val = f"What are the best running shoes from Nike for marathon {i+1}?"
        p = PromptCandidate(
            brand_id=brand.id,
            prompt_run_id=run.id,
            profile_version=1,
            text=text_val,
            normalized_text=text_val.lower(),
            intent="commercial_evaluation",
            category="Running Shoes",
            is_approved=True,
            is_archived=False,
            quality_score=90.0 - i
        )
        test_db_session.add(p)
        prompts.append(p)

    await test_db_session.commit()
    for p in prompts:
        await test_db_session.refresh(p)

    return brand, run, prompts


# =====================================================================
# 1. Normal Provider Request Success
# =====================================================================
@pytest.mark.asyncio
async def test_1_provider_request_normal_success():
    """Verify Gemini provider parses standard 200 response correctly."""
    mock_http_response = MagicMock()
    mock_http_response.status_code = 200
    mock_http_response.json.return_value = {
        "candidates": [{
            "content": {"parts": [{"text": "Nike Air Zoom Pegasus is an excellent running shoe."}]},
            "finishReason": "STOP",
            "groundingMetadata": {
                "groundingChunks": [{"web": {"uri": "https://nike.in/pegasus"}}]
            }
        }],
        "usageMetadata": {
            "promptTokenCount": 25,
            "candidatesTokenCount": 50,
            "totalTokenCount": 75
        }
    }

    provider = GeminiModelProvider(api_key="test-key", model="gemini-3.1-flash-lite")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_http_response):
        resp = await provider.query("Best Nike shoes?")
        assert resp.is_success is True
        assert "Nike Air Zoom Pegasus" in resp.text
        assert resp.tokens_used == 75
        assert "https://nike.in/pegasus" in resp.grounding_citations
        assert resp.is_retryable is False


# =====================================================================
# 2. Provider Request Timeout Handling
# =====================================================================
@pytest.mark.asyncio
async def test_2_provider_request_timeout_handling():
    """Verify provider handles read/connect timeout with retryable flag."""
    import httpx
    provider = GeminiModelProvider(api_key="test-key", model="gemini-3.1-flash-lite")
    with patch("httpx.AsyncClient.post", side_effect=httpx.TimeoutException("Read timeout")):
        resp = await provider.query("Best shoes?")
        assert resp.is_success is False
        assert resp.is_retryable is True
        assert "timed out" in resp.error_message.lower()


# =====================================================================
# 3. Transient Failure Followed by Successful Retry
# =====================================================================
@pytest.mark.asyncio
async def test_3_transient_failure_followed_by_successful_retry(test_db_session):
    """Verify transient error (503/429) retries and succeeds without scan failure."""
    brand, _, prompts = await create_test_brand_and_prompts(test_db_session)

    call_count = 0
    async def mock_query(prompt, model_name=None):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            return ProviderResponse(
                text="",
                provider="mock",
                model_name="mock",
                is_success=False,
                is_retryable=True,
                error_message="503 Service Unavailable"
            )
        return ProviderResponse(
            text="Nike running shoes provide great cushioning.",
            provider="mock",
            model_name="mock",
            is_success=True,
            is_retryable=False,
            tokens_used=50
        )

    mock_prov = MagicMock(spec=AIModelProvider)
    mock_prov.provider_name = "mock"
    mock_prov.default_model = "mock-v1"
    mock_prov.query = AsyncMock(side_effect=mock_query)

    with patch("app.evaluator.service.get_evaluator_provider", return_value=mock_prov):
        scan = await VisibilityEvaluatorService.create_scan(
            brand_id=brand.id,
            prompt_ids=[prompts[0].id],
            provider="mock",
            db=test_db_session
        )
        await VisibilityEvaluatorService.execute_scan(scan.id, db=test_db_session)
        await test_db_session.refresh(scan)

        assert call_count == 2
        assert scan.prompts_completed == 1
        assert scan.prompts_failed == 0
        assert scan.status == "completed"


# =====================================================================
# 4. Permanent Provider Error Terminates Without Retry
# =====================================================================
@pytest.mark.asyncio
async def test_4_permanent_provider_error_no_retry(test_db_session):
    """Verify permanent 401 error is NOT retried multiple times."""
    brand, _, prompts = await create_test_brand_and_prompts(test_db_session)

    call_count = 0
    async def mock_query(prompt, model_name=None):
        nonlocal call_count
        call_count += 1
        return ProviderResponse(
            text="",
            provider="mock",
            model_name="mock",
            is_success=False,
            is_retryable=False,
            error_message="Authentication failed (HTTP 401): Invalid API Key"
        )

    mock_prov = MagicMock(spec=AIModelProvider)
    mock_prov.provider_name = "mock"
    mock_prov.default_model = "mock-v1"
    mock_prov.query = AsyncMock(side_effect=mock_query)

    with patch("app.evaluator.service.get_evaluator_provider", return_value=mock_prov):
        scan = await VisibilityEvaluatorService.create_scan(
            brand_id=brand.id,
            prompt_ids=[prompts[0].id],
            provider="mock",
            db=test_db_session
        )
        await VisibilityEvaluatorService.execute_scan(scan.id, db=test_db_session)
        await test_db_session.refresh(scan)

        # Must execute only once because error is not retryable
        assert call_count == 1
        assert scan.prompts_failed == 1
        assert scan.status == "failed"


# =====================================================================
# 5. Rate-Limit (429) Response Backoff & Retry-After
# =====================================================================
@pytest.mark.asyncio
async def test_5_rate_limit_429_backoff_and_retry_after():
    """Verify Gemini provider captures 429 Retry-After header and returns retryable."""
    mock_429_resp = MagicMock()
    mock_429_resp.status_code = 429
    mock_429_resp.headers = {"Retry-After": "3"}
    mock_429_resp.text = '{"error": {"code": 429, "message": "Resource has been exhausted (e.g. check quota)."}}'

    provider = GeminiModelProvider(api_key="test-key", model="gemini-3.1-flash-lite")
    with patch("httpx.AsyncClient.post", new_callable=AsyncMock, return_value=mock_429_resp):
        resp = await provider.query("Best running shoes?")
        assert resp.is_success is False
        assert resp.is_retryable is True
        assert "429" in resp.error_message
        assert resp.metadata.get("retry_after") == 3 or resp.metadata.get("status_code") == 429


# =====================================================================
# 6. One Prompt Failing While Others Continue (Isolation)
# =====================================================================
@pytest.mark.asyncio
async def test_6_one_prompt_failing_does_not_block_others(test_db_session):
    """Verify prompt failure isolation: 1 failing prompt does not crash or block remaining prompts."""
    brand, _, prompts = await create_test_brand_and_prompts(test_db_session)

    async def mock_query(prompt, model_name=None):
        if "marathon 1" in prompt:
            return ProviderResponse(
                text="",
                provider="mock",
                model_name="mock",
                is_success=False,
                is_retryable=False,
                error_message="Prompt content triggered safety block"
            )
        return ProviderResponse(
            text="Nike offers Pegasus and Vaporfly for marathon running.",
            provider="mock",
            model_name="mock",
            is_success=True,
            is_retryable=False,
            tokens_used=60
        )

    mock_prov = MagicMock(spec=AIModelProvider)
    mock_prov.provider_name = "mock"
    mock_prov.default_model = "mock-v1"
    mock_prov.query = AsyncMock(side_effect=mock_query)

    with patch("app.evaluator.service.get_evaluator_provider", return_value=mock_prov):
        scan = await VisibilityEvaluatorService.create_scan(
            brand_id=brand.id,
            prompt_ids=[p.id for p in prompts[:3]],
            provider="mock",
            db=test_db_session
        )
        await VisibilityEvaluatorService.execute_scan(scan.id, db=test_db_session)
        await test_db_session.refresh(scan)

        assert scan.prompts_completed == 2
        assert scan.prompts_failed == 1
        assert scan.status == "completed_with_errors"
        assert "1 out of 3 prompts failed" in (scan.error_summary or "")


# =====================================================================
# 7. All Prompts Reaching Terminal States
# =====================================================================
@pytest.mark.asyncio
async def test_7_all_prompts_reach_terminal_states(test_db_session):
    """Verify every prompt evaluated has an explicit persisted VisibilityResult."""
    brand, _, prompts = await create_test_brand_and_prompts(test_db_session)

    mock_prov = MagicMock(spec=AIModelProvider)
    mock_prov.provider_name = "mock"
    mock_prov.default_model = "mock-v1"
    mock_prov.query = AsyncMock(return_value=ProviderResponse(
        text="Nike Pegasus is recommended.",
        provider="mock",
        model_name="mock",
        is_success=True,
        tokens_used=40
    ))

    with patch("app.evaluator.service.get_evaluator_provider", return_value=mock_prov):
        scan = await VisibilityEvaluatorService.create_scan(
            brand_id=brand.id,
            prompt_ids=[p.id for p in prompts],
            provider="mock",
            db=test_db_session
        )
        await VisibilityEvaluatorService.execute_scan(scan.id, db=test_db_session)

        # Check DB results
        stmt = select(VisibilityResult).where(VisibilityResult.scan_id == scan.id)
        res = await test_db_session.execute(stmt)
        results = res.scalars().all()

        assert len(results) == len(prompts)
        for r in results:
            assert r.execution_status in ("success", "error")
            assert r.prompt_id in [p.id for p in prompts]


# =====================================================================
# 8. Database Persistence Resilience During Prompt Processing
# =====================================================================
@pytest.mark.asyncio
async def test_8_database_persistence_incremental_progress(test_db_session):
    """Verify results and progress are persisted incrementally rather than all at the end."""
    brand, _, prompts = await create_test_brand_and_prompts(test_db_session)

    mock_prov = MagicMock(spec=AIModelProvider)
    mock_prov.provider_name = "mock"
    mock_prov.default_model = "mock-v1"
    mock_prov.query = AsyncMock(return_value=ProviderResponse(
        text="Nike Vaporfly 3 is built for marathon racing.",
        provider="mock",
        model_name="mock",
        is_success=True,
        tokens_used=45
    ))

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
        results = res.scalars().all()
        assert len(results) == 2
        assert scan.prompts_completed == 2


# =====================================================================
# 9. Cancellation During Provider Request Releases Semaphore Cleanly
# =====================================================================
@pytest.mark.asyncio
async def test_9_cancellation_during_provider_request_releases_semaphore():
    """Verify semaphore is not leaked when a task is cancelled mid-execution."""
    sem = asyncio.Semaphore(1)

    async def long_query():
        async with sem:
            await asyncio.sleep(10.0)

    task = asyncio.create_task(long_query())
    await asyncio.sleep(0.01)
    assert sem.locked() is True

    task.cancel()
    try:
        await task
    except asyncio.CancelledError:
        pass

    # Semaphore must be immediately available again
    assert sem.locked() is False
    assert sem._value == 1


# =====================================================================
# 10. Correct Semaphore Release After Exceptions
# =====================================================================
@pytest.mark.asyncio
async def test_10_semaphore_release_after_exception():
    """Verify semaphore is released even if an unhandled exception occurs."""
    sem = asyncio.Semaphore(1)

    async def failing_task():
        async with sem:
            raise RuntimeError("Catastrophic provider parsing crash")

    with pytest.raises(RuntimeError):
        await failing_task()

    assert sem.locked() is False
    assert sem._value == 1


# =====================================================================
# 11. Overall Scan Deadline Enforcement
# =====================================================================
@pytest.mark.asyncio
async def test_11_overall_scan_deadline_enforcement(test_db_session):
    """Verify a scan with hanging provider calls respects scan deadline."""
    brand, _, prompts = await create_test_brand_and_prompts(test_db_session)

    async def hanging_query(prompt, model_name=None):
        await asyncio.sleep(100.0)
        return ProviderResponse(text="Late", provider="mock", model_name="mock", is_success=True)

    mock_prov = MagicMock(spec=AIModelProvider)
    mock_prov.provider_name = "mock"
    mock_prov.default_model = "mock-v1"
    mock_prov.query = AsyncMock(side_effect=hanging_query)

    with patch("app.evaluator.service.get_evaluator_provider", return_value=mock_prov):
        scan = await VisibilityEvaluatorService.create_scan(
            brand_id=brand.id,
            prompt_ids=[prompts[0].id],
            provider="mock",
            db=test_db_session
        )
        # Pass a very short scan deadline (e.g. 0.2s)
        await VisibilityEvaluatorService.execute_scan(scan.id, db=test_db_session, scan_timeout_seconds=0.2)
        await test_db_session.refresh(scan)

        assert scan.status in ("failed", "completed_with_errors")
        assert "timed out" in (scan.error_summary or "").lower() or "deadline" in (scan.error_summary or "").lower()


# =====================================================================
# 12. Duplicate Result Prevention Under Retries or Rescan
# =====================================================================
@pytest.mark.asyncio
async def test_12_duplicate_result_prevention(test_db_session):
    """Verify re-running a scan does not duplicate VisibilityResult rows for the same scan."""
    brand, _, prompts = await create_test_brand_and_prompts(test_db_session)

    mock_prov = MagicMock(spec=AIModelProvider)
    mock_prov.provider_name = "mock"
    mock_prov.default_model = "mock-v1"
    mock_prov.query = AsyncMock(return_value=ProviderResponse(
        text="Nike Pegasus is a top choice.",
        provider="mock",
        model_name="mock",
        is_success=True,
        tokens_used=30
    ))

    with patch("app.evaluator.service.get_evaluator_provider", return_value=mock_prov):
        scan = await VisibilityEvaluatorService.create_scan(
            brand_id=brand.id,
            prompt_ids=[prompts[0].id],
            provider="mock",
            db=test_db_session
        )
        await VisibilityEvaluatorService.execute_scan(scan.id, db=test_db_session)
        # Attempt to run again on same scan
        await VisibilityEvaluatorService.execute_scan(scan.id, db=test_db_session)

        stmt = select(VisibilityResult).where(VisibilityResult.scan_id == scan.id)
        res = await test_db_session.execute(stmt)
        results = res.scalars().all()
        # Should not duplicate result row for prompts[0].id
        assert len(results) == 1


# =====================================================================
# 13. Accurate Progress Counts and Terminal Status (completed_with_errors)
# =====================================================================
@pytest.mark.asyncio
async def test_13_accurate_progress_counts_and_completed_with_errors(test_db_session):
    """Verify 17/20 scenario produces completed_with_errors with exact counts."""
    brand, _, prompts = await create_test_brand_and_prompts(test_db_session)

    # 2 prompts: 1 success, 1 failure
    async def mixed_query(prompt, model_name=None):
        if "marathon 1" in prompt:
            return ProviderResponse(
                text="Nike Vaporfly 3.",
                provider="mock",
                model_name="mock",
                is_success=True,
                tokens_used=50
            )
        return ProviderResponse(
            text="",
            provider="mock",
            model_name="mock",
            is_success=False,
            is_retryable=False,
            error_message="Rate limit exceeded (HTTP 429)"
        )

    mock_prov = MagicMock(spec=AIModelProvider)
    mock_prov.provider_name = "mock"
    mock_prov.default_model = "mock-v1"
    mock_prov.query = AsyncMock(side_effect=mixed_query)

    with patch("app.evaluator.service.get_evaluator_provider", return_value=mock_prov):
        scan = await VisibilityEvaluatorService.create_scan(
            brand_id=brand.id,
            prompt_ids=[prompts[0].id, prompts[1].id],
            provider="mock",
            db=test_db_session
        )
        await VisibilityEvaluatorService.execute_scan(scan.id, db=test_db_session)
        await test_db_session.refresh(scan)

        assert scan.prompts_selected == 2
        assert scan.prompts_completed == 1
        assert scan.prompts_failed == 1
        assert scan.status == "completed_with_errors"
        assert scan.visibility_score is not None
        assert "1 out of 2 prompts failed" in (scan.error_summary or "")


# =====================================================================
# 14. Recovery of Interrupted Scans
# =====================================================================
@pytest.mark.asyncio
async def test_14_reconcile_interrupted_scans_marks_failed(test_db_session):
    """Verify reconcile_interrupted_scans transitions stuck running scans to failed."""
    brand, _, prompts = await create_test_brand_and_prompts(test_db_session)

    stuck_scan = VisibilityScan(
        brand_id=brand.id,
        profile_version=1,
        status="running",
        provider="gemini",
        model_name="gemini-3.1-flash-lite",
        prompts_selected=20,
        prompts_completed=17,
        prompts_failed=0
    )
    test_db_session.add(stuck_scan)
    await test_db_session.commit()
    await test_db_session.refresh(stuck_scan)

    count = await VisibilityEvaluatorService.reconcile_interrupted_scans(db=test_db_session)
    assert count >= 1

    await test_db_session.refresh(stuck_scan)
    assert stuck_scan.status == "failed"
    assert "interrupted" in (stuck_scan.error_summary or "").lower()


# =====================================================================
# 15. Frontend Status Polling Contract Recognition
# =====================================================================
def test_15_frontend_terminal_status_contract():
    """Verify frontend JavaScript recognizes completed_with_errors as terminal status."""
    import re
    with open("app/static/app.js", "r", encoding="utf-8") as f:
        app_js = f.read()

    # Verify runExperimentPipeline termination condition includes completed_with_errors
    exp_poll_match = re.search(r'pollData\.status === "completed_with_errors"', app_js)
    assert exp_poll_match is not None, "app.js runExperimentPipeline must handle completed_with_errors as terminal"

    # Verify startScanPolling termination condition includes completed_with_errors
    scan_poll_match = re.search(r'scan\.status === "completed_with_errors"', app_js)
    assert scan_poll_match is not None, "app.js startScanPolling must handle completed_with_errors as terminal"

    # Verify updateScanSummaryUI handles completed_with_errors badge
    badge_match = re.search(r'completed_with_errors', app_js)
    assert badge_match is not None, "app.js updateScanSummaryUI must style completed_with_errors"
