import pytest
from httpx import AsyncClient
from app.db.models import Brand, ProfileRun, BrandFact, CrawledPage
from app.services.profiler_service import ProfilerService


@pytest.mark.asyncio
async def test_refresh_preserves_user_confirmed_facts(client: AsyncClient, test_db_session, test_org):
    # 1. Create a brand with profile_version = 1
    brand = Brand(
        domain="example-brand.com",
        business_name="Original Name",
        profile_version=1,
        organization_id=test_org.id
    )
    test_db_session.add(brand)
    await test_db_session.flush()

    # 2. Add an unconfirmed fact and a user-confirmed fact
    unconfirmed_fact = BrandFact(
        brand_id=brand.id,
        profile_version=1,
        fact_type="product_service",
        fact_value="Old Unconfirmed Product",
        user_confirmed=False,
        confidence=0.7
    )
    confirmed_fact = BrandFact(
        brand_id=brand.id,
        profile_version=1,
        fact_type="target_audience",
        fact_value="B2B Enterprise CTOs",
        user_confirmed=True,
        confidence=1.0,
        evidence_snippet="Explicitly verified by compliance team"
    )
    test_db_session.add(unconfirmed_fact)
    test_db_session.add(confirmed_fact)
    await test_db_session.commit()

    # 3. Trigger refresh run via API
    res = await client.post(
        f"/api/brands/{brand.id}/profile-runs",
        json={"page_limit": 20}
    )
    assert res.status_code == 202
    data = res.json()
    assert data["profile_version"] == 2

    # 4. Query facts to ensure user-confirmed fact is intact
    facts_res = await client.get(f"/api/brands/{brand.id}/facts")
    assert facts_res.status_code == 200
    facts_list = facts_res.json()
    
    # Confirm that the verified fact is preserved
    confirmed_found = next((f for f in facts_list if f["fact_value"] == "B2B Enterprise CTOs"), None)
    assert confirmed_found is not None
    assert confirmed_found["user_confirmed"] is True
    assert confirmed_found["evidence_snippet"] == "Explicitly verified by compliance team"
