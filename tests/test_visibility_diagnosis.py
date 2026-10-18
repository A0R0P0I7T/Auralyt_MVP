"""Unit and integration tests for VisibilityDiagnosisService and Action Recommendations (DEF-DX-01)."""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Brand,
    BrandFact,
    PromptRun,
    PromptCandidate,
    VisibilityScan,
    VisibilityResult,
    Organization,
    User
)
from app.services.diagnosis_service import VisibilityDiagnosisService


@pytest_asyncio.fixture
async def setup_diagnostic_scan(test_db_session: AsyncSession, test_org: Organization):

    """Sets up a complete brand, active profile facts, prompts, and evaluated scan results."""
    brand = Brand(
        domain="linear.app",
        business_name="Linear",
        industry="Project Management",
        organization_id=test_org.id,
        profile_version=1
    )
    test_db_session.add(brand)
    await test_db_session.flush()

    # Engine 1 Facts
    f1 = BrandFact(
        brand_id=brand.id,
        profile_version=1,
        fact_type="product_service",
        fact_value={"name": "Issue Tracking", "type": "product"},
        source_url="https://linear.app",
        evidence_snippet="Linear is purpose-built for issue tracking.",
        extraction_method="heading_heuristic",
        confidence=0.85
    )
    f2 = BrandFact(
        brand_id=brand.id,
        profile_version=1,
        fact_type="differentiator",
        fact_value="Sub-second speed and keyboard shortcuts",
        source_url="https://linear.app",
        evidence_snippet="Sub-second speed and keyboard shortcuts built for high-performance teams.",
        extraction_method="content_heuristic",
        confidence=0.80
    )
    test_db_session.add_all([f1, f2])
    await test_db_session.flush()

    # Engine 2 Run & Prompts
    prun = PromptRun(
        brand_id=brand.id,
        profile_version=1,
        status="completed",
        prompt_count_requested=4,
        prompts_generated=4
    )
    test_db_session.add(prun)
    await test_db_session.flush()

    p1 = PromptCandidate(
        brand_id=brand.id,
        prompt_run_id=prun.id,
        profile_version=1,
        text="What are the best tools for issue tracking?",
        normalized_text="what are the best tools for issue tracking?",
        category="discovery",
        intent="informational",
        buying_stage="awareness"
    )
    p2 = PromptCandidate(
        brand_id=brand.id,
        prompt_run_id=prun.id,
        profile_version=1,
        text="Which software is best for sprint planning?",
        normalized_text="which software is best for sprint planning?",
        category="discovery",
        intent="commercial",
        buying_stage="consideration"
    )
    p3 = PromptCandidate(
        brand_id=brand.id,
        prompt_run_id=prun.id,
        profile_version=1,
        text="How does Jira compare to modern alternatives?",
        normalized_text="how does jira compare to modern alternatives?",
        category="comparisons",
        intent="comparative",
        buying_stage="consideration"
    )
    p4 = PromptCandidate(
        brand_id=brand.id,
        prompt_run_id=prun.id,
        profile_version=1,
        text="What are top platforms recommended for issue tracking?",
        normalized_text="what are top platforms recommended for issue tracking?",
        category="recommendations",
        intent="commercial",
        buying_stage="decision"
    )
    test_db_session.add_all([p1, p2, p3, p4])
    await test_db_session.flush()

    # Engine 3 Scan
    scan = VisibilityScan(
        brand_id=brand.id,
        profile_version=1,
        provider="mock",
        model_name="mock-model",
        status="completed",
        prompts_selected=4,
        prompts_completed=4,
        prompts_failed=0,
        mention_rate=0.5,
        recommendation_rate=0.25,
        visibility_score=55.0
    )
    test_db_session.add(scan)
    await test_db_session.flush()

    # Results showing:
    # - Mentioned in P1 & P4 (discovery & recommendations)
    # - Blindspot in P3 (comparisons: 0 mentions, competitor Jira cited)
    # - Citation deficit: Competitor cited https://jira.atlassian.com, 0 target citations
    r1 = VisibilityResult(
        scan_id=scan.id,
        brand_id=brand.id,
        prompt_id=p1.id,
        prompt_text=p1.text,
        provider="mock",
        model_name="mock-model",
        execution_status="success",
        brand_mentioned=True,
        recommendation_status="neutral_mention",
        visibility_rank=2,
        competitor_mentions=["Jira"],
        citations=["https://jira.atlassian.com"],
        raw_response_metadata={"target_brand_citations": []}
    )
    r2 = VisibilityResult(
        scan_id=scan.id,
        brand_id=brand.id,
        prompt_id=p2.id,
        prompt_text=p2.text,
        provider="mock",
        model_name="mock-model",
        execution_status="success",
        brand_mentioned=False,
        recommendation_status="not_mentioned",
        visibility_rank=None,
        competitor_mentions=["Jira", "Asana"],
        citations=["https://jira.atlassian.com"],
        raw_response_metadata={"target_brand_citations": []}
    )
    r3 = VisibilityResult(
        scan_id=scan.id,
        brand_id=brand.id,
        prompt_id=p3.id,
        prompt_text=p3.text,
        provider="mock",
        model_name="mock-model",
        execution_status="success",
        brand_mentioned=False,
        recommendation_status="not_mentioned",
        visibility_rank=None,
        competitor_mentions=["Jira", "Linear-Competitor"],
        citations=["https://atlassian.com"],
        raw_response_metadata={"target_brand_citations": []}
    )
    r4 = VisibilityResult(
        scan_id=scan.id,
        brand_id=brand.id,
        prompt_id=p4.id,
        prompt_text=p4.text,
        provider="mock",
        model_name="mock-model",
        execution_status="success",
        brand_mentioned=True,
        recommendation_status="recommended",
        visibility_rank=1,
        comparative_position="leader",
        competitor_mentions=["Jira"],
        citations=["https://jira.atlassian.com"],
        raw_response_metadata={"target_brand_citations": []}
    )
    test_db_session.add_all([r1, r2, r3, r4])
    await test_db_session.commit()

    return brand, scan


@pytest.mark.asyncio
async def test_diagnosis_abstains_on_insufficient_sample(test_db_session: AsyncSession, setup_diagnostic_scan):
    """DEF-DX-01: Must abstain with clear reason if scan has < 3 completed prompts or is running/failed."""
    brand, scan = setup_diagnostic_scan
    scan.prompts_completed = 1
    scan.status = "running"
    await test_db_session.commit()

    report = await VisibilityDiagnosisService.diagnose_scan(scan.id, brand.id, test_db_session)
    assert report.status == "insufficient_data"
    assert report.findings_count == 0
    assert report.abstention_reason is not None
    assert "small or incomplete" in report.abstention_reason


@pytest.mark.asyncio
async def test_diagnosis_generates_actionable_findings(test_db_session: AsyncSession, setup_diagnostic_scan):
    """DEF-DX-01: Generates evidence-backed findings (citation deficit, competitive leadership) with testable follow-ups."""
    brand, scan = setup_diagnostic_scan
    scan.prompts_completed = 4
    scan.status = "completed"
    await test_db_session.commit()

    report = await VisibilityDiagnosisService.diagnose_scan(scan.id, brand.id, test_db_session)
    assert report.status == "sufficient_data"
    assert report.findings_count > 0

    finding_types = [f.finding_type for f in report.findings]
    # Check Citation Deficit finding was triggered
    assert "citation_deficit" in finding_types
    cit_finding = next(f for f in report.findings if f.finding_type == "citation_deficit")
    assert cit_finding.severity == "medium"
    assert "Schema.org" in cit_finding.recommended_action
    assert "measurable_follow_up" in cit_finding.model_dump()
    assert cit_finding.confidence > 0.7

    # Check Competitive Strength finding was triggered from Rank #1 result
    assert "competitive_strength" in finding_types
    strength_finding = next(f for f in report.findings if f.finding_type == "competitive_strength")
    assert "Rank #1" in strength_finding.observation


@pytest.mark.asyncio
async def test_diagnosis_api_endpoint_authenticated(client: AsyncClient, setup_diagnostic_scan):
    """DEF-DX-01: GET /api/brands/{brand_id}/visibility/scans/{scan_id}/diagnosis returns 200 with structured report."""
    brand, scan = setup_diagnostic_scan
    scan.prompts_completed = 4
    scan.status = "completed"

    res = await client.get(f"/api/brands/{brand.id}/visibility/scans/{scan.id}/diagnosis")
    assert res.status_code == 200
    data = res.json()
    assert data["scan_id"] == scan.id
    assert data["brand_id"] == brand.id
    assert data["status"] == "sufficient_data"
    assert isinstance(data["findings"], list)
    assert data["findings_count"] == len(data["findings"])
