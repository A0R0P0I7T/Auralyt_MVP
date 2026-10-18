"""Prompt Generation Remediation, Freshness, Relevance & Quality Gate Evaluation Suite.

Validates:
1. Nike-like footwear brand: 20 prompts, footwear-grounded, zero SaaS/software terms.
2. Road and trail running brand with blog article inspiration.
3. Sportswear brand (footwear and apparel).
4. Consumer electronics brand (headphones/audio, zero footwear terms).
5. Enterprise SaaS company (project management, zero apparel terms).
6. Ambiguous/insufficient category evidence (cautious awareness, rejection on empty).
7. Blog mentions unrelated products (category locking prevents prompt contamination).
8. Profile version changes and stale prompt set invalidation.
9. Exact reconciliation of prompt lifecycle counts (requested=20 -> evaluated=20).
10. Tenant isolation and security boundaries.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import Brand, ProfileRun, BrandFact, PromptRun, PromptCandidate, VisibilityScan
from app.prompts.models import (
    NormalizedBrandProfile,
    GroundedFact,
    GeneratedPromptCandidate,
)
from app.prompts.planner import CoveragePlanner
from app.prompts.generator import DeterministicGenerator, transform_article_title_to_question
from app.prompts.validator import PromptValidator
from app.prompts.normalizer import ProfileNormalizer
from app.evaluator.service import VisibilityEvaluatorService


# ==============================================================================
# FIXTURES & HELPERS
# ==============================================================================

def create_nike_like_profile() -> NormalizedBrandProfile:
    """Synthetic profile for a Nike-like running shoe brand."""
    facts = [
        GroundedFact(
            id="fact-nike-ind",
            fact_type="industry",
            fact_value="Footwear & Athletic Shoes",
            confidence=0.95,
            evidence_snippet="Leading manufacturer of athletic footwear, running shoes, and sports performance equipment.",
            supporting_evidence=[{"source_url": "https://nike.example/about", "snippet": "athletic footwear and running shoes"}],
            extraction_method="taxonomy_match"
        ),
        GroundedFact(
            id="fact-nike-prod-1",
            fact_type="product_service",
            fact_value={"name": "Air Zoom Pegasus Running Shoes", "category": "Road Running Shoes"},
            confidence=0.95,
            evidence_snippet="Air Zoom Pegasus Road Running Shoes offer responsive cushioning for daily training.",
            supporting_evidence=[{"source_url": "https://nike.example/pegasus", "snippet": "responsive cushioning for daily training"}],
            extraction_method="catalog"
        ),
        GroundedFact(
            id="fact-nike-prod-2",
            fact_type="product_service",
            fact_value={"name": "ZoomX Vaporfly Marathon Racing Shoes", "category": "Racing Shoes"},
            confidence=0.95,
            evidence_snippet="ZoomX Vaporfly Marathon Racing Shoes designed for distance runners chasing records.",
            supporting_evidence=[{"source_url": "https://nike.example/vaporfly", "snippet": "designed for distance runners"}],
            extraction_method="catalog"
        ),
        GroundedFact(
            id="fact-nike-prod-3",
            fact_type="product_service",
            fact_value={"name": "Wildhorse Trail Running Shoes", "category": "Trail Running Shoes"},
            confidence=0.90,
            evidence_snippet="Wildhorse Trail Running Shoes built for rugged off-road traction.",
            supporting_evidence=[{"source_url": "https://nike.example/trail", "snippet": "rugged off-road traction"}],
            extraction_method="catalog"
        ),
        GroundedFact(
            id="fact-nike-aud-1",
            fact_type="target_audience",
            fact_value="marathon training runners and daily joggers",
            confidence=0.90,
            evidence_snippet="Engineered for marathon training runners, sprinters, and daily joggers of all experience levels.",
            supporting_evidence=[{"source_url": "https://nike.example/running", "snippet": "marathon training runners"}],
            extraction_method="audience_extractor"
        ),
        GroundedFact(
            id="fact-nike-uc-1",
            fact_type="use_case",
            fact_value="half-marathon and long-distance road training",
            confidence=0.90,
            evidence_snippet="Optimal for half-marathon and long-distance road training sessions.",
            supporting_evidence=[{"source_url": "https://nike.example/training", "snippet": "half-marathon and long-distance road training"}],
            extraction_method="use_case_extractor"
        ),
        GroundedFact(
            id="fact-nike-blog-1",
            fact_type="use_case",
            fact_value="Road running vs trail running shoes: What you need to know",
            confidence=0.88,
            evidence_snippet="Blog article guide: Road running vs trail running shoes: What you need to know",
            supporting_evidence=[{"source_url": "https://nike.example/stories/road-vs-trail", "snippet": "Road running vs trail running shoes", "source_type": "article_topic"}],
            extraction_method="article_topic"
        ),
        GroundedFact(
            id="fact-nike-blog-2",
            fact_type="use_case",
            fact_value="How to choose running shoes for high arches",
            confidence=0.88,
            evidence_snippet="Buying guide: How to choose running shoes for high arches",
            supporting_evidence=[{"source_url": "https://nike.example/stories/high-arches", "snippet": "How to choose running shoes for high arches", "source_type": "article_topic"}],
            extraction_method="article_topic"
        ),
        GroundedFact(
            id="fact-nike-diff-1",
            fact_type="differentiator",
            fact_value="ZoomX foam responsive energy return",
            confidence=0.92,
            evidence_snippet="Proprietary ZoomX foam provides up to 85% responsive energy return.",
            supporting_evidence=[{"source_url": "https://nike.example/tech", "snippet": "ZoomX foam responsive energy return"}],
            extraction_method="differentiator_extractor"
        ),
    ]
    return NormalizedBrandProfile(
        brand_id="brand-nike-fixture",
        domain="nike.example",
        business_name="Nike",
        industry="Footwear & Athletic Shoes",
        target_market="Global",
        primary_language="en",
        profile_version=1,
        tagline_or_description="World leader in athletic footwear, running shoes, and sports performance apparel.",
        products_and_services=[
            "Nike Air Zoom Pegasus Running Shoes",
            "Nike ZoomX Vaporfly Marathon Racing Shoes",
            "Nike Wildhorse Trail Running Shoes"
        ],
        target_audiences=["marathon training runners and daily joggers", "daily fitness athletes"],
        use_cases=[
            "half-marathon and long-distance road training",
            "Road running vs trail running shoes: What you need to know",
            "How to choose running shoes for high arches"
        ],
        pricing_models=["Standard retail footwear ($120 - $260)"],
        differentiators=["ZoomX foam responsive energy return", "Flyknit breathable upper construction"],
        facts=facts,
        is_empty=False
    )


# ==============================================================================
# DETERMINISTIC QUALITY AND RELEVANCE TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_nike_running_shoe_relevance_and_zero_software_terms():
    """Verify Nike-like fixture produces 20 valid footwear prompts and 0 software/SaaS terms."""
    profile = create_nike_like_profile()
    assert profile.get_domain_archetype() == "footwear_apparel"

    plan = CoveragePlanner.create_plan(profile, requested_count=20, surplus_ratio=1.5)
    generator = DeterministicGenerator()
    candidates = await generator.generate(profile, plan)

    assert len(candidates) >= 20

    # Validate each candidate
    valid_candidates = []
    for cand in candidates:
        is_valid, reason = PromptValidator.validate(cand, profile, reject_brand_mentions=True)
        if is_valid:
            valid_candidates.append(cand)

    assert len(valid_candidates) >= 20, f"Expected at least 20 valid candidates, got {len(valid_candidates)}"

    footwear_keywords = {"shoe", "shoes", "running", "footwear", "trainer", "trainers", "sneaker", "marathon", "cushioning", "trail", "road"}
    forbidden_software_terms = {"software", "saas", "api", "database", "platform", "cloud", "crm", "workflow", "developer", "sdk", "backend"}

    for cand in valid_candidates[:20]:
        text_lower = cand.text.lower()
        # 1. Zero brand mentions
        assert "nike" not in text_lower, f"Brand leakage found in prompt: {cand.text}"

        # 2. Zero software / SaaS terms
        for bad_term in forbidden_software_terms:
            assert bad_term not in text_lower, f"Irrelevant software term '{bad_term}' in footwear prompt: {cand.text}"

        # 3. Must be grammatically complete and end with '?'
        assert cand.text.endswith("?"), f"Prompt does not end with question mark: {cand.text}"
        assert not any(placeholder in cand.text for placeholder in ["{category}", "{brand}", "{product}", "{pricing}"])

        # 4. Relevant footwear domain concept must be present
        has_footwear_concept = any(kw in text_lower for kw in footwear_keywords)
        assert has_footwear_concept, f"Footwear prompt lacks footwear grounding: {cand.text}"


@pytest.mark.asyncio
async def test_blog_article_inspiration_without_blind_copying():
    """Verify blog article titles are transformed into natural AI assistant questions."""
    title_1 = "Road running vs trail running shoes: What you need to know"
    q_1 = transform_article_title_to_question(title_1, "Running Shoes")
    assert q_1.endswith("?")
    assert "road running and trail running shoes" in q_1.lower()
    assert not q_1.startswith("Road running vs")  # transformed into question
    assert any(q_1.lower().startswith(prefix) for prefix in ["what is the difference", "how do i choose", "what are the key differences", "should i get", "what should i look for", "what are the main differences"])

    title_2 = "How to choose running shoes for high arches"
    q_2 = transform_article_title_to_question(title_2, "Running Shoes")
    assert q_2.endswith("?")
    assert "high arches" in q_2.lower()
    assert "choosing running shoes" in q_2.lower() or "choose running shoes" in q_2.lower() or "look for" in q_2.lower()


def test_category_locking_rejects_irrelevant_product_mentions():
    """Verify that a footwear brand profile rejects candidate prompts about audio or software."""
    profile = create_nike_like_profile()

    # Candidate prompt mentioning audio / headphones
    irrelevant_cand = GeneratedPromptCandidate(
        text="What are the best wireless noise cancelling headphones for daily focus?",
        category="discovery",
        intent="informational",
        buying_stage="awareness",
        provenance_fact_ids=["fact-nike-ind"]
    )
    is_valid, reason = PromptValidator.validate(irrelevant_cand, profile)
    assert not is_valid
    assert "incompatible with footwear" in reason.lower()

    # Candidate prompt mentioning cloud software
    saas_cand = GeneratedPromptCandidate(
        text="Which enterprise cloud database has the lowest latency?",
        category="product_evaluation",
        intent="commercial",
        buying_stage="consideration",
        provenance_fact_ids=["fact-nike-ind"]
    )
    is_valid_saas, reason_saas = PromptValidator.validate(saas_cand, profile)
    assert not is_valid_saas
    assert "incompatible with footwear" in reason_saas.lower()


@pytest.mark.asyncio
async def test_consumer_electronics_relevance_and_zero_footwear_terms():
    """Verify consumer electronics brand produces electronics prompts without footwear terms."""
    facts = [
        GroundedFact(
            id="fact-audio-ind",
            fact_type="industry",
            fact_value="Consumer Electronics",
            confidence=0.95,
            evidence_snippet="Designer of high-fidelity wireless audio and active noise-cancelling headphones.",
            supporting_evidence=[{"source_url": "https://audio.example", "snippet": "high-fidelity wireless audio"}],
            extraction_method="taxonomy_match"
        ),
        GroundedFact(
            id="fact-audio-prod",
            fact_type="product_service",
            fact_value={"name": "StudioPro Wireless Headphones"},
            confidence=0.95,
            evidence_snippet="StudioPro Wireless Headphones with 40-hour battery life and adaptive ANC.",
            supporting_evidence=[{"source_url": "https://audio.example/studiopro", "snippet": "40-hour battery life"}],
            extraction_method="catalog"
        ),
    ]
    audio_profile = NormalizedBrandProfile(
        brand_id="brand-audio-fixture",
        domain="audiopro.example",
        business_name="AudioPro",
        industry="Consumer Electronics",
        target_market="Global",
        primary_language="en",
        profile_version=1,
        tagline_or_description="Premium wireless audio and noise-cancelling headphones.",
        products_and_services=["AudioPro StudioPro Wireless Headphones", "AudioPro QuietBuds"],
        target_audiences=["audiophiles and frequent travelers"],
        use_cases=["commute listening and studio monitoring"],
        pricing_models=["Premium tier ($299)"],
        differentiators=["Lossless audio over Bluetooth"],
        facts=facts,
        is_empty=False
    )

    plan = CoveragePlanner.create_plan(audio_profile, requested_count=20, surplus_ratio=1.5)
    generator = DeterministicGenerator()
    candidates = await generator.generate(audio_profile, plan)

    assert len(candidates) >= 20
    for cand in candidates[:20]:
        text_lower = cand.text.lower()
        # Zero brand mentions
        assert "audiopro" not in text_lower
        # Zero footwear mentions
        for foot_term in ["shoe", "shoes", "sneaker", "running shoe", "trail shoe"]:
            assert foot_term not in text_lower, f"Footwear term in audio prompt: {cand.text}"


@pytest.mark.asyncio
async def test_lifecycle_count_reconciliation_end_to_end(client: AsyncClient, test_db_session: AsyncSession, test_org):
    """Verify exact count reconciliation: requested=20 -> generated>=20 -> accepted=20 -> persisted=20 -> evaluated=20."""
    # 1. Onboard a fresh brand
    brand = Brand(
        domain="runnerhub.example",
        business_name="RunnerHub",
        industry="Footwear & Athletic Shoes",
        organization_id=test_org.id,
        profile_version=1
    )
    test_db_session.add(brand)
    await test_db_session.flush()

    run = ProfileRun(brand_id=brand.id, status="completed", page_limit=5, pages_discovered=3, pages_succeeded=3)
    test_db_session.add(run)
    await test_db_session.flush()

    facts = [
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="product_service",
            fact_value={"name": "RunnerHub Stride Marathon Shoes"},
            source_url="https://runnerhub.example/stride",
            evidence_snippet="RunnerHub Stride Marathon Shoes with high cushion."
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="target_audience",
            fact_value="long distance runners",
            source_url="https://runnerhub.example/runners",
            evidence_snippet="Designed for long distance runners."
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="use_case",
            fact_value="marathon training",
            source_url="https://runnerhub.example/training",
            evidence_snippet="Optimal for marathon training."
        ),
    ]
    for f in facts:
        test_db_session.add(f)
    await test_db_session.commit()

    # 2. Request exactly 20 prompts
    gen_res = await client.post(
        f"/api/brands/{brand.id}/prompts/generate",
        json={"prompt_count": 20, "force_regenerate": True}
    )
    assert gen_res.status_code == 202
    gen_data = gen_res.json()

    requested_count = 20
    persisted_count = gen_data["prompts_generated"]
    assert persisted_count == requested_count, f"Expected 20 persisted prompts, got {persisted_count}"

    # Diagnostics verification
    diag = gen_data["diagnostics"]
    assert diag["requested_count"] == 20
    assert diag["accepted_count"] == 20
    assert diag["persisted_count"] == 20
    assert diag["generated_count"] >= 20

    # 3. Create Visibility Scan with mock provider
    scan_res = await client.post(
        f"/api/brands/{brand.id}/visibility/scans",
        json={"provider": "mock", "force_rescan": True}
    )
    assert scan_res.status_code == 202
    scan_data = scan_res.json()
    scan_id = scan_data["id"]

    # 4. Execute scan synchronously
    await VisibilityEvaluatorService.execute_scan(scan_id, db=test_db_session)

    # 5. Fetch completed scan and verify counts
    completed_scan_res = await client.get(f"/api/brands/{brand.id}/visibility/scans/{scan_id}")
    assert completed_scan_res.status_code == 200
    scan_detail = completed_scan_res.json()

    assert scan_detail["status"] == "completed"
    assert scan_detail["prompts_selected"] == 20
    assert scan_detail["prompts_completed"] == 20
    assert scan_detail["prompts_failed"] == 0

    # 6. Detailed results count verification: exactly 20 evaluations
    results_res = await client.get(f"/api/brands/{brand.id}/visibility/scans/{scan_id}/results")
    assert results_res.status_code == 200
    results_data = results_res.json()
    assert len(results_data["results"]) == 20
    assert results_data["scan"]["prompts_completed"] == 20


@pytest.mark.asyncio
async def test_stale_prompt_invalidation_on_profile_version_bump(client: AsyncClient, test_db_session: AsyncSession, test_org):
    """Verify that bumping profile_version does NOT reuse stale prompts from v1."""
    # 1. Onboard brand at v1
    brand = Brand(
        domain="freshshoes.example",
        business_name="FreshShoes",
        industry="Footwear & Athletic Shoes",
        organization_id=test_org.id,
        profile_version=1
    )
    test_db_session.add(brand)
    await test_db_session.flush()

    p_run1 = ProfileRun(brand_id=brand.id, status="completed", page_limit=5, pages_discovered=2, pages_succeeded=2)
    test_db_session.add(p_run1)
    await test_db_session.flush()

    fact1 = BrandFact(
        brand_id=brand.id,
        profile_version=1,
        fact_type="product_service",
        fact_value={"name": "FreshShoes Classic Trainer"},
        source_url="https://freshshoes.example",
        evidence_snippet="Classic Trainer shoes"
    )
    test_db_session.add(fact1)
    await test_db_session.commit()

    # 2. Generate prompts for v1
    v1_res = await client.post(
        f"/api/brands/{brand.id}/prompts/generate",
        json={"prompt_count": 20, "force_regenerate": True}
    )
    assert v1_res.json()["prompts_generated"] == 20
    assert v1_res.json()["profile_version"] == 1

    # 3. Simulate website re-profile: bump profile_version to 2 and add new facts
    brand.profile_version = 2
    p_run2 = ProfileRun(brand_id=brand.id, status="completed", page_limit=5, pages_discovered=3, pages_succeeded=3)
    test_db_session.add(p_run2)
    await test_db_session.flush()

    fact2 = BrandFact(
        brand_id=brand.id,
        profile_version=2,
        fact_type="product_service",
        fact_value={"name": "FreshShoes Carbon Speed Racer"},
        source_url="https://freshshoes.example/racer",
        evidence_snippet="Carbon Speed Racer for marathon competition."
    )
    test_db_session.add(fact2)
    await test_db_session.commit()

    # 4. Generate prompts without force_regenerate - must detect version change and generate fresh v2 prompts
    v2_res = await client.post(
        f"/api/brands/{brand.id}/prompts/generate",
        json={"prompt_count": 20, "force_regenerate": False}
    )
    assert v2_res.json()["prompts_generated"] == 20
    assert v2_res.json()["profile_version"] == 2

    # 5. Verify v1 prompts remain isolated in history
    v1_list = await client.get(f"/api/brands/{brand.id}/prompts?profile_version=1")
    assert v1_list.json()["total"] == 20

    # 6. Verify v2 prompts are active
    v2_list = await client.get(f"/api/brands/{brand.id}/prompts?profile_version=2")
    assert v2_list.json()["total"] == 20


@pytest.mark.asyncio
async def test_tenant_boundary_isolation_on_prompts_and_scans(
    client: AsyncClient, test_db_session: AsyncSession, test_user
):
    """Verify that a brand belonging to another organization cannot be viewed or scanned."""
    from app.db.models import Organization, OrganizationMember

    # Create Org B and Brand B
    org_b = Organization(name="Competitor Org", slug="competitor-org")
    test_db_session.add(org_b)
    await test_db_session.flush()

    brand_b = Brand(
        domain="otherbrand.example",
        business_name="OtherBrand",
        industry="Footwear",
        organization_id=org_b.id,
        profile_version=1
    )
    test_db_session.add(brand_b)
    await test_db_session.commit()

    # Attempt to generate prompts for Brand B using client authenticated as Org A
    res_gen = await client.post(
        f"/api/brands/{brand_b.id}/prompts/generate",
        json={"prompt_count": 20}
    )
    assert res_gen.status_code == 404

    # Attempt to list prompts for Brand B
    res_list = await client.get(f"/api/brands/{brand_b.id}/prompts")
    assert res_list.status_code == 404

    # Attempt to initiate visibility scan for Brand B
    res_scan = await client.post(
        f"/api/brands/{brand_b.id}/visibility/scans",
        json={"provider": "mock"}
    )
    assert res_scan.status_code == 404


@pytest.mark.asyncio
async def test_road_and_trail_running_brand_dual_coverage():
    """Verify footwear brand with road and trail products explores both disciplines."""
    facts = [
        GroundedFact(
            id="f-rt-ind",
            fact_type="industry",
            fact_value="Footwear & Athletic Shoes",
            confidence=0.95,
            evidence_snippet="Trail and road running shoe specialist.",
            extraction_method="taxonomy_match"
        ),
        GroundedFact(
            id="f-rt-prod1",
            fact_type="product_service",
            fact_value={"name": "Summit Trail Grip Runner", "category": "Trail Running Shoes"},
            confidence=0.95,
            evidence_snippet="Summit Trail Grip Runner with 5mm Vibram lugs.",
            extraction_method="catalog"
        ),
        GroundedFact(
            id="f-rt-prod2",
            fact_type="product_service",
            fact_value={"name": "Metro Pace Road Trainer", "category": "Road Running Shoes"},
            confidence=0.95,
            evidence_snippet="Metro Pace Road Trainer with responsive EVA foam.",
            extraction_method="catalog"
        ),
    ]
    profile = NormalizedBrandProfile(
        brand_id="b-road-trail",
        domain="peakrun.example",
        business_name="PeakRun",
        industry="Footwear & Athletic Shoes",
        primary_language="en",
        profile_version=1,
        tagline_or_description="Trail and road running shoes engineered for any terrain.",
        products_and_services=["PeakRun Summit Trail Grip Runner", "PeakRun Metro Pace Road Trainer"],
        facts=facts,
        is_empty=False
    )
    plan = CoveragePlanner.create_plan(profile, requested_count=20, surplus_ratio=1.5)
    generator = DeterministicGenerator()
    candidates = await generator.generate(profile, plan)
    texts = [c.text.lower() for c in candidates]

    has_trail = any("trail" in t for t in texts)
    has_road = any("road" in t or "running" in t for t in texts)
    assert has_trail, "Expected trail running topics in generated prompts"
    assert has_road, "Expected road running topics in generated prompts"


@pytest.mark.asyncio
async def test_sportswear_company_footwear_and_apparel():
    """Verify sportswear brand with footwear and apparel supports both categories without software leakage."""
    facts = [
        GroundedFact(
            id="f-sw-ind",
            fact_type="industry",
            fact_value="Sportswear & Athletic Apparel",
            confidence=0.95,
            evidence_snippet="Performance athletic footwear and running apparel.",
            extraction_method="taxonomy_match"
        ),
        GroundedFact(
            id="f-sw-prod1",
            fact_type="product_service",
            fact_value={"name": "AeroGlide Running Shoes"},
            confidence=0.95,
            evidence_snippet="AeroGlide Running Shoes with carbon plate.",
            extraction_method="catalog"
        ),
        GroundedFact(
            id="f-sw-prod2",
            fact_type="product_service",
            fact_value={"name": "Ventilation Performance Running Shorts"},
            confidence=0.95,
            evidence_snippet="Lightweight moisture-wicking running shorts.",
            extraction_method="catalog"
        ),
    ]
    profile = NormalizedBrandProfile(
        brand_id="b-sportswear",
        domain="aerosport.example",
        business_name="AeroSport",
        industry="Sportswear & Athletic Apparel",
        primary_language="en",
        profile_version=1,
        tagline_or_description="High-performance running shoes and athletic apparel.",
        products_and_services=["AeroSport AeroGlide Running Shoes", "AeroSport Ventilation Performance Running Shorts"],
        facts=facts,
        is_empty=False
    )
    plan = CoveragePlanner.create_plan(profile, requested_count=20, surplus_ratio=1.5)
    generator = DeterministicGenerator()
    candidates = await generator.generate(profile, plan)

    for cand in candidates[:20]:
        text_lower = cand.text.lower()
        assert "aerosport" not in text_lower
        for term in ["kubernetes", "database", "api", "saas", "sql", "crm"]:
            assert term not in text_lower, f"Irrelevant tech term in sportswear prompt: {cand.text}"


@pytest.mark.asyncio
async def test_saas_company_relevance_and_zero_apparel_terms():
    """Verify enterprise SaaS brand produces project management prompts with zero footwear terms."""
    facts = [
        GroundedFact(
            id="f-saas-ind",
            fact_type="industry",
            fact_value="Enterprise SaaS & Project Management",
            confidence=0.95,
            evidence_snippet="Streamlined issue tracking, sprints, and product roadmaps.",
            extraction_method="taxonomy_match"
        ),
        GroundedFact(
            id="f-saas-prod1",
            fact_type="product_service",
            fact_value={"name": "Issue Tracker & Sprint Planning"},
            confidence=0.95,
            evidence_snippet="High performance issue tracker and sprint cycles.",
            extraction_method="catalog"
        ),
    ]
    profile = NormalizedBrandProfile(
        brand_id="b-saas-pm",
        domain="flowpm.example",
        business_name="FlowPM",
        industry="Enterprise SaaS & Project Management",
        primary_language="en",
        profile_version=1,
        tagline_or_description="Issue tracking and agile sprint planning built for modern engineering teams.",
        products_and_services=["FlowPM Issue Tracker & Sprint Planning"],
        target_audiences=["software engineering teams", "product managers"],
        use_cases=["sprint planning and bug tracking"],
        pricing_models=["Free Tier ($0) and Pro ($12/user/month)"],
        facts=facts,
        is_empty=False
    )
    plan = CoveragePlanner.create_plan(profile, requested_count=20, surplus_ratio=1.5)
    generator = DeterministicGenerator()
    candidates = await generator.generate(profile, plan)

    assert len(candidates) >= 20
    for cand in candidates[:20]:
        text_lower = cand.text.lower()
        assert "flowpm" not in text_lower
        for foot_term in ["shoe", "shoes", "running shoe", "sneaker", "apparel", "footwear", "marathon training"]:
            assert foot_term not in text_lower, f"Irrelevant footwear term '{foot_term}' in SaaS prompt: {cand.text}"


@pytest.mark.asyncio
async def test_empty_or_ambiguous_category_evidence_rejection(client: AsyncClient, test_db_session: AsyncSession, test_org):
    """Verify empty brand profile rejects generation with actionable error."""
    empty_brand = Brand(
        domain="mystery.example",
        business_name="MysteryBrand",
        organization_id=test_org.id,
        profile_version=1
    )
    test_db_session.add(empty_brand)
    await test_db_session.commit()

    res = await client.post(
        f"/api/brands/{empty_brand.id}/prompts/generate",
        json={"prompt_count": 20}
    )
    assert res.status_code == 400
    assert "empty brand profile" in res.json()["detail"].lower()
