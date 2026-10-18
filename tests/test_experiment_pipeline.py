"""Deterministic Pipeline Orchestration Tests for Auralyt MVP.

Verifies the complete sequence:
Engine 1 (Brand Profile) -> Engine 2 (Prompt Intelligence) -> Engine 3 (AI Visibility Evaluator) -> Results Persistence
"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Brand, ProfileRun, BrandFact, CrawledPage, Organization, User, OrganizationMember
from app.auth.security import hash_password, create_access_token


@pytest.mark.asyncio
async def test_end_to_end_experiment_pipeline_deterministic(client: AsyncClient, test_db_session: AsyncSession, test_org: Organization):
    """
    Verify complete 3-engine pipeline orchestration with deterministic mock provider:
    1. Engine 1: Profile facts exist for brand.
    2. Engine 2: POST /api/brands/{brand_id}/prompts/generate produces 10 approved prompts.
    3. Engine 3: POST /api/brands/{brand_id}/visibility/scans executes scan against prompts.
    4. Results: GET /api/brands/{brand_id}/visibility/scans/{scan_id}/results returns complete score & prompt evaluations.
    5. Persistence: Scan and prompt-level results persist and are retrievable.
    """
    # 1. Setup Engine 1 Profile in DB
    brand = Brand(
        domain="chatgpt-test.com",
        business_name="ChatGPT Test",
        industry="Artificial Intelligence",
        target_market="Global",
        language="en",
        organization_id=test_org.id,
        profile_version=1
    )
    test_db_session.add(brand)
    await test_db_session.flush()

    run = ProfileRun(
        brand_id=brand.id,
        profile_version=1,
        status="completed",
        page_limit=10,
        pages_discovered=5,
        pages_succeeded=5
    )
    test_db_session.add(run)
    await test_db_session.flush()

    facts = [
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="business_overview",
            fact_value={"description": "Conversational artificial intelligence assistant for workflow automation."},
            confidence=0.98,
            user_confirmed=True
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="product_service",
            fact_value="GPT-4o Multimodal Reasoning Engine",
            confidence=0.95,
            user_confirmed=True
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="pricing_tier",
            fact_value={"tier_name": "Free", "price": 0, "billing_period": "monthly"},
            confidence=0.90,
            user_confirmed=True
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="pricing_tier",
            fact_value={"tier_name": "Plus", "price": 20, "billing_period": "monthly"},
            confidence=0.92,
            user_confirmed=True
        ),
        BrandFact(
            brand_id=brand.id,
            profile_version=1,
            fact_type="target_audience",
            fact_value="Knowledge workers, developers, and enterprise teams.",
            confidence=0.90,
            user_confirmed=True
        ),
    ]
    for f in facts:
        test_db_session.add(f)
    await test_db_session.commit()

    # Verify Engine 1 Profile can be retrieved
    profile_res = await client.get(f"/api/brands/{brand.id}/profile")
    assert profile_res.status_code == 200
    p_data = profile_res.json()
    assert len(p_data["facts"]) == 5

    # 2. Engine 2: Generate 10 grounded prompts
    gen_res = await client.post(
        f"/api/brands/{brand.id}/prompts/generate",
        json={"prompt_count": 10, "force_regenerate": True}
    )
    assert gen_res.status_code == 202
    gen_data = gen_res.json()
    assert gen_data["status"] == "completed"
    assert gen_data["prompts_generated"] == 10

    # Verify prompts are retrievable
    prompts_res = await client.get(f"/api/brands/{brand.id}/prompts?page=1&page_size=20")
    assert prompts_res.status_code == 200
    prompts_data = prompts_res.json()
    assert prompts_data["total"] == 10
    prompt_items = prompts_data["items"]
    assert all(p["is_approved"] for p in prompt_items)

    # 3. Engine 3: Execute AI Visibility scan with deterministic mock provider
    scan_res = await client.post(
        f"/api/brands/{brand.id}/visibility/scans",
        json={
            "provider": "mock",
            "max_prompts": 10,
            "force_rescan": True
        }
    )
    assert scan_res.status_code == 202
    scan_data = scan_res.json()
    scan_id = scan_data["id"]
    assert scan_data["provider"] == "mock"
    assert scan_data["prompts_selected"] == 10

    # 3. Execute scan directly with test_db_session for deterministic in-memory test execution
    from app.evaluator.service import VisibilityEvaluatorService
    await VisibilityEvaluatorService.execute_scan(scan_id, db=test_db_session)

    # Poll / verify scan is completed
    poll_res = await client.get(f"/api/brands/{brand.id}/visibility/scans/{scan_id}")
    assert poll_res.status_code == 200
    poll_data = poll_res.json()
    assert poll_data["status"] == "completed"

    # 4. Results: Inspect full results payload
    results_res = await client.get(f"/api/brands/{brand.id}/visibility/scans/{scan_id}/results")
    assert results_res.status_code == 200
    res_data = results_res.json()

    assert res_data["scan"]["id"] == scan_id
    assert res_data["scan"]["visibility_score"] is not None
    assert res_data["scan"]["mention_rate"] is not None
    assert res_data["scan"]["recommendation_rate"] is not None
    assert len(res_data["results"]) == 10

    # Verify prompt-level evaluation structure
    for r in res_data["results"]:
      assert "prompt_id" in r
      assert "prompt_text" in r
      assert "brand_mentioned" in r
      assert "recommendation_status" in r
      assert "raw_response_text" in r
      assert r["execution_status"] == "success"

    # 5. Persistence: Verify scan is listed in historical scans
    history_res = await client.get(f"/api/brands/{brand.id}/visibility/scans")
    assert history_res.status_code == 200
    hist_items = history_res.json()["items"]
    assert any(s["id"] == scan_id for s in hist_items)


@pytest.mark.asyncio
async def test_experiment_cross_tenant_isolation(client: AsyncClient, test_db_session: AsyncSession, test_org: Organization):
    """
    Verify that another tenant cannot access or trigger scans on this brand's experiment.
    """
    # Create Tenant B
    org_b = Organization(name="Tenant B", slug="tenant-b")
    test_db_session.add(org_b)
    await test_db_session.flush()

    user_b = User(
        email="bob@tenant-b.com",
        hashed_password=hash_password("Pass123!"),
        full_name="Bob Tenant B"
    )
    test_db_session.add(user_b)
    await test_db_session.flush()
    test_db_session.add(OrganizationMember(organization_id=org_b.id, user_id=user_b.id, role="owner"))

    brand_a = Brand(
        domain="alpha-secret.com",
        business_name="Alpha Secret",
        organization_id=test_org.id,
        profile_version=1
    )
    test_db_session.add(brand_a)
    await test_db_session.commit()

    token_b = create_access_token(data={"sub": user_b.id, "email": user_b.email, "org_id": org_b.id})
    headers_b = {"Authorization": f"Bearer {token_b}"}

    # Tenant B tries to generate prompts for Brand A -> 404
    gen_res = await client.post(
        f"/api/brands/{brand_a.id}/prompts/generate",
        json={"prompt_count": 5},
        headers=headers_b
    )
    assert gen_res.status_code == 404

    # Tenant B tries to scan Brand A -> 404
    scan_res = await client.post(
        f"/api/brands/{brand_a.id}/visibility/scans",
        json={"provider": "mock"},
        headers=headers_b
    )
    assert scan_res.status_code == 404
