"""Unit and pipeline tests for Engine 2: Prompt Intelligence."""
import pytest
from app.prompts.models import (
    NormalizedBrandProfile,
    GroundedFact,
    GeneratedPromptCandidate,
)
from app.prompts.normalizer import ProfileNormalizer
from app.prompts.planner import CoveragePlanner
from app.prompts.generator import DeterministicGenerator, GeminiGenerator
from app.prompts.validator import PromptValidator
from app.prompts.scorer import (
    PromptScorer,
    normalize_prompt_text,
    token_jaccard_similarity,
)


@pytest.fixture
def sample_profile_data():
    return {
        "brand": {
            "id": "b-123",
            "domain": "acmecloud.io",
            "business_name": "AcmeCloud",
            "industry": "Edge Computing",
            "target_market": "North America",
            "language": "en",
        },
        "profile_version": 1,
        "business_overview": {
            "description": "High-speed distributed edge computing platform for latency-critical applications."
        },
        "products_and_services": [
            {"name": "EdgeRouter Pro", "description": "Global edge routing engine"},
            {"name": "Serverless Functions", "description": "Sub-millisecond execution runtime"},
        ],
        "target_audience": [
            {"segment": "DevOps Engineers"},
            {"segment": "Fintech Platforms"},
        ],
        "use_cases": [
            {"title": "Low-Latency API Gateway"},
            {"title": "Real-time Fraud Detection"},
        ],
        "pricing_information": [
            {"model": "Usage-Based Pay As You Go"},
            {"model": "Enterprise Reserved Tier"},
        ],
        "differentiators": [
            {"claim": "Zero-cold-start edge containers"},
            {"claim": "Sub-10ms global latency guarantee"},
        ],
        "faqs": [
            {"question": "How fast is deployment?", "answer": "Under 30 seconds globally."}
        ],
        "supported_languages": ["en"],
        "facts": [
            {
                "id": "f-1",
                "fact_type": "product_service",
                "fact_value": {"name": "EdgeRouter Pro"},
                "confidence": 0.95,
                "user_confirmed": True,
                "source_url": "https://acmecloud.io/products",
                "evidence_snippet": "EdgeRouter Pro delivers automated global edge traffic steering.",
            },
            {
                "id": "f-2",
                "fact_type": "pricing",
                "fact_value": {"model": "Usage-Based Pay As You Go"},
                "confidence": 0.90,
                "user_confirmed": False,
                "source_url": "https://acmecloud.io/pricing",
                "evidence_snippet": "Usage-based pricing with transparent metrics.",
            },
        ],
    }


def test_profile_normalizer_complete(sample_profile_data):
    normalized = ProfileNormalizer.normalize(sample_profile_data)
    assert normalized.brand_id == "b-123"
    assert normalized.business_name == "AcmeCloud"
    assert normalized.industry == "Edge Computing"
    assert "EdgeRouter Pro" in normalized.products_and_services
    assert "Serverless Functions" in normalized.products_and_services
    assert "DevOps Engineers" in normalized.target_audiences
    assert "Low-Latency API Gateway" in normalized.use_cases
    assert "Usage-Based Pay As You Go" in normalized.pricing_models
    assert len(normalized.facts) == 2
    assert normalized.is_empty is False


def test_profile_normalizer_empty():
    empty_data = {
        "brand": {"id": "b-empty", "domain": "empty.org", "business_name": "Empty"},
        "profile_version": 1,
        "business_overview": {},
        "products_and_services": [],
        "target_audience": [],
        "use_cases": [],
        "pricing_information": [],
        "differentiators": [],
        "faqs": [],
        "facts": [],
    }
    normalized = ProfileNormalizer.normalize(empty_data)
    assert normalized.is_empty is True


def test_coverage_planner_allocates_slots_proportional(sample_profile_data):
    normalized = ProfileNormalizer.normalize(sample_profile_data)
    plan = CoveragePlanner.create_plan(normalized, requested_count=20)

    assert plan.total_slots_requested == 20
    assert len(plan.slots) == 20
    # Expected rich categories
    assert "product_evaluation" in plan.category_distribution
    assert "audience_specific" in plan.category_distribution
    assert "use_cases" in plan.category_distribution
    assert "pricing_value" in plan.category_distribution
    assert "comparisons" in plan.category_distribution


def test_coverage_planner_skips_missing_dimensions():
    # Profile with NO pricing and NO audience
    sparse_data = {
        "brand": {"id": "b-sparse", "domain": "sparse.io", "business_name": "SparseCorp", "industry": "DevTools"},
        "profile_version": 1,
        "business_overview": {"description": "Developer automation suite."},
        "products_and_services": ["CLI Tool"],
        "target_audience": [],
        "use_cases": [],
        "pricing_information": [],
        "differentiators": ["Open Core Architecture"],
        "facts": [],
    }
    normalized = ProfileNormalizer.normalize(sparse_data)
    plan = CoveragePlanner.create_plan(normalized, requested_count=10)

    # Must NOT force pricing_value or audience_specific
    assert "pricing_value" not in plan.category_distribution
    assert "audience_specific" not in plan.category_distribution
    assert "product_evaluation" in plan.category_distribution
    assert len(plan.slots) == 10


@pytest.mark.asyncio
async def test_deterministic_generator_grounding(sample_profile_data):
    normalized = ProfileNormalizer.normalize(sample_profile_data)
    plan = CoveragePlanner.create_plan(normalized, requested_count=15)
    generator = DeterministicGenerator()
    candidates = await generator.generate(normalized, plan)

    assert len(candidates) == 15
    for c in candidates:
        assert c.text
        assert len(c.text) > 15
        # Must be valid category
        assert c.category in plan.category_distribution


def test_prompt_validator_accepts_valid_prompt(sample_profile_data):
    normalized = ProfileNormalizer.normalize(sample_profile_data)
    valid_cand = GeneratedPromptCandidate(
        text="How does AcmeCloud's EdgeRouter Pro compare with other edge solutions?",
        category="comparisons",
        intent="comparative",
        buying_stage="consideration",
    )
    is_valid, reason = PromptValidator.validate(valid_cand, normalized)
    assert is_valid is True
    assert reason == ""


def test_prompt_validator_rejects_too_short(sample_profile_data):
    normalized = ProfileNormalizer.normalize(sample_profile_data)
    short_cand = GeneratedPromptCandidate(
        text="What is?",
        category="discovery",
        intent="informational",
        buying_stage="awareness",
    )
    is_valid, reason = PromptValidator.validate(short_cand, normalized)
    assert is_valid is False
    assert "too short" in reason.lower()


def test_prompt_validator_rejects_hallucinated_pricing():
    no_pricing_profile = NormalizedBrandProfile(
        brand_id="b-1",
        domain="noprice.com",
        business_name="NoPrice",
        industry="SaaS",
        profile_version=1,
        pricing_models=[]
    )
    hallucinated_cand = GeneratedPromptCandidate(
        text="Is NoPrice worth $99/mo for small businesses?",
        category="pricing_value",
        intent="transactional",
        buying_stage="decision",
    )
    is_valid, reason = PromptValidator.validate(hallucinated_cand, no_pricing_profile)
    assert is_valid is False
    assert "pricing" in reason.lower()


def test_deduplication_exact_and_near_duplicate():
    cand1 = GeneratedPromptCandidate(
        text="What are the best tools for Edge Computing?",
        category="discovery",
        intent="informational",
        buying_stage="awareness",
    )
    # Exact duplicate (case-different)
    cand2 = GeneratedPromptCandidate(
        text="what are the best tools for edge computing?",
        category="discovery",
        intent="informational",
        buying_stage="awareness",
    )
    # Near duplicate
    cand3 = GeneratedPromptCandidate(
        text="What are the best tools for Edge Computing in 2026?",
        category="discovery",
        intent="informational",
        buying_stage="awareness",
    )
    # Distinct
    cand4 = GeneratedPromptCandidate(
        text="How does AcmeCloud handle real-time fraud detection?",
        category="use_cases",
        intent="informational",
        buying_stage="consideration",
    )

    deduped = PromptScorer.deduplicate([cand1, cand2, cand4])
    assert len(deduped) == 2
    assert deduped[0].text == cand1.text
    assert deduped[1].text == cand4.text


def test_scorer_computes_explainable_scores(sample_profile_data):
    normalized = ProfileNormalizer.normalize(sample_profile_data)
    cand = GeneratedPromptCandidate(
        text="How does AcmeCloud EdgeRouter Pro compare with legacy edge tools?",
        category="comparisons",
        intent="comparative",
        buying_stage="consideration",
        provenance_fact_ids=["f-1"],
        grounding_evidence=["EdgeRouter Pro delivers automated global edge traffic steering."],
    )
    scored = PromptScorer.score_candidate(cand, normalized, existing_accepted=[])

    assert 0.0 <= scored.quality_score <= 1.0
    assert "relevance" in scored.scores
    assert "grounding" in scored.scores
    assert "intent_clarity" in scored.scores
    assert "diversity" in scored.scores
    assert scored.scores["grounding"] >= 0.8
