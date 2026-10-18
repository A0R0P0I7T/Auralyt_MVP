"""Regression and Verification Tests for Engine 1:
- DEF-E1-01: Industry/category synthesis from URL-only onboarding
- DEF-E1-02: Verbatim evidence provenance (avoiding synthetic/procedural strings)
- DEF-E1-03: Confidence heuristics and provenance metadata transparency
"""
import pytest
from app.db.models import CrawledPage, BrandFact
from app.extractor.fact_synthesizer import FactSynthesizer


def test_def_e1_01_url_only_onboarding_synthesizes_grounded_category():
    """DEF-E1-01: When user_industry is None, crawl evidence must synthesize grounded industry/category."""
    homepage = CrawledPage(
        requested_url="https://linear.app",
        final_url="https://linear.app",
        http_status=200,
        title="Linear – Purpose-built tool for modern software development",
        meta_description="Linear is an issue tracking and project management tool designed for high-performance software teams.",
        headings={"h1": ["Linear is a purpose-built tool for planning and building products"]},
        extracted_text="Linear is an issue tracking and project management platform. Issue tracking built for speed. Cycle planning and project roadmaps.",
        page_type="homepage"
    )

    synthesizer = FactSynthesizer(
        brand_id="test-brand-123",
        profile_version=1,
        user_business_name="Linear",
        user_industry=None  # URL-only onboarding
    )

    facts = synthesizer.synthesize_facts([homepage])
    industry_facts = [f for f in facts if f.fact_type in ("industry", "category")]

    assert len(industry_facts) > 0, "Engine 1 must synthesize an industry/category fact when crawl evidence is available!"
    cat_fact = industry_facts[0]
    assert any(term in cat_fact.fact_value.lower() for term in ("project management", "issue tracking", "software development", "developer tools"))
    assert cat_fact.extraction_method != "user_input", "Inferred category must be labeled with its actual extraction method, not user_input"
    assert cat_fact.confidence > 0.0
    # Must have verbatim evidence snippet
    assert cat_fact.evidence_snippet is not None
    assert "Linear is an issue tracking" in cat_fact.evidence_snippet or "purpose-built tool" in cat_fact.evidence_snippet


def test_def_e1_01_abstains_when_evidence_insufficient():
    """DEF-E1-01: When website content is blank or insufficient, Engine 1 must abstain rather than hallucinating."""
    empty_homepage = CrawledPage(
        requested_url="https://empty-example.com",
        final_url="https://empty-example.com",
        http_status=200,
        title="",
        meta_description=None,
        headings={"h1": []},
        extracted_text="",
        page_type="homepage"
    )

    synthesizer = FactSynthesizer(
        brand_id="test-brand-456",
        profile_version=1,
        user_business_name="EmptyBrand",
        user_industry=None
    )

    facts = synthesizer.synthesize_facts([empty_homepage])
    industry_facts = [f for f in facts if f.fact_type in ("industry", "category")]
    assert len(industry_facts) == 0, "Engine 1 must not fabricate an industry when crawl evidence is empty!"


def test_def_e1_02_evidence_snippets_are_verbatim_page_content():
    """DEF-E1-02: Evidence snippets must contain verbatim source text rather than procedural templates."""
    h1_text = "Real-time collaborative kanban boards"
    bullet_feature = "Sub-second keyboard navigation and dark mode"
    page = CrawledPage(
        requested_url="https://linear.app/features",
        final_url="https://linear.app/features",
        http_status=200,
        title="Linear Features",
        headings={"h1": [h1_text]},
        extracted_text=f"Core capabilities:\n* {bullet_feature}\n* Fast offline syncing",
        page_type="product_service"
    )

    synthesizer = FactSynthesizer(
        brand_id="test-brand-789",
        profile_version=1,
        user_business_name="Linear",
        user_industry="Project Management"
    )

    facts = synthesizer.synthesize_facts([page])

    # Check product/service fact snippet
    product_facts = [f for f in facts if f.fact_type == "product_service"]
    assert len(product_facts) > 0
    for pf in product_facts:
        snippet = pf.evidence_snippet
        # The snippet must NOT be a procedural string like "Heading '...' on product_service page"
        assert not snippet.startswith("Heading '"), f"Procedural snippet found: {snippet}"
        assert not snippet.startswith("Page title '"), f"Procedural snippet found: {snippet}"
        # It must contain verbatim text matching the heading or title
        assert h1_text in snippet or "Linear Features" in snippet

    # Check feature list fact snippet
    feature_facts = [f for f in facts if f.fact_type == "product_feature"]
    assert len(feature_facts) > 0
    for ff in feature_facts:
        snippet = ff.evidence_snippet
        assert not snippet.startswith("Feature list item: '"), f"Procedural snippet found: {snippet}"
        assert bullet_feature in snippet or "Fast offline syncing" in snippet


def test_def_e1_03_confidence_and_provenance_metadata():
    """DEF-E1-03: Facts must include supporting_evidence structure with provenance_type and heuristic confidence."""
    page = CrawledPage(
        requested_url="https://example.com",
        final_url="https://example.com",
        http_status=200,
        title="Example App",
        meta_description="Example App is a cloud monitoring platform.",
        headings={"h1": ["Cloud Monitoring Platform"]},
        extracted_text="Example App is a cloud monitoring platform for microservices.",
        page_type="homepage"
    )

    synthesizer = FactSynthesizer(
        brand_id="test-brand-abc",
        profile_version=1,
        user_business_name="Example App",
        user_industry=None
    )

    facts = synthesizer.synthesize_facts([page])
    assert len(facts) > 0

    for f in facts:
        assert 0.0 <= f.confidence <= 1.0
        assert hasattr(f, "supporting_evidence")
        assert isinstance(f.supporting_evidence, list)
        if f.supporting_evidence:
            ev = f.supporting_evidence[0]
            assert "source_url" in ev
            assert "snippet" in ev
