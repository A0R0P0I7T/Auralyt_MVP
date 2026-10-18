"""API and integration tests for Engine 2: Prompt Intelligence."""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from app.db.models import Brand, ProfileRun, BrandFact


@pytest_asyncio.fixture
async def profiled_brand(test_db_session, test_org):
    """Fixture providing an onboarded brand with verified facts."""
    brand = Brand(
        domain="aurora-ai.io",
        business_name="Aurora AI",
        industry="Artificial Intelligence",
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
            fact_value={"description": "Autonomous AI workflow optimization platform."},
            confidence=0.95,
            user_confirmed=True,
            source_url="https://aurora-ai.io/about",
            evidence_snippet="Aurora AI accelerates enterprise agent orchestration.",
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="product_service",
            fact_value={"name": "Aurora Agent Flow"},
            confidence=0.90,
            user_confirmed=True,
            source_url="https://aurora-ai.io/products",
            evidence_snippet="Aurora Agent Flow orchestrates multi-agent tasks.",
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="target_audience",
            fact_value={"segment": "AI Engineers and Product Managers"},
            confidence=0.88,
            user_confirmed=False,
            source_url="https://aurora-ai.io/solutions",
            evidence_snippet="Built for AI engineers building production pipelines.",
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="pricing",
            fact_value={"model": "Developer Free Tier and Enterprise Scale"},
            confidence=0.85,
            user_confirmed=True,
            source_url="https://aurora-ai.io/pricing",
            evidence_snippet="Flexible developer and enterprise tiers.",
        ),
    ]
    test_db_session.add_all(facts)
    await test_db_session.commit()
    await test_db_session.refresh(brand)
    return brand


@pytest.mark.asyncio
async def test_generate_prompts_success(client: AsyncClient, profiled_brand):
    """Verify POST /api/brands/{brand_id}/prompts/generate produces prompts and returns 202."""
    payload = {
        "prompt_count": 15,
        "force_regenerate": True,
    }
    res = await client.post(f"/api/brands/{profiled_brand.id}/prompts/generate", json=payload)
    assert res.status_code == 202
    data = res.json()
    assert data["status"] == "completed"
    assert data["prompts_generated"] == 15
    assert data["run_id"] is not None
    assert data["profile_version"] == 1

    # Check run status endpoint
    run_res = await client.get(f"/api/brands/{profiled_brand.id}/prompts/runs/{data['run_id']}")
    assert run_res.status_code == 200
    r_data = run_res.json()
    assert r_data["status"] == "completed"
    assert r_data["prompts_generated"] == 15


@pytest.mark.asyncio
async def test_list_and_filter_prompts(client: AsyncClient, profiled_brand):
    """Verify GET /api/brands/{brand_id}/prompts supports pagination, filtering, and search."""
    # Generate prompts first
    await client.post(
        f"/api/brands/{profiled_brand.id}/prompts/generate",
        json={"prompt_count": 20, "force_regenerate": True}
    )

    # 1. List all prompts
    res = await client.get(f"/api/brands/{profiled_brand.id}/prompts?page=1&page_size=10")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 20
    assert len(data["items"]) == 10
    assert data["total_pages"] == 2
    assert "product_evaluation" in data["coverage_summary"]

    # 2. Filter by category
    cat_res = await client.get(f"/api/brands/{profiled_brand.id}/prompts?category=product_evaluation")
    assert cat_res.status_code == 200
    for item in cat_res.json()["items"]:
        assert item["category"] == "product_evaluation"

    # 3. Filter by search term
    search_res = await client.get(f"/api/brands/{profiled_brand.id}/prompts?search=Aurora")
    assert search_res.status_code == 200
    for item in search_res.json()["items"]:
        assert "aurora" in item["text"].lower()


@pytest.mark.asyncio
async def test_prompt_update_edit_approve_archive(client: AsyncClient, profiled_brand):
    """Verify PATCH /api/prompts/{prompt_id} updates text and approval status."""
    gen_res = await client.post(
        f"/api/brands/{profiled_brand.id}/prompts/generate",
        json={"prompt_count": 10, "force_regenerate": True}
    )
    assert gen_res.status_code == 202

    # Get first prompt
    list_res = await client.get(f"/api/brands/{profiled_brand.id}/prompts?page_size=1")
    prompt = list_res.json()["items"][0]
    prompt_id = prompt["id"]

    # Update text and toggle approval
    new_text = "How does Aurora AI compare with alternative enterprise orchestration engines?"
    patch_res = await client.patch(
        f"/api/prompts/{prompt_id}",
        json={"text": new_text, "is_approved": False}
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["text"] == new_text
    assert updated["is_approved"] is False
    assert updated["user_edited"] is True

    # Check detail endpoint
    get_res = await client.get(f"/api/prompts/{prompt_id}")
    assert get_res.status_code == 200
    detail = get_res.json()
    assert detail["text"] == new_text
    assert detail["user_edited"] is True


@pytest.mark.asyncio
async def test_coverage_summary_endpoint(client: AsyncClient, profiled_brand):
    """Verify GET /api/brands/{brand_id}/prompts/coverage returns aggregated metrics."""
    await client.post(
        f"/api/brands/{profiled_brand.id}/prompts/generate",
        json={"prompt_count": 15, "force_regenerate": True}
    )

    cov_res = await client.get(f"/api/brands/{profiled_brand.id}/prompts/coverage")
    assert cov_res.status_code == 200
    cov = cov_res.json()
    assert cov["total_prompts"] == 15
    assert cov["approved_prompts"] == 15
    assert cov["archived_prompts"] == 0
    assert len(cov["categories"]) > 0
    assert cov["average_quality_score"] > 0.0


@pytest.mark.asyncio
async def test_caching_and_idempotency(client: AsyncClient, profiled_brand):
    """Verify generate without force_regenerate reuses cached prompts for the same profile version."""
    # First generation
    res1 = await client.post(
        f"/api/brands/{profiled_brand.id}/prompts/generate",
        json={"prompt_count": 10, "force_regenerate": True}
    )
    run_id_1 = res1.json()["run_id"]

    # Second generation without force_regenerate
    res2 = await client.post(
        f"/api/brands/{profiled_brand.id}/prompts/generate",
        json={"prompt_count": 10, "force_regenerate": False}
    )
    run_id_2 = res2.json()["run_id"]

    # Must reuse the same run ID
    assert run_id_1 == run_id_2

    # Third generation WITH force_regenerate
    res3 = await client.post(
        f"/api/brands/{profiled_brand.id}/prompts/generate",
        json={"prompt_count": 10, "force_regenerate": True}
    )
    run_id_3 = res3.json()["run_id"]
    assert run_id_3 != run_id_1


@pytest.mark.asyncio
async def test_profile_version_bump_isolates_prompts(client: AsyncClient, profiled_brand, test_db_session):
    """Verify bumping profile_version generates new prompts tagged with the new version."""
    # Generate v1
    await client.post(
        f"/api/brands/{profiled_brand.id}/prompts/generate",
        json={"prompt_count": 10, "force_regenerate": True}
    )

    # Bump profile_version to 2
    profiled_brand.profile_version = 2
    await test_db_session.commit()

    # Generate v2
    res_v2 = await client.post(
        f"/api/brands/{profiled_brand.id}/prompts/generate",
        json={"prompt_count": 12, "force_regenerate": True}
    )
    assert res_v2.json()["profile_version"] == 2

    # Listing prompts for current version (v2) returns 12
    v2_list = await client.get(f"/api/brands/{profiled_brand.id}/prompts?profile_version=2")
    assert v2_list.json()["total"] == 12

    # Listing prompts for older version (v1) returns 10
    v1_list = await client.get(f"/api/brands/{profiled_brand.id}/prompts?profile_version=1")
    assert v1_list.json()["total"] == 10


@pytest.mark.asyncio
async def test_generate_fails_on_empty_profile(client: AsyncClient, test_db_session, test_org):
    """Verify generate returns 400 when brand has no crawled facts or description."""
    empty_brand = Brand(domain="emptybrand.io", business_name="EmptyBrand", profile_version=1, organization_id=test_org.id)
    test_db_session.add(empty_brand)
    await test_db_session.commit()

    res = await client.post(
        f"/api/brands/{empty_brand.id}/prompts/generate",
        json={"prompt_count": 10}
    )
    assert res.status_code == 400
    assert "empty brand profile" in res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_generate_fails_on_nonexistent_brand(client: AsyncClient):
    """Verify generate returns 404 on nonexistent brand ID."""
    res = await client.post(
        "/api/brands/nonexistent-uuid-12345/prompts/generate",
        json={"prompt_count": 10}
    )
    assert res.status_code == 404
    assert "brand not found" in res.json()["detail"].lower()
