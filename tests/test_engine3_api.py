"""Integration and API tests for Engine 3: AI Visibility Evaluator."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import VisibilityScan, VisibilityResult, PromptCandidate, PromptRun
from app.evaluator.service import VisibilityEvaluatorService


@pytest.mark.asyncio
async def test_create_visibility_scan_success(client: AsyncClient, profiled_brand, test_db_session: AsyncSession):
    """Verify initiating an AI Visibility scan on approved prompts and validating results."""
    # 1. Generate prompts using Engine 2
    p_gen_res = await client.post(f"/api/brands/{profiled_brand.id}/prompts/generate", json={
        "prompt_count": 5,
        "force_regenerate": True
    })
    assert p_gen_res.status_code == 202

    # 2. Initiate Visibility Scan using Mock Provider
    scan_res = await client.post(f"/api/brands/{profiled_brand.id}/visibility/scans", json={
        "provider": "mock",
        "max_prompts": 5,
        "force_rescan": True
    })
    assert scan_res.status_code == 202
    scan_data = scan_res.json()
    scan_id = scan_data["id"]
    assert scan_data["brand_id"] == profiled_brand.id
    assert scan_data["provider"] == "mock"
    assert scan_data["prompts_selected"] > 0

    # 3. Execute scan directly with the test db session to ensure synchronous test completion
    await VisibilityEvaluatorService.execute_scan(scan_id, db=test_db_session)

    # 4. Verify scan completed successfully with valid scores
    status_res = await client.get(f"/api/brands/{profiled_brand.id}/visibility/scans/{scan_id}")
    assert status_res.status_code == 200
    final_scan = status_res.json()
    assert final_scan["status"] == "completed"
    assert final_scan["prompts_completed"] > 0
    assert final_scan["visibility_score"] is not None
    assert final_scan["mention_rate"] is not None
    assert final_scan["duration_seconds"] is not None

    # 5. Check scan detailed results endpoint
    detail_res = await client.get(f"/api/brands/{profiled_brand.id}/visibility/scans/{scan_id}/results")
    assert detail_res.status_code == 200
    detail_data = detail_res.json()
    assert len(detail_data["results"]) == final_scan["prompts_completed"]

    first_result = detail_data["results"][0]
    assert first_result["scan_id"] == scan_id
    assert first_result["execution_status"] == "success"
    assert first_result["raw_response_text"] is not None
    assert first_result["recommendation_status"] in ("recommended", "neutral_mention", "not_recommended", "not_mentioned", "unknown")


@pytest.mark.asyncio
async def test_create_visibility_scan_rejects_unapproved_prompts(client: AsyncClient, profiled_brand, test_db_session: AsyncSession):
    """Verify attempting to scan an unapproved prompt raises 400 error."""
    # Insert one approved prompt and one unapproved prompt
    p_run = PromptRun(brand_id=profiled_brand.id, profile_version=1, status="completed")
    test_db_session.add(p_run)
    await test_db_session.flush()

    cand_approved = PromptCandidate(
        brand_id=profiled_brand.id,
        prompt_run_id=p_run.id,
        profile_version=1,
        text="Approved prompt question",
        normalized_text="approved prompt question",
        category="discovery",
        is_approved=True
    )
    cand_unapproved = PromptCandidate(
        brand_id=profiled_brand.id,
        prompt_run_id=p_run.id,
        profile_version=1,
        text="Unapproved prompt question",
        normalized_text="unapproved prompt question",
        category="discovery",
        is_approved=False
    )
    test_db_session.add_all([cand_approved, cand_unapproved])
    await test_db_session.commit()
    unapproved_id = cand_unapproved.id

    # Request scan specifically for the unapproved prompt ID
    scan_res = await client.post(f"/api/brands/{profiled_brand.id}/visibility/scans", json={
        "prompt_ids": [unapproved_id]
    })
    assert scan_res.status_code == 400
    assert "not approved" in scan_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_create_visibility_scan_rejects_nonexistent_brand(client: AsyncClient):
    """Verify requesting a scan for a nonexistent brand returns 404."""
    fake_id = "00000000-0000-0000-0000-000000000000"
    scan_res = await client.post(f"/api/brands/{fake_id}/visibility/scans", json={})
    assert scan_res.status_code == 404
    assert scan_res.json()["detail"] == "Brand not found."


@pytest.mark.asyncio
async def test_create_visibility_scan_fails_on_empty_approved_prompts(client: AsyncClient, profiled_brand):
    """Verify requesting a scan when a brand has 0 approved prompts returns 400."""
    # profiled_brand has no prompts generated yet
    scan_res = await client.post(f"/api/brands/{profiled_brand.id}/visibility/scans", json={})
    assert scan_res.status_code == 400
    assert "no approved prompts" in scan_res.json()["detail"].lower()


@pytest.mark.asyncio
async def test_list_visibility_scans_historical(client: AsyncClient, profiled_brand):
    """Verify retrieving scan history for a brand."""
    list_res = await client.get(f"/api/brands/{profiled_brand.id}/visibility/scans")
    assert list_res.status_code == 200
    assert list_res.json()["total"] == 0
    assert list_res.json()["items"] == []


@pytest.mark.asyncio
async def test_tenant_isolation_scan_access(client: AsyncClient, profiled_brand, test_db_session: AsyncSession):
    """Verify tenant isolation: Brand A cannot access Brand B's scan records."""
    # Create scan for profiled_brand (Brand A) directly in DB
    scan_a = VisibilityScan(
        brand_id=profiled_brand.id,
        profile_version=1,
        status="completed",
        provider="mock",
        model_name="mock-evaluator",
        prompts_selected=1
    )
    test_db_session.add(scan_a)
    await test_db_session.commit()
    await test_db_session.refresh(scan_a)

    other_brand_id = "11111111-2222-3333-4444-555555555555"

    # Try to access Brand A's scan using a different brand ID route
    leak_res = await client.get(f"/api/brands/{other_brand_id}/visibility/scans/{scan_a.id}")
    assert leak_res.status_code == 404
    assert "not found" in leak_res.json()["detail"].lower()

    leak_detail_res = await client.get(f"/api/brands/{other_brand_id}/visibility/scans/{scan_a.id}/results")
    assert leak_detail_res.status_code == 404


@pytest.mark.asyncio
async def test_list_all_brands(client: AsyncClient, profiled_brand):
    """Verify GET /api/brands returns all onboarded brands."""
    res = await client.get("/api/brands")
    assert res.status_code == 200
    brands = res.json()
    assert isinstance(brands, list)
    assert any(b["id"] == profiled_brand.id for b in brands)

