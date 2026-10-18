"""Tests for Organic, Unbranded Prompt Generation (Engine 2) and Visibility Intelligence (Engine 3)."""
import pytest
import pytest_asyncio
import re
from httpx import AsyncClient

from app.db.models import Brand, ProfileRun, BrandFact
from app.prompts.normalizer import ProfileNormalizer
from app.prompts.planner import CoveragePlanner
from app.prompts.generator import DeterministicGenerator
from app.prompts.validator import PromptValidator
from app.prompts.scorer import PromptScorer
from app.prompts.service import PromptIntelligenceService
from app.evaluator.service import VisibilityEvaluatorService


@pytest_asyncio.fixture
async def openrouter_brand(test_db_session, test_org):
    """Fixture providing an onboarded OpenRouter brand profile."""
    brand = Brand(
        domain="openrouter.ai",
        business_name="OpenRouter",
        industry="Unified LLM API & Model Routing",
        target_market="Global",
        language="en",
        organization_id=test_org.id,
        profile_version=1,
    )
    test_db_session.add(brand)
    await test_db_session.flush()

    run = ProfileRun(
        brand_id=brand.id,
        status="completed",
        page_limit=10,
        pages_discovered=5,
        pages_succeeded=5,
    )
    test_db_session.add(run)
    await test_db_session.flush()

    facts = [
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="business_overview",
            fact_value={"description": "Unified API gateway offering flexible model routing and competitive pricing across multiple AI models."},
            confidence=0.95,
            user_confirmed=True,
            source_url="https://openrouter.ai/about",
            evidence_snippet="OpenRouter provides a unified interface for routing requests across 100+ large language models.",
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="product_service",
            fact_value={"name": "Unified LLM Gateway"},
            confidence=0.90,
            user_confirmed=True,
            source_url="https://openrouter.ai/docs",
            evidence_snippet="Access all major large language models through a single OpenAI-compatible API endpoint.",
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="target_audience",
            fact_value={"segment": "AI Developers and Engineering Teams"},
            confidence=0.88,
            user_confirmed=True,
            source_url="https://openrouter.ai/solutions",
            evidence_snippet="Built for software engineers integrating multiple LLMs into production applications.",
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="use_case",
            fact_value={"title": "switching between language models with unified routing"},
            confidence=0.92,
            user_confirmed=True,
            source_url="https://openrouter.ai/use-cases",
            evidence_snippet="Allows teams to switch models dynamically and fall back when one provider is down.",
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="pricing",
            fact_value={"model": "Usage-Based Pay Per Token with No Monthly Fees"},
            confidence=0.89,
            user_confirmed=True,
            source_url="https://openrouter.ai/pricing",
            evidence_snippet="Transparent per-token pricing with zero platform markups and pay-as-you-go billing.",
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="differentiator",
            fact_value={"claim": "Real-time cost and latency comparison across leading AI providers"},
            confidence=0.91,
            user_confirmed=True,
            source_url="https://openrouter.ai/features",
            evidence_snippet="Provides real-time analytics to compare model latency, uptime, and pricing.",
        ),
    ]
    test_db_session.add_all(facts)
    await test_db_session.commit()
    await test_db_session.refresh(brand)
    return brand


@pytest_asyncio.fixture
async def nike_brand(test_db_session, test_org):
    """Fixture providing an onboarded Nike brand profile."""
    brand = Brand(
        domain="nike.com",
        business_name="Nike",
        industry="Athletic Footwear & Running Shoes",
        target_market="Global",
        language="en",
        organization_id=test_org.id,
        profile_version=1,
    )
    test_db_session.add(brand)
    await test_db_session.flush()

    run = ProfileRun(
        brand_id=brand.id,
        status="completed",
        page_limit=10,
        pages_discovered=5,
        pages_succeeded=5,
    )
    test_db_session.add(run)
    await test_db_session.flush()

    facts = [
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="business_overview",
            fact_value={"description": "Global designer of high-performance running shoes and athletic sportswear."},
            confidence=0.95,
            user_confirmed=True,
            source_url="https://nike.com/about",
            evidence_snippet="Nike innovates athletic footwear for marathon runners and everyday athletes.",
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="product_service",
            fact_value={"name": "Marathon Training Running Shoes"},
            confidence=0.90,
            user_confirmed=True,
            source_url="https://nike.com/running",
            evidence_snippet="High-cushion road running shoes engineered for distance training.",
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="target_audience",
            fact_value={"segment": "Marathon Runners and Fitness Enthusiasts"},
            confidence=0.88,
            user_confirmed=True,
            source_url="https://nike.com/community",
            evidence_snippet="Designed for marathon runners, sprinters, and everyday fitness walkers.",
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="use_case",
            fact_value={"title": "long-distance road race training"},
            confidence=0.92,
            user_confirmed=True,
            source_url="https://nike.com/training",
            evidence_snippet="Maximizes energy return during long-distance marathon preparation.",
        ),
    ]
    test_db_session.add_all(facts)
    await test_db_session.commit()
    await test_db_session.refresh(brand)
    return brand


@pytest.mark.asyncio
async def test_openrouter_organic_prompts_contain_no_brand_leakage(client: AsyncClient, openrouter_brand):
    """Verify Engine 2 generates 20 organic prompts for OpenRouter with ZERO brand mentions."""
    res = await client.post(
        f"/api/brands/{openrouter_brand.id}/prompts/generate",
        json={"prompt_count": 20, "force_regenerate": True}
    )
    assert res.status_code == 202
    data = res.json()
    assert data["prompts_generated"] == 20

    prompts_res = await client.get(f"/api/brands/{openrouter_brand.id}/prompts?page_size=30")
    assert prompts_res.status_code == 200
    items = prompts_res.json()["items"]
    assert len(items) == 20

    forbidden_tokens = ["openrouter", "openrouter.ai"]
    for prompt in items:
        text = prompt["text"].lower()
        for token in forbidden_tokens:
            assert token not in text, f"Brand leakage found in prompt: '{prompt['text']}'"

        # Must be natural question / query
        assert text.endswith("?") or any(text.startswith(w) for w in ("what", "which", "how", "top", "best"))


@pytest.mark.asyncio
async def test_nike_organic_prompts_contain_no_brand_leakage(client: AsyncClient, nike_brand):
    """Verify Engine 2 generates organic prompts for Nike with ZERO mentions of Nike or nike.com."""
    res = await client.post(
        f"/api/brands/{nike_brand.id}/prompts/generate",
        json={"prompt_count": 20, "force_regenerate": True}
    )
    assert res.status_code == 202
    data = res.json()
    assert data["prompts_generated"] == 20

    prompts_res = await client.get(f"/api/brands/{nike_brand.id}/prompts?page_size=30")
    assert prompts_res.status_code == 200
    items = prompts_res.json()["items"]
    assert len(items) == 20

    for prompt in items:
        text = prompt["text"].lower()
        assert "nike" not in text, f"Brand leakage found in prompt: '{prompt['text']}'"
        assert "nike.com" not in text


@pytest.mark.asyncio
async def test_prompt_validator_rejects_brand_leakage():
    """Verify PromptValidator explicitly fails candidates that mention the brand name or domain."""
    from app.prompts.models import GeneratedPromptCandidate, NormalizedBrandProfile

    profile = NormalizedBrandProfile(
        brand_id="b1",
        domain="openrouter.ai",
        business_name="OpenRouter",
        industry="Unified LLM API & Model Routing",
        profile_version=1,
    )

    biased_candidate = GeneratedPromptCandidate(
        text="Is OpenRouter a recommended platform for SaaS?",
        category="recommendations",
        intent="commercial",
        buying_stage="consideration",
    )
    valid, reason = PromptValidator.validate(biased_candidate, profile, reject_brand_mentions=True)
    assert not valid
    assert "brand" in reason.lower()

    organic_candidate = GeneratedPromptCandidate(
        text="What are the best API providers for accessing multiple large language models?",
        category="discovery",
        intent="informational",
        buying_stage="awareness",
    )
    valid_org, reason_org = PromptValidator.validate(organic_candidate, profile)
    assert valid_org, f"Expected organic prompt to be valid, got rejection: {reason_org}"


@pytest.mark.asyncio
async def test_insufficient_profile_returns_clear_error(client: AsyncClient, test_db_session, test_org):
    """Verify attempting to generate prompts on an unprofiled or insufficient brand returns clear error."""
    insufficient_brand = Brand(
        domain="mysterycompany.com",
        business_name="MysteryCompany",
        industry=None,  # No industry
        profile_version=1,
        organization_id=test_org.id
    )
    test_db_session.add(insufficient_brand)
    await test_db_session.commit()

    res = await client.post(
        f"/api/brands/{insufficient_brand.id}/prompts/generate",
        json={"prompt_count": 20}
    )
    assert res.status_code in (400, 422)
    detail = res.json()["detail"].lower()
    assert "insufficient" in detail or "empty" in detail or "profile" in detail


@pytest.mark.asyncio
async def test_organic_prompts_evaluated_by_engine3(client: AsyncClient, openrouter_brand, test_db_session):
    """Verify Engine 3 evaluates organic prompts and detects natural brand appearance in AI answers."""
    # 1. Generate organic prompts
    gen_res = await client.post(
        f"/api/brands/{openrouter_brand.id}/prompts/generate",
        json={"prompt_count": 10, "force_regenerate": True}
    )
    assert gen_res.status_code == 202

    # 2. Trigger Visibility Scan with Mock provider
    scan_res = await client.post(
        f"/api/brands/{openrouter_brand.id}/visibility/scans",
        json={"provider": "mock", "max_prompts": 10, "force_rescan": True}
    )
    scan_data = scan_res.json()
    scan_id = scan_data.get("id") or scan_data.get("scan_id")

    # 3. Execute scan directly
    await VisibilityEvaluatorService.execute_scan(
        scan_id=scan_id,
        db=test_db_session
    )

    # 4. Fetch results
    results_res = await client.get(
        f"/api/brands/{openrouter_brand.id}/visibility/scans/{scan_id}/results"
    )
    assert results_res.status_code == 200
    r_data = results_res.json()
    assert r_data["scan"]["status"] == "completed"
    assert r_data["scan"]["prompts_completed"] == 10
    assert r_data["scan"]["visibility_score"] is not None
    assert r_data["scan"]["mention_rate"] is not None
    # Verify OpenRouter was naturally mentioned in relevant LLM API queries
    assert r_data["scan"]["mention_rate"] > 0.0
