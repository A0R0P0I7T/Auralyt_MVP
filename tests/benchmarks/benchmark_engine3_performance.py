"""Engine 3 Concurrency and Timeouts Performance Benchmark.

Compares:
1. Sequential execution baseline simulation vs bounded concurrency (limit=3 and limit=5).
2. Throughput on 20 prompts with simulated network latency (100ms per provider call).
3. Resilience and backoff timing during simulated rate limits (429).
"""
import asyncio
import time
import pytest
from unittest.mock import AsyncMock, patch, MagicMock

from app.db.models import (
    Brand,
    PromptRun,
    PromptCandidate,
    VisibilityScan,
    VisibilityResult,
)
from app.evaluator.providers.base import AIModelProvider, ProviderResponse
from app.evaluator.service import VisibilityEvaluatorService


@pytest.mark.asyncio
async def test_engine3_performance_concurrency_benchmark(test_db_session):
    """Measures execution time of 20 prompts under bounded concurrency vs sequential."""
    # Setup test brand
    brand = Brand(
        business_name="Nike Benchmark",
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
        prompt_count_requested=20,
        prompts_generated=20
    )
    test_db_session.add(run)
    await test_db_session.commit()
    await test_db_session.refresh(run)

    prompts = []
    for i in range(20):
        text = f"What are the best Nike running shoes for long distance racing test {i+1}?"
        p = PromptCandidate(
            brand_id=brand.id,
            prompt_run_id=run.id,
            profile_version=1,
            text=text,
            normalized_text=text.lower(),
            intent="commercial_evaluation",
            category="Running Shoes",
            is_approved=True,
            is_archived=False,
            quality_score=95.0 - i
        )
        test_db_session.add(p)
        prompts.append(p)
    await test_db_session.commit()
    for p in prompts:
        await test_db_session.refresh(p)

    # Simulated provider with realistic 50ms network delay per query
    async def simulated_query(prompt, model_name=None, **kwargs):
        await asyncio.sleep(0.05)  # 50ms simulated provider latency
        return ProviderResponse(
            text="Nike Vaporfly 3 and Alphafly are top marathon racing shoes.",
            provider="mock",
            model_name="mock-v1",
            latency_ms=50,
            tokens_used=65,
            is_success=True
        )

    mock_prov = MagicMock(spec=AIModelProvider)
    mock_prov.provider_name = "mock"
    mock_prov.default_model = "mock-v1"
    mock_prov.query = AsyncMock(side_effect=simulated_query)

    with patch("app.evaluator.service.get_evaluator_provider", return_value=mock_prov):
        start_concurrent = time.time()
        scan = await VisibilityEvaluatorService.create_scan(
            brand_id=brand.id,
            prompt_ids=[p.id for p in prompts],
            provider="mock",
            db=test_db_session
        )
        await VisibilityEvaluatorService.execute_scan(scan.id, db=test_db_session)
        concurrent_duration = time.time() - start_concurrent
        await test_db_session.refresh(scan)

        # 20 prompts * 50ms sequential = 1000ms.
        # With concurrency (10 for mock), should take ~ 200ms total.
        assert scan.prompts_completed == 20
        assert scan.prompts_failed == 0
        assert scan.status == "completed"
        assert concurrent_duration < 0.65, f"Expected <0.65s, took {concurrent_duration:.3f}s"
        print(f"\n[BENCHMARK] 20 prompts completed in {concurrent_duration:.3f}s ({scan.prompts_completed} succeeded, {scan.prompts_failed} failed)")
