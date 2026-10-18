"""Focused regressions for prompt grounding and visibility validity."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Brand, ProfileRun, PromptCandidate, PromptRun
from app.evaluator.evaluator import VisibilityResponseEvaluator
from app.evaluator.service import VisibilityEvaluatorService
from app.prompts.models import GeneratedPromptCandidate, GroundedFact, NormalizedBrandProfile
from app.prompts.scorer import PromptScorer
from app.prompts.validator import PromptValidator


def _profile() -> NormalizedBrandProfile:
    return NormalizedBrandProfile(
        brand_id="b-1",
        domain="acme.example",
        business_name="Acme",
        industry="SaaS",
        profile_version=7,
        products_and_services=["Acme Flow"],
        facts=[GroundedFact(
            id="fact-product-v7",
            fact_type="product_service",
            fact_value={"name": "Acme Flow"},
            source_url="https://acme.example/products",
            evidence_snippet="Acme Flow automates approvals.",
        )],
    )


def test_prompt_validator_rejects_unknown_or_ungrounded_fact_ids():
    profile = _profile()
    candidate = GeneratedPromptCandidate(
        text="What should I consider before choosing Acme Flow?",
        category="product_evaluation",
        intent="commercial",
        buying_stage="consideration",
        provenance_fact_ids=["not-in-profile"],
    )
    valid, reason = PromptValidator.validate(candidate, profile)
    assert valid is False
    assert "outside the active profile" in reason

    candidate.provenance_fact_ids = []
    valid, reason = PromptValidator.validate(candidate, profile)
    assert valid is False
    assert "requires provenance" in reason


def test_ungrounded_prompt_does_not_receive_high_grounding_score():
    candidate = GeneratedPromptCandidate(
        text="What are the best SaaS tools?",
        category="discovery",
        intent="informational",
        buying_stage="awareness",
    )
    scored = PromptScorer.score_candidate(candidate, _profile(), [])
    assert scored.scores["grounding"] == 0.0


def test_evaluator_separates_provider_and_response_citations_and_parses_url_domain():
    result = VisibilityResponseEvaluator.evaluate(
        response_text="Acme is a neutral mention. See https://third-party.example/review.",
        brand_name="Acme",
        brand_domain="https://acme.example/",
        provider_metadata={"grounding_citations": ["https://grounded.example/source"]},
    )
    assert result.brand_mentioned is True
    assert result.provider_citations == ["https://grounded.example/source"]
    assert result.response_citations == ["https://third-party.example/review"]
    assert set(result.citations) == set(result.provider_citations + result.response_citations)


@pytest.mark.asyncio
async def test_zero_successful_observations_report_unavailable_metrics(
    client: AsyncClient, profiled_brand, test_db_session: AsyncSession
):
    profiled_brand.business_name = "Linear"
    profiled_brand.domain = "linear.app"
    run = PromptRun(brand_id=profiled_brand.id, profile_version=1, status="completed")
    test_db_session.add(run)
    await test_db_session.flush()
    prompt = PromptCandidate(
        brand_id=profiled_brand.id,
        prompt_run_id=run.id,
        profile_version=1,
        text="What is Linear? [SIMULATE_ERROR]",
        normalized_text="what is linear simulate error",
        category="discovery",
        is_approved=True,
    )
    test_db_session.add(prompt)
    await test_db_session.commit()

    response = await client.post(
        f"/api/brands/{profiled_brand.id}/visibility/scans",
        json={"provider": "mock", "force_rescan": True},
    )
    scan_id = response.json()["id"]
    await VisibilityEvaluatorService.execute_scan(scan_id, db=test_db_session)
    result = (await client.get(f"/api/brands/{profiled_brand.id}/visibility/scans/{scan_id}")).json()
    assert result["status"] == "failed"
    assert result["prompts_completed"] == 0
    assert result["mention_rate"] is None
    assert result["recommendation_rate"] is None
    assert result["visibility_score"] is None


@pytest.mark.asyncio
async def test_force_regeneration_does_not_persist_duplicate_prompt_text(
    client: AsyncClient, profiled_brand
):
    first = await client.post(
        f"/api/brands/{profiled_brand.id}/prompts/generate",
        json={"prompt_count": 10, "force_regenerate": True},
    )
    second = await client.post(
        f"/api/brands/{profiled_brand.id}/prompts/generate",
        json={"prompt_count": 10, "force_regenerate": True},
    )
    assert first.json()["prompts_generated"] == 10
    assert second.json()["prompts_generated"] == 10
    prompts = (
        await client.get(f"/api/brands/{profiled_brand.id}/prompts?page_size=50")
    ).json()
    assert prompts["total"] == 10
    assert len({item["text"].casefold() for item in prompts["items"]}) == prompts["total"]


@pytest.mark.asyncio
async def test_prompt_listing_stays_on_last_completed_version_during_refresh(
    client: AsyncClient, profiled_brand, test_db_session: AsyncSession
):
    profiled_brand.profile_version = 2
    pending = ProfileRun(
        brand_id=profiled_brand.id,
        profile_version=2,
        status="pending",
    )
    test_db_session.add(pending)
    await test_db_session.commit()
    response = await client.get(f"/api/brands/{profiled_brand.id}/prompts")
    assert response.json()["profile_version"] == 1
