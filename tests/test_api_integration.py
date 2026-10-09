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
async def test_crawled_pages_pagination(client: AsyncClient, test_db_session):
    # Setup test brand and pages directly
    brand = Brand(domain="pagetest.org", business_name="PageTest Org")
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
