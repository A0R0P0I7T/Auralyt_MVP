"""Regression tests for Engine 3 P0 Attribution & Scoring Defects:
- DEF-E3-01: Competitor citation credit leakage
- DEF-E3-02: Dictionary-word brand homonym false positives
- DEF-E3-03: Competitor endorsement misattribution in contrastive/comparative clauses
- DEF-E3-04: Ranking factor incorporation in visibility scoring
"""
import pytest
from app.evaluator.evaluator import VisibilityResponseEvaluator


def test_def_e3_01_competitor_citation_leakage_isolated():
    """DEF-E3-01: Citations from competitor domains must NOT be credited as target brand citations."""
    text = (
        "For enterprise project management, Jira is the standard tool. See [Jira](https://jira.atlassian.com) "
        "and [Asana](https://asana.com/guide). Meanwhile, Linear (https://linear.app) is great for startups."
    )
    res = VisibilityResponseEvaluator.evaluate(
        response_text=text,
        brand_name="Linear",
        brand_domain="linear.app",
        known_competitors=["Jira", "Asana"]
    )

    assert res.brand_mentioned is True
    # Target brand citations should ONLY contain linear.app URLs
    assert hasattr(res, "target_brand_citations"), "EvaluationResult must have target_brand_citations"
    assert "https://linear.app" in res.target_brand_citations
    assert "https://jira.atlassian.com" not in res.target_brand_citations
    assert "https://asana.com/guide" not in res.target_brand_citations

    # Competitor citations should contain competitor URLs
    assert hasattr(res, "competitor_citations"), "EvaluationResult must have competitor_citations"
    assert any("atlassian.com" in u for u in res.competitor_citations)
    assert any("asana.com" in u for u in res.competitor_citations)


def test_def_e3_02_dictionary_word_brand_homonym_false_positives():
    """DEF-E3-02: Dictionary words like 'linear' in mathematical or general context must not trigger brand mention."""
    # Test case 1: "linear regression" should NOT be attributed to Linear
    text_math = "In introductory statistics, linear regression models the relationship between dependent and independent variables."
    res_math = VisibilityResponseEvaluator.evaluate(
        response_text=text_math,
        brand_name="Linear",
        brand_domain="linear.app"
    )
    assert res_math.brand_mentioned is False
    assert res_math.recommendation_status == "not_mentioned"
    assert "homonym" in res_math.evaluation_reasoning.lower() or "not mentioned" in res_math.evaluation_reasoning.lower()

    # Test case 2: "scale up" should NOT be attributed to Scale AI
    text_scale = "To handle increased web traffic, teams need to scale up their cloud infrastructure horizontally."
    res_scale = VisibilityResponseEvaluator.evaluate(
        response_text=text_scale,
        brand_name="Scale",
        brand_domain="scale.com"
    )
    assert res_scale.brand_mentioned is False

    # Test case 3: Genuine brand mention in software context MUST still be recognized
    text_genuine = "Linear is an exceptional issue tracking tool with blazing fast keyboard shortcuts."
    res_genuine = VisibilityResponseEvaluator.evaluate(
        response_text=text_genuine,
        brand_name="Linear",
        brand_domain="linear.app"
    )
    assert res_genuine.brand_mentioned is True
    assert res_genuine.recommendation_status in ("recommended", "neutral_mention")


def test_def_e3_03_competitor_endorsement_misattribution_contrastive():
    """DEF-E3-03: Recommending a competitor in a contrastive clause must NOT mark target brand as recommended."""
    # Contrastive sentence with While
    text_while = "While Linear is a fast modern tool, Jira remains the top choice for enterprise teams."
    res_while = VisibilityResponseEvaluator.evaluate(
        response_text=text_while,
        brand_name="Linear",
        brand_domain="linear.app",
        known_competitors=["Jira"]
    )
    assert res_while.brand_mentioned is True
    # Linear is NOT the top choice here, Jira is!
    assert res_while.recommendation_status != "recommended", "Linear was falsely marked recommended when Jira was endorsed!"
    assert res_while.comparative_position != "leader"
    assert res_while.recommendation_status in ("neutral_mention", "not_recommended")

    # Contrastive sentence with Although
    text_although = "Although Linear offers great UI, we strongly recommend Jira for complex enterprise compliance."
    res_although = VisibilityResponseEvaluator.evaluate(
        response_text=text_although,
        brand_name="Linear",
        brand_domain="linear.app",
        known_competitors=["Jira"]
    )
    assert res_although.recommendation_status != "recommended"

    # Comparative preference: "prefer X over Y"
    text_prefer = "Most engineering leaders prefer Jira over Linear when audit logs are required."
    res_prefer = VisibilityResponseEvaluator.evaluate(
        response_text=text_prefer,
        brand_name="Linear",
        brand_domain="linear.app",
        known_competitors=["Jira"]
    )
    assert res_prefer.recommendation_status != "recommended"


@pytest.mark.asyncio
async def test_def_e3_04_ranking_factor_in_visibility_scoring(test_db_session, test_org):
    """DEF-E3-04: Average position rank must differentiate score between rank #1 and rank #5."""
    from app.db.models import Brand, PromptRun, PromptCandidate, VisibilityScan, VisibilityResult
    from app.evaluator.service import VisibilityEvaluatorService

    brand = Brand(
        domain="ranktest.com",
        business_name="RankTest",
        organization_id=test_org.id,
        profile_version=1
    )
    test_db_session.add(brand)
    await test_db_session.flush()

    run = PromptRun(
        brand_id=brand.id,
        profile_version=1,
        status="completed",
        prompt_count_requested=1,
        prompts_generated=1
    )
    test_db_session.add(run)
    await test_db_session.flush()

    prompt = PromptCandidate(
        brand_id=brand.id,
        prompt_run_id=run.id,
        profile_version=1,
        text="What are the best tools?",
        normalized_text="what are the best tools?",
        category="discovery",
        intent="commercial",
        buying_stage="awareness"
    )
    test_db_session.add(prompt)
    await test_db_session.flush()


    # Scan A: Brand is ranked #1
    scan_a = VisibilityScan(
        brand_id=brand.id,
        profile_version=1,
        provider="mock",
        model_name="mock-model",
        status="running",
        prompts_selected=1
    )
    test_db_session.add(scan_a)
    await test_db_session.flush()

    res_a = VisibilityResult(
        scan_id=scan_a.id,
        brand_id=brand.id,
        prompt_id=prompt.id,
        prompt_text=prompt.text,
        provider="mock",
        model_name="mock-model",
        execution_status="success",
        brand_mentioned=True,
        recommendation_status="recommended",
        visibility_rank=1,
        citations=["https://ranktest.com"]
    )
    test_db_session.add(res_a)

    # Scan B: Brand is mentioned and recommended, but ranked #8
    scan_b = VisibilityScan(
        brand_id=brand.id,
        profile_version=1,
        provider="mock",
        model_name="mock-model",
        status="running",
        prompts_selected=1
    )
    test_db_session.add(scan_b)
    await test_db_session.flush()

    res_b = VisibilityResult(
        scan_id=scan_b.id,
        brand_id=brand.id,
        prompt_id=prompt.id,
        prompt_text=prompt.text,
        provider="mock",
        model_name="mock-model",
        execution_status="success",
        brand_mentioned=True,
        recommendation_status="recommended",
        visibility_rank=8,
        citations=["https://ranktest.com"]
    )
    test_db_session.add(res_b)
    await test_db_session.commit()

    # Compute score for Scan A and Scan B
    score_a = VisibilityEvaluatorService.calculate_composite_score(
        mention_rate=1.0,
        recommendation_rate=1.0,
        target_citation_count=1,
        total_prompts=1,
        avg_position=1.0
    )
    score_b = VisibilityEvaluatorService.calculate_composite_score(
        mention_rate=1.0,
        recommendation_rate=1.0,
        target_citation_count=1,
        total_prompts=1,
        avg_position=8.0
    )

    assert score_a > score_b, f"Expected rank #1 score ({score_a}) to exceed rank #8 score ({score_b})!"
