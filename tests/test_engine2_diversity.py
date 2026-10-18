"""Regression and Verification Tests for Engine 2:
- DEF-E2-01: Grammar-aware slot normalization (no 'needing to switching')
- DEF-E2-02: Semantic diversity and template clustering avoidance
- DEF-E2-03: Contextual dictionary-word brand token validation
"""
import pytest
from app.prompts.models import (
    NormalizedBrandProfile,
    GroundedFact,
    PlannedPromptSlot,
    CoveragePlan,
    GeneratedPromptCandidate
)
from app.prompts.generator import DeterministicGenerator
from app.prompts.planner import CoveragePlanner
from app.prompts.validator import PromptValidator


@pytest.fixture
def linear_profile():
    facts = [
        GroundedFact(id="f1", fact_type="industry", fact_value="Project Management"),
        GroundedFact(id="f2", fact_type="product_service", fact_value={"name": "Issue Tracking", "type": "product"}),
        GroundedFact(id="f3", fact_type="product_service", fact_value={"name": "Project Roadmaps", "type": "product"}),
        GroundedFact(id="f4", fact_type="use_case", fact_value="switching project management tools"),
        GroundedFact(id="f5", fact_type="use_case", fact_value="automate sprint cycles"),
        GroundedFact(id="f6", fact_type="target_audience", fact_value="high-growth engineering teams"),
        GroundedFact(id="f7", fact_type="differentiator", fact_value="sub-second keyboard-first workflow"),
    ]
    return NormalizedBrandProfile(
        brand_id="test-brand-linear",
        profile_version=1,
        business_name="Linear",
        domain="linear.app",
        industry="Project Management",
        target_market="Global",
        products_and_services=["Issue Tracking", "Project Roadmaps"],
        use_cases=["switching project management tools", "automate sprint cycles"],
        target_audiences=["high-growth engineering teams"],
        differentiators=["sub-second keyboard-first workflow"],
        facts=facts
    )



@pytest.mark.asyncio
async def test_def_e2_01_grammar_normalization_no_clashes(linear_profile):
    """DEF-E2-01: Generated prompts must be grammatically natural, avoiding 'needing to switching'."""
    plan = CoveragePlanner.create_plan(linear_profile, requested_count=10)
    generator = DeterministicGenerator()
    candidates = await generator.generate(linear_profile, plan)

    # Check that no prompt contains "needing to switching" or "accomplish for"
    awkward_phrases = [
        "needing to switching",
        "needing to automating",
        "needing to managing",
        "accomplish for",
        "tools for to ",
        "best software for to "
    ]

    for cand in candidates:
        text_lower = cand.text.lower()
        for awkward in awkward_phrases:
            assert awkward not in text_lower, f"Grammar clash detected in prompt: '{cand.text}'"


@pytest.mark.asyncio
async def test_def_e2_02_semantic_diversity_and_clustering(linear_profile):
    """DEF-E2-02: 20 prompts must cover diverse buyer intents and not cluster around identical frames."""
    plan = CoveragePlanner.create_plan(linear_profile, requested_count=20)
    generator = DeterministicGenerator()
    candidates = await generator.generate(linear_profile, plan)

    assert len(candidates) == 20
    unique_texts = {c.text for c in candidates}
    # All 20 must be distinct
    assert len(unique_texts) == 20

    # Must cover at least 4 distinct categories/dimensions
    categories = {c.category for c in candidates}
    assert len(categories) >= 4, f"Expected at least 4 intent categories, got {len(categories)}: {categories}"

    # Must cover multiple buyer journey stages (awareness, consideration, decision)
    stages = {c.buying_stage for c in candidates}
    assert len(stages) >= 2


def test_def_e2_03_dictionary_word_brand_validation(linear_profile):
    """DEF-E2-03: Contextual validation allows common phrases ('linear regression') while rejecting real brand leakage."""
    # Test case 1: Genuine brand mention in prompt MUST be rejected
    cand_leak = GeneratedPromptCandidate(
        text="Why should engineering teams choose Linear over Jira for issue tracking?",
        category="comparisons",
        intent="comparative",
        buying_stage="consideration",
        provenance_fact_ids=["f1"]
    )
    is_valid, reason = PromptValidator.validate(cand_leak, linear_profile, reject_brand_mentions=True)
    assert is_valid is False
    assert "Linear" in reason or "linear" in reason

    # Test case 2: Dictionary word in legitimate mathematical context MUST NOT be falsely rejected
    cand_math = GeneratedPromptCandidate(
        text="How do modern platforms implement linear regression models for issue estimation?",
        category="product_evaluation",
        intent="commercial",
        buying_stage="consideration",
        target_product_service="Issue Tracking",
        provenance_fact_ids=["f2"]
    )
    is_valid_math, reason_math = PromptValidator.validate(cand_math, linear_profile, reject_brand_mentions=True)
    assert is_valid_math is True, f"Legitimate mathematical term 'linear regression' was falsely rejected: {reason_math}"
