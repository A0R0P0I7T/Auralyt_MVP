"""Unit tests for Engine 3 deterministic visibility evaluator and mock provider."""
import pytest
from app.evaluator.evaluator import VisibilityResponseEvaluator
from app.evaluator.providers.mock_provider import MockAIModelProvider


def test_evaluator_brand_mention_and_context():
    """Verify target brand mention is detected and verbatim context snippet is extracted."""
    text = (
        "In the software engineering space, Linear is widely praised for its high performance "
        "and clean keyboard shortcuts. It makes backlog grooming fast and effortless."
    )
    res = VisibilityResponseEvaluator.evaluate(
        response_text=text,
        brand_name="Linear",
        brand_domain="linear.app"
    )

    assert res.brand_mentioned is True
    assert res.mention_context is not None
    assert "Linear" in res.mention_context
    assert res.recommendation_status != "not_mentioned"


def test_evaluator_non_mentioned_brand():
    """Verify brand not present in response returns brand_mentioned=False and not_mentioned status."""
    text = (
        "Top project management tools for agile teams include Jira and Trello. "
        "They offer comprehensive kanban boards and workflow automation."
    )
    res = VisibilityResponseEvaluator.evaluate(
        response_text=text,
        brand_name="Linear",
        brand_domain="linear.app"
    )

    assert res.brand_mentioned is False
    assert res.mention_context is None
    assert res.recommendation_status == "not_mentioned"
    assert res.comparative_position == "not_mentioned"


def test_evaluator_positive_recommendation_and_ranking():
    """Verify positive recommendation signals and ordered list rank detection."""
    text = (
        "Recommended tools for sprint planning:\n"
        "1. **Linear** — Top recommendation for fast-moving engineering teams. Highly recommended.\n"
        "2. **Jira** — Suitable for enterprise audit requirements.\n"
        "3. **Asana** — General purpose task management."
    )
    res = VisibilityResponseEvaluator.evaluate(
        response_text=text,
        brand_name="Linear",
        brand_domain="linear.app"
    )

    assert res.brand_mentioned is True
    assert res.recommendation_status == "recommended"
    assert res.visibility_rank == 1
    assert res.comparative_position == "leader"
    assert res.sentiment_score is not None and res.sentiment_score > 0.5


def test_evaluator_negative_recommendation():
    """Verify negative evaluation terms are detected."""
    text = (
        "We do not recommend Linear for non-technical teams because it lacks spreadsheet views "
        "and has a steep learning curve with poor custom field support."
    )
    res = VisibilityResponseEvaluator.evaluate(
        response_text=text,
        brand_name="Linear",
        brand_domain="linear.app"
    )

    assert res.brand_mentioned is True
    assert res.recommendation_status == "not_recommended"
    assert res.comparative_position == "unfavorable"
    assert res.sentiment_score is not None and res.sentiment_score < 0.0


def test_evaluator_competitor_mentions():
    """Verify competitors are identified and target brand is excluded from competitors."""
    text = (
        "When comparing issue trackers, teams usually evaluate Linear versus Jira, Asana, and Monday.com. "
        "Linear excels at developer velocity."
    )
    res = VisibilityResponseEvaluator.evaluate(
        response_text=text,
        brand_name="Linear",
        brand_domain="linear.app"
    )

    assert res.brand_mentioned is True
    assert "Jira" in res.competitor_mentions
    assert "Asana" in res.competitor_mentions
    # Target brand should NOT be in its own competitor list
    assert "Linear" not in res.competitor_mentions


def test_evaluator_citations_extracted_only_when_present():
    """Verify citations are extracted strictly when present and not invented."""
    text_with_links = (
        "Linear provides real-time issue sync. For details, see [Linear Docs](https://linear.app/docs) "
        "and their homepage at https://linear.app."
    )
    res_links = VisibilityResponseEvaluator.evaluate(
        response_text=text_with_links,
        brand_name="Linear",
        brand_domain="linear.app"
    )

    assert "https://linear.app/docs" in res_links.citations
    assert "https://linear.app" in res_links.citations

    # Response with zero URLs must yield empty citations list
    text_no_links = "Linear is a software development issue tracker."
    res_no_links = VisibilityResponseEvaluator.evaluate(
        response_text=text_no_links,
        brand_name="Linear",
        brand_domain="linear.app"
    )
    assert res_no_links.citations == []


@pytest.mark.asyncio
async def test_mock_provider_deterministic_response_and_simulation():
    """Verify MockAIModelProvider response structure, token usage, and simulated errors."""
    provider = MockAIModelProvider()

    # Success query
    resp = await provider.query("What are the best alternatives to Linear for issue tracking?")
    assert resp.is_success is True
    assert "Linear" in resp.text
    assert resp.provider == "mock"
    assert resp.model_name == "mock-evaluator-v1"
    assert resp.tokens_used is not None and resp.tokens_used > 0
    assert resp.latency_ms > 0

    # Simulated error query
    err_resp = await provider.query("Test query with [SIMULATE_ERROR]")
    assert err_resp.is_success is False
    assert "Simulated upstream provider error" in err_resp.error_message

    # Simulated timeout query
    timeout_resp = await provider.query("Test query with [SIMULATE_TIMEOUT]")
    assert timeout_resp.is_success is False
    assert "timed out" in timeout_resp.error_message
