import pytest
from httpx import AsyncClient
from app.db.models import Brand, ProfileRun, BrandFact, CrawledPage


@pytest.mark.asyncio
async def test_health_check(client: AsyncClient):
    res = await client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "Engine 1" in data["engine"]


@pytest.mark.asyncio
async def test_onboard_blocks_ssrf_url(client: AsyncClient):
    payload = {
        "website_url": "http://127.0.0.1:8000/admin",
        "business_name": "Test Local"
    }
    res = await client.post("/api/brands/profile", json=payload)
    assert res.status_code == 400
    assert "Security/URL validation error" in res.json()["detail"]


@pytest.mark.asyncio
async def test_brand_onboarding_and_fact_management(client: AsyncClient, test_db_session):
    # 1. Onboard a valid domain
    payload = {
        "website_url": "https://example.com",
        "business_name": "Example Corp",
        "industry": "Cloud Infrastructure",
        "target_market": "Global",
        "language": "en"
    }
    onboard_res = await client.post("/api/brands/profile", json=payload)
    assert onboard_res.status_code == 202
    res_data = onboard_res.json()
    brand_id = res_data["brand_id"]
    run_id = res_data["run_id"]
    assert brand_id is not None
    assert run_id is not None

    # 2. Check Run status
    run_res = await client.get(f"/api/brands/profile-runs/{run_id}")
    assert run_res.status_code == 200
    run_json = run_res.json()
    assert run_json["id"] == run_id
    assert run_json["brand_id"] == brand_id

    # 3. Add manual fact
    fact_payload = {
        "fact_type": "product_service",
        "fact_value": "High-availability edge routing engine",
        "source_url": "https://example.com/products/routing",
        "evidence_snippet": "Confirmed from architecture documentation",
        "confidence": 1.0,
        "user_confirmed": True
    }
    fact_res = await client.post(f"/api/brands/{brand_id}/facts", json=fact_payload)
    assert fact_res.status_code == 201
    fact_data = fact_res.json()
    fact_id = fact_data["id"]
    assert fact_data["user_confirmed"] is True
    assert fact_data["fact_type"] == "product_service"

    # 4. Confirm/Update fact via PATCH
    patch_res = await client.patch(
        f"/api/brands/{brand_id}/facts/{fact_id}",
        json={"user_confirmed": True, "fact_value": "Updated high-availability edge router"}
    )
    assert patch_res.status_code == 200
    assert patch_res.json()["fact_value"] == "Updated high-availability edge router"

    # 5. Retrieve Brand Profile
    profile_res = await client.get(f"/api/brands/{brand_id}/profile")
    assert profile_res.status_code == 200
    pdata = profile_res.json()
    assert pdata["brand"]["domain"] == "example.com"
    assert pdata["business_overview"]["business_name"] == "Example Corp"
    assert pdata["verification_progress"]["confirmed_facts"] >= 1

    # 6. Delete fact
    del_res = await client.delete(f"/api/brands/{brand_id}/facts/{fact_id}")
    assert del_res.status_code == 204

    # Verify fact is removed
    facts_res = await client.get(f"/api/brands/{brand_id}/facts")
    assert facts_res.status_code == 200
    assert not any(f["id"] == fact_id for f in facts_res.json())


@pytest.mark.asyncio
async def test_crawled_pages_pagination(client: AsyncClient, test_db_session, test_org):
    # Setup test brand and pages directly
    brand = Brand(domain="pagetest.org", business_name="PageTest Org", organization_id=test_org.id)
    test_db_session.add(brand)
    await test_db_session.flush()

    run = ProfileRun(brand_id=brand.id, status="completed", page_limit=10)
    test_db_session.add(run)
    await test_db_session.flush()

    for i in range(5):
        page = CrawledPage(
            brand_id=brand.id,
            profile_run_id=run.id,
            requested_url=f"https://pagetest.org/page-{i}",
            final_url=f"https://pagetest.org/page-{i}",
            http_status=200,
            title=f"Page {i}",
            headings={"h1": [f"Header {i}"], "h2": []},
            extracted_text=f"Text for page {i}",
            page_type="product_service" if i % 2 == 0 else "about",
            content_hash=f"hash-{i}"
        )
        test_db_session.add(page)
    await test_db_session.commit()

    # Query with pagination
    res = await client.get(f"/api/brands/{brand.id}/pages?page=1&page_size=3")
    assert res.status_code == 200
    data = res.json()
    assert data["total"] == 5
    assert len(data["items"]) == 3
    assert data["total_pages"] == 2

    # Filter by page_type
    filtered_res = await client.get(f"/api/brands/{brand.id}/pages?page_type=about")
    assert filtered_res.status_code == 200
    fdata = filtered_res.json()
    assert fdata["total"] == 2


@pytest.mark.asyncio
async def test_create_brand_fact_rejects_malicious_source_url(client: AsyncClient, test_db_session, test_org):
    brand = Brand(domain="factsecurity.org", business_name="FactSecurity Org", organization_id=test_org.id)
    test_db_session.add(brand)
    await test_db_session.commit()

    # Reject javascript: pseudo-protocol
    res = await client.post(f"/api/brands/{brand.id}/facts", json={
        "fact_type": "product_service",
        "fact_value": "Malicious script link test",
        "source_url": "javascript:alert(1)"
    })
    assert res.status_code == 400
    assert "http or https" in res.json()["detail"].lower()

    # Reject file:// protocol
    res_file = await client.post(f"/api/brands/{brand.id}/facts", json={
        "fact_type": "product_service",
        "fact_value": "Local file read link test",
        "source_url": "file:///etc/passwd"
    })
    assert res_file.status_code == 400


@pytest.mark.asyncio
async def test_brand_profile_contract_freeze_schema(client: AsyncClient, test_db_session, test_org):
    """
    Contract Freeze Test: Verifies that GET /api/brands/{brand_id}/profile adheres
    strictly to the ProfileSummaryResponse schema required by Engine 2.
    """
    brand = Brand(
        domain="contract-test.com",
        business_name="Contract Test Corp",
        industry="SaaS",
        target_market="Enterprise",
        language="en",
        organization_id=test_org.id,
        profile_version=1
    )
    test_db_session.add(brand)
    await test_db_session.flush()

    run = ProfileRun(
        brand_id=brand.id,
        status="completed",
        page_limit=10,
        pages_discovered=10,
        pages_succeeded=5
    )
    test_db_session.add(run)
    await test_db_session.flush()

    fact1 = BrandFact(
        brand_id=brand.id,
        profile_version=1,
        fact_type="business_overview",
        fact_value={"description": "AI Visibility Intelligence Platform"},
        confidence=0.95,
        user_confirmed=True,
        source_url="https://contract-test.com/about",
        evidence_snippet="AI visibility intelligence platform for modern brands"
    )
    fact2 = BrandFact(
        brand_id=brand.id,
        profile_version=1,
        fact_type="product_service",
        fact_value={"name": "Automated Brand Monitor"},
        confidence=0.88,
        user_confirmed=False,
        source_url="https://contract-test.com/products",
        evidence_snippet="Real-time automated brand monitoring across generative models"
    )
    test_db_session.add_all([fact1, fact2])
    await test_db_session.commit()

    res = await client.get(f"/api/brands/{brand.id}/profile")
    assert res.status_code == 200
    data = res.json()

    # Guaranteed top-level keys
    guaranteed_keys = [
        "brand", "active_run", "profile_version", "business_overview",
        "products_and_services", "target_audience", "use_cases",
        "pricing_information", "differentiators", "faqs",
        "contact_and_company_info", "supported_languages",
        "facts", "coverage_summary", "verification_progress"
    ]
    for key in guaranteed_keys:
        assert key in data, f"Missing guaranteed contract field '{key}' in profile summary"

    # Brand fields
    assert data["brand"]["id"] == brand.id
    assert data["brand"]["domain"] == "contract-test.com"
    assert data["brand"]["business_name"] == "Contract Test Corp"

    # Profile version
    assert data["profile_version"] == 1

    # Fact structure & provenance
    assert len(data["facts"]) == 2
    fact_entry = next(f for f in data["facts"] if f["fact_type"] == "business_overview")
    assert fact_entry["user_confirmed"] is True
    assert fact_entry["source_url"] == "https://contract-test.com/about"
    assert "provenance" in fact_entry or "evidence_snippet" in fact_entry

    # Verification progress counters
    assert data["verification_progress"]["total_facts"] == 2
    assert data["verification_progress"]["confirmed_facts"] == 1


@pytest.mark.asyncio
async def test_brand_profile_contract_empty_profile_behavior(client: AsyncClient, test_db_session, test_org):
    """
    Contract Freeze Test: Brand with no facts returns 200 with empty lists/dicts
    rather than failing or returning null.
    """
    brand = Brand(
        domain="empty-profile.com",
        business_name="Empty Profile Inc",
        organization_id=test_org.id,
        profile_version=1
    )
    test_db_session.add(brand)
    await test_db_session.commit()

    res = await client.get(f"/api/brands/{brand.id}/profile")
    assert res.status_code == 200
    data = res.json()
    assert data["facts"] == []
    assert data["verification_progress"]["total_facts"] == 0
    assert data["verification_progress"]["confirmed_facts"] == 0
    assert isinstance(data["products_and_services"], list)
    assert len(data["products_and_services"]) == 0


@pytest.mark.asyncio
async def test_brand_profile_contract_not_found_404(client: AsyncClient):
    """
    Contract Freeze Test: Requesting a non-existent brand returns 404.
    """
    res = await client.get("/api/brands/non-existent-uuid/profile")
    assert res.status_code == 404
    assert res.json()["detail"] == "Brand not found."


