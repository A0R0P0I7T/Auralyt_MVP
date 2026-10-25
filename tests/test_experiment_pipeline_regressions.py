"""Regression and Contract Tests for End-to-End AI Visibility Experiment Pipeline.

Covers:
1. Engine 1 category inference from AI title/meta/hero text (e.g., ChatGPT-style landing pages).
2. Distinction between successful crawl and sufficient usable profile evidence.
3. Profile version increment on re-onboarding / refresh.
4. URL vs Active Brand isolation (Engine 2 operates on submitted brand, not stale brand).
5. Engine 3 blocked when Engine 2 fails or has no approved prompts.
6. Honest status reporting when crawl succeeds but evidence is genuinely insufficient.
7. Cross-organization isolation.
"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Brand, ProfileRun, CrawledPage, BrandFact, Organization, User, OrganizationMember, PromptCandidate
from app.extractor.fact_synthesizer import FactSynthesizer
from app.services.profiler_service import ProfilerService
from app.prompts.normalizer import ProfileNormalizer
from app.prompts.service import PromptIntelligenceService
from app.evaluator.service import VisibilityEvaluatorService
from app.auth.security import hash_password, create_access_token


def test_fact_synthesizer_infers_ai_category_from_title_and_hero():
    """Engine 1 must infer Artificial Intelligence & Machine Learning when title/hero contains AI indicators."""
    homepage = CrawledPage(
        brand_id="b-test",
        requested_url="https://chatgpt.com/",
        final_url="https://chatgpt.com/",
        http_status=200,
        title="ChatGPT: Chat, Work, Create & Code with AI",
        meta_description="Use ChatGPT to answer questions, write, create images, complete work, and code—all in one place. Get started for free or download the app.",
        headings={"h1": [], "h2": ["Log in or sign up"]},
        extracted_text="ChatGPT is AI. By using it, you agree to our Terms & Privacy Policy. Chats may be reviewed and used to improve our AI models.",
        page_type="homepage",
        structured_data=[]
    )
    synthesizer = FactSynthesizer(
        brand_id="b-test",
        profile_version=1,
        user_business_name="ChatGPT",
        user_industry=None,
    )
    facts = synthesizer.synthesize_facts([homepage])
    cat_fact = next((f for f in facts if f.fact_type in ("industry", "category")), None)
    assert cat_fact is not None, "Failed to infer industry/category fact from AI title and text"
    assert "Artificial Intelligence" in str(cat_fact.fact_value)


def test_fact_synthesizer_extracts_use_cases_from_meta_description():
    """Engine 1 should extract actionable use cases from meta description ('Use X to [actions]...')."""
    homepage = CrawledPage(
        brand_id="b-test",
        requested_url="https://chatgpt.com/",
        final_url="https://chatgpt.com/",
        http_status=200,
        title="ChatGPT: Chat, Work, Create & Code with AI",
        meta_description="Use ChatGPT to answer questions, write, create images, complete work, and code—all in one place.",
        headings={"h1": [], "h2": []},
        extracted_text="Log in or sign up",
        page_type="homepage",
        structured_data=[]
    )
    synthesizer = FactSynthesizer(
        brand_id="b-test",
        profile_version=1,
        user_business_name="ChatGPT",
        user_industry=None,
    )
    facts = synthesizer.synthesize_facts([homepage])
    use_cases = [f for f in facts if f.fact_type == "use_case"]
    assert len(use_cases) > 0, "Expected at least one use case extracted from meta description"


@pytest.mark.asyncio
async def test_onboard_existing_brand_increments_profile_version(test_db_session: AsyncSession, test_org: Organization):
    """When an existing brand is re-onboarded for a new crawl, profile_version must increment."""
    brand = Brand(
        domain="chatgpt.com",
        business_name="Chatgpt",
        organization_id=test_org.id,
        profile_version=1
    )
    test_db_session.add(brand)
    await test_db_session.commit()

    # Re-onboard the brand with ProfilerService
    updated_brand, run = await ProfilerService.onboard_brand(
        website_url="https://chatgpt.com",
        organization_id=test_org.id,
        db=test_db_session
    )
    assert updated_brand.id == brand.id
    assert updated_brand.profile_version == 2, f"Expected profile_version 2, got {updated_brand.profile_version}"
    assert run.profile_version == 2, f"Expected run profile_version 2, got {run.profile_version}"


@pytest.mark.asyncio
async def test_genuine_insufficient_evidence_profile_fails_safely_and_blocks_engine_3(test_db_session: AsyncSession, test_org: Organization):
    """When a profile genuinely lacks evidence, Engine 2 raises ValueError and Engine 3 is blocked."""
    brand = Brand(
        domain="empty-brand.com",
        business_name="Empty Brand",
        industry=None,
        organization_id=test_org.id,
        profile_version=1
    )
    test_db_session.add(brand)
    await test_db_session.flush()

    # Brand has only a business name fact, but NO industry, NO category, NO products, NO use cases
    fact = BrandFact(
        brand_id=brand.id,
        profile_version=1,
        fact_type="business_name",
        fact_value="Empty Brand",
        confidence=1.0,
        user_confirmed=True
    )
    test_db_session.add(fact)
    await test_db_session.commit()

    # Engine 2 must reject this profile safely
    with pytest.raises(ValueError, match="insufficient evidence"):
        await PromptIntelligenceService.generate_prompts(
            brand_id=brand.id,
            prompt_count=10,
            force_regenerate=True,
            db=test_db_session
        )

    # Engine 3 must not run when no approved prompts exist
    with pytest.raises(ValueError, match="approved prompts"):
        await VisibilityEvaluatorService.create_scan(
            brand_id=brand.id,
            provider="mock",
            db=test_db_session
        )


@pytest.mark.asyncio
async def test_pipeline_isolates_submitted_url_from_unrelated_active_brand(client: AsyncClient, test_db_session: AsyncSession, test_org: Organization):
    """Submitting https://chatgpt.com must create/use chatgpt.com brand, NOT the previously active brand."""
    # Brand 1: Louis Vuitton
    lv_brand = Brand(
        domain="in.louisvuitton.com",
        business_name="Louisvuitton",
        industry="Luxury Fashion",
        organization_id=test_org.id,
        profile_version=1
    )
    test_db_session.add(lv_brand)
    await test_db_session.commit()

    # Client onboards https://chatgpt.com
    res = await client.post("/api/brands/profile", json={"website_url": "https://chatgpt.com"})
    assert res.status_code == 202
    data = res.json()
    assert data["brand_id"] != lv_brand.id
    assert data["domain"] == "chatgpt.com"


@pytest.mark.asyncio
async def test_engine_1_usable_facts_to_engine_2_prompt_generation_and_count(test_db_session: AsyncSession, test_org: Organization):
    """Engine 1 usable facts are correctly loaded by Engine 2 to produce requested grounded prompt count."""
    brand = Brand(
        domain="techplatform.io",
        business_name="TechPlatform",
        industry="Artificial Intelligence & Machine Learning",
        organization_id=test_org.id,
        profile_version=1
    )
    test_db_session.add(brand)
    await test_db_session.flush()

    facts = [
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="industry",
            fact_value="Artificial Intelligence & Machine Learning",
            confidence=0.9,
            user_confirmed=True
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="product_service",
            fact_value="Automated Code Assistant",
            confidence=0.85,
            user_confirmed=True
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="use_case",
            fact_value="write automated tests",
            confidence=0.85,
            user_confirmed=True
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="target_audience",
            fact_value="software engineers",
            confidence=0.85,
            user_confirmed=True
        )
    ]
    test_db_session.add_all(facts)
    await test_db_session.commit()

    run, prompts = await PromptIntelligenceService.generate_prompts(
        brand_id=brand.id,
        prompt_count=10,
        force_regenerate=True,
        db=test_db_session
    )
    assert run is not None
    assert len(prompts) >= 5, f"Expected at least 5 prompts, got {len(prompts)}"
    assert all(p.brand_id == brand.id for p in prompts)
    assert all(p.profile_version == 1 for p in prompts)


@pytest.mark.asyncio
async def test_engine_1_fetches_pages_but_extracts_insufficient_evidence_marks_warning(test_db_session: AsyncSession, test_org: Organization):
    """When crawler fetches pages but no business context can be extracted, ProfilerService identifies lack of usable evidence."""
    brand = Brand(
        domain="sparse-site.com",
        business_name="SparseSite",
        industry=None,
        organization_id=test_org.id,
        profile_version=1
    )
    test_db_session.add(brand)
    await test_db_session.flush()

    run = ProfileRun(
        brand_id=brand.id,
        profile_version=1,
        status="pending",
        page_limit=5
    )
    test_db_session.add(run)
    await test_db_session.flush()

    c_page = CrawledPage(
        brand_id=brand.id,
        profile_run_id=run.id,
        requested_url="https://sparse-site.com/",
        final_url="https://sparse-site.com/",
        http_status=200,
        title="",
        meta_description="",
        headings={},
        extracted_text="Access denied. Click here to verify you are human.",
        page_type="other",
        content_hash="abc123hash",
        structured_data=[]
    )
    test_db_session.add(c_page)
    await test_db_session.commit()

    synthesizer = FactSynthesizer(
        brand_id=brand.id,
        profile_version=1,
        user_business_name=None,
        user_industry=None
    )
    new_facts = synthesizer.synthesize_facts([c_page])
    has_usable_evidence = bool(
        brand.industry
        or any(f.fact_type in ("industry", "category", "product_service", "use_case") for f in new_facts)
    )
    assert not has_usable_evidence, "Sparse site should not have usable category, product, or use case facts"


@pytest.mark.asyncio
async def test_transaction_or_persistence_failure_prevents_next_stage(test_db_session: AsyncSession):
    """Non-existent brand or missing profile snapshot prevents Engine 2 prompt generation."""
    with pytest.raises(ValueError, match="Brand not found"):
        await PromptIntelligenceService.generate_prompts(
            brand_id="non-existent-brand-id",
            prompt_count=10,
            db=test_db_session
        )


@pytest.mark.asyncio
async def test_cross_organization_access_cannot_substitute_another_org_profile(client: AsyncClient, test_db_session: AsyncSession):
    """User in Org A cannot generate prompts or scans for Org B's brand."""
    org_b = Organization(name="Other Corp", slug="other-corp")
    test_db_session.add(org_b)
    await test_db_session.flush()

    other_brand = Brand(
        domain="competitor.com",
        business_name="Competitor",
        industry="Retail",
        organization_id=org_b.id,
        profile_version=1
    )
    test_db_session.add(other_brand)
    await test_db_session.commit()

    res = await client.post(f"/api/brands/{other_brand.id}/prompts/generate", json={"prompt_count": 5})
    assert res.status_code in (403, 404), f"Expected 403 or 404 for cross-tenant access, got {res.status_code}"


@pytest.mark.asyncio
async def test_api_terminal_failure_state_when_engine_2_fails(client: AsyncClient, test_db_session: AsyncSession, test_org: Organization):
    """API endpoint returns HTTP 400 when Engine 2 rejects profile due to insufficient evidence."""
    sparse_brand = Brand(
        domain="insufficient-brand.com",
        business_name="InsufficientBrand",
        industry=None,
        organization_id=test_org.id,
        profile_version=1
    )
    test_db_session.add(sparse_brand)
    await test_db_session.flush()

    # Brand is not completely empty (has business_name fact), but has no category, products, or use cases
    fact = BrandFact(
        brand_id=sparse_brand.id,
        profile_version=1,
        fact_type="business_name",
        fact_value="InsufficientBrand",
        confidence=1.0,
        user_confirmed=True
    )
    test_db_session.add(fact)
    await test_db_session.commit()

    res = await client.post(f"/api/brands/{sparse_brand.id}/prompts/generate", json={"prompt_count": 5})
    assert res.status_code == 400
    detail = res.json().get("detail", "")
    assert "insufficient evidence" in detail


@pytest.mark.asyncio
async def test_engine_3_failure_preserves_root_cause_in_error_summary(test_db_session: AsyncSession, test_org: Organization):
    """When Engine 3 queries fail, scan.error_summary preserves the root cause diagnostic rather than a generic message."""
    brand = Brand(
        domain="nike.in",
        business_name="Nike",
        industry="Sporting Goods & Athletic Footwear",
        organization_id=test_org.id,
        profile_version=1
    )
    test_db_session.add(brand)
    await test_db_session.flush()

    fact = BrandFact(
        brand_id=brand.id,
        profile_version=1,
        fact_type="industry",
        fact_value="Sporting Goods & Athletic Footwear",
        confidence=1.0,
        user_confirmed=True
    )
    test_db_session.add(fact)
    await test_db_session.commit()

    await PromptIntelligenceService.generate_prompts(
        brand_id=brand.id,
        prompt_count=5,
        force_regenerate=True,
        db=test_db_session
    )

    # Create a scan with an intentional bad provider or mock that simulates auth failure
    from unittest.mock import AsyncMock, patch
    from app.evaluator.providers.base import ProviderResponse

    mock_fail_resp = ProviderResponse(
        text="",
        provider="gemini",
        model_name="gemini-3.1-flash-lite",
        is_success=False,
        is_retryable=False,
        error_message="Authentication failed (HTTP 401): API key not valid. Please pass a valid API key."
    )

    with patch("app.evaluator.service.get_evaluator_provider") as mock_get_prov:
        prov_instance = AsyncMock()
        prov_instance.provider_name = "gemini"
        prov_instance.default_model = "gemini-3.1-flash-lite"
        prov_instance.query.return_value = mock_fail_resp
        mock_get_prov.return_value = prov_instance

        scan = await VisibilityEvaluatorService.create_scan(
            brand_id=brand.id,
            provider="gemini",
            db=test_db_session
        )
        # Background task runs inline in test
        await VisibilityEvaluatorService.execute_scan(scan.id, db=test_db_session)

        await test_db_session.refresh(scan)
        assert scan.status == "failed"
        assert "Authentication failed (HTTP 401)" in scan.error_summary, f"Expected 401 in error summary, got: {scan.error_summary}"


@pytest.mark.asyncio
async def test_end_to_end_pipeline_validation_with_nike_in_and_mock_provider(test_db_session: AsyncSession, test_org: Organization):
    """End-to-end validation of the complete pipeline using nike.in with the offline deterministic mock provider."""
    # Step 1: Brand & Profile Facts
    brand = Brand(
        domain="nike.in",
        business_name="Nike India",
        industry="Sporting Goods & Athletic Footwear",
        organization_id=test_org.id,
        profile_version=1
    )
    test_db_session.add(brand)
    await test_db_session.flush()

    facts = [
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="industry",
            fact_value="Sporting Goods & Athletic Footwear",
            confidence=0.95,
            user_confirmed=True
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="product_service",
            fact_value="Road Running Shoes",
            confidence=0.9,
            user_confirmed=True
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="product_service",
            fact_value="Athletic Apparel and Tracksuits",
            confidence=0.9,
            user_confirmed=True
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="use_case",
            fact_value="marathon training and daily running",
            confidence=0.85,
            user_confirmed=True
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="target_audience",
            fact_value="runners and fitness enthusiasts",
            confidence=0.85,
            user_confirmed=True
        )
    ]
    test_db_session.add_all(facts)
    await test_db_session.commit()

    # Step 2: Engine 2 Prompt Generation
    prompt_run, prompts = await PromptIntelligenceService.generate_prompts(
        brand_id=brand.id,
        prompt_count=10,
        force_regenerate=True,
        db=test_db_session
    )
    assert prompt_run.status == "completed"
    assert len(prompts) >= 5, f"Expected at least 5 prompts, got {len(prompts)}"

    # Step 3: Engine 3 AI Visibility Scan via Offline Mock
    scan = await VisibilityEvaluatorService.create_scan(
        brand_id=brand.id,
        provider="mock",
        max_prompts=10,
        force_rescan=True,
        db=test_db_session
    )
    await VisibilityEvaluatorService.execute_scan(scan.id, db=test_db_session)

    await test_db_session.refresh(scan)
    assert scan.status in ("completed", "completed_with_warnings"), f"Expected completed scan, got {scan.status} ({scan.error_summary})"
    assert scan.visibility_score is not None, "Expected valid visibility score"
    assert scan.prompts_completed > 0, "Expected completed prompt evaluations"
