"""Targeted regression tests for Frontend Integration and Cross-Engine Contracts."""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.db.models import Brand, BrandFact, PromptCandidate, PromptRun, VisibilityScan, VisibilityResult
from app.evaluator.service import VisibilityEvaluatorService
from app.prompts.service import PromptIntelligenceService


@pytest.mark.asyncio
async def test_prompt_generation_response_contract(client: AsyncClient, profiled_brand):
    """
    Verify POST /api/brands/{id}/prompts/generate contract expected by app.js:
    Returns run_id, status, prompts_generated, and profile_version.
    Prevents TypeError where app.js formerly accessed undefined 'data.id'.
    """
    res = await client.post(f"/api/brands/{profiled_brand.id}/prompts/generate", json={
        "prompt_count": 5,
        "force_regenerate": True
    })
    assert res.status_code == 202
    data = res.json()
    assert "run_id" in data
    assert data["run_id"] is not None
    assert data["brand_id"] == profiled_brand.id
    assert data["status"] in ("completed", "pending")
    assert isinstance(data["prompts_generated"], int)
    assert data["prompts_generated"] > 0
    assert "profile_version" in data
    assert data["profile_version"] >= 1


@pytest.mark.asyncio
async def test_prompt_patch_approval_contract(client: AsyncClient, profiled_brand):
    """
    Verify PATCH /api/prompts/{prompt_id} allows editing approval, archiving, and text.
    Matches frontend togglePromptApproval, archivePrompt, and handleSavePromptEdit.
    """
    # 1. Generate prompts with minimum allowed count 5
    gen_res = await client.post(f"/api/brands/{profiled_brand.id}/prompts/generate", json={
        "prompt_count": 5,
        "force_regenerate": True
    })
    assert gen_res.status_code == 202

    # 2. Get prompt list
    list_res = await client.get(f"/api/brands/{profiled_brand.id}/prompts")
    assert list_res.status_code == 200
    prompts = list_res.json()["items"]
    assert len(prompts) > 0
    target_prompt = prompts[0]

    # 3. Toggle approval
    initial_approval = target_prompt["is_approved"]
    patch_res = await client.patch(f"/api/prompts/{target_prompt['id']}", json={
        "is_approved": not initial_approval
    })
    assert patch_res.status_code == 200
    updated = patch_res.json()
    assert updated["is_approved"] == (not initial_approval)

    # 4. Edit prompt text
    edit_res = await client.patch(f"/api/prompts/{target_prompt['id']}", json={
        "text": "How does Linear compare to Jira for agile sprint planning?"
    })
    assert edit_res.status_code == 200
    assert edit_res.json()["text"] == "How does Linear compare to Jira for agile sprint planning?"
    assert edit_res.json()["user_edited"] is True


@pytest.mark.asyncio
async def test_brand_fact_patch_contract(client: AsyncClient, profiled_brand, test_db_session: AsyncSession):
    """
    Verify PATCH /api/brands/{brand_id}/facts/{fact_id} allows confirming or rejecting facts.
    Matches toggleConfirmFact and toggleRejectFact in app.js.
    """
    # Retrieve an existing fact
    fact_q = await test_db_session.execute(
        select(BrandFact).where(BrandFact.brand_id == profiled_brand.id).limit(1)
    )
    fact = fact_q.scalars().first()
    assert fact is not None

    # Test Confirming
    res_conf = await client.patch(f"/api/brands/{profiled_brand.id}/facts/{fact.id}", json={
        "user_confirmed": True,
        "is_rejected": False
    })
    assert res_conf.status_code == 200
    assert res_conf.json()["user_confirmed"] is True
    assert res_conf.json()["is_rejected"] is False

    # Test Rejecting
    res_rej = await client.patch(f"/api/brands/{profiled_brand.id}/facts/{fact.id}", json={
        "is_rejected": True,
        "user_confirmed": False
    })
    assert res_rej.status_code == 200
    assert res_rej.json()["is_rejected"] is True
    assert res_rej.json()["user_confirmed"] is False


@pytest.mark.asyncio
async def test_rejected_fact_exclusion_from_engine2(client: AsyncClient, profiled_brand, test_db_session: AsyncSession):
    """
    Verify that rejected facts are completely excluded from downstream Engine 2 generation.
    """
    facts_q = await test_db_session.execute(
        select(BrandFact).where(BrandFact.brand_id == profiled_brand.id)
    )
    all_facts = facts_q.scalars().all()
    assert len(all_facts) >= 2

    # Reject all facts except the first one
    active_fact = all_facts[0]
    rejected_facts = all_facts[1:]
    rejected_ids = set()
    for f in rejected_facts:
        f.is_rejected = True
        rejected_ids.add(f.id)
    await test_db_session.commit()

    run, prompts = await PromptIntelligenceService.generate_prompts(
        brand_id=profiled_brand.id,
        prompt_count=5,
        force_regenerate=True,
        db=test_db_session
    )
    assert run.status == "completed"
    assert len(prompts) > 0

    # Verify no prompt references any of the rejected fact IDs
    for p in prompts:
        for f_id in p.provenance_fact_ids:
            assert f_id not in rejected_ids, f"Rejected fact {f_id} was referenced in prompt provenance!"


@pytest.mark.asyncio
async def test_visibility_scans_history_and_profile_version(client: AsyncClient, profiled_brand, test_db_session: AsyncSession):
    """
    Verify GET /api/brands/{brand_id}/visibility/scans returns items containing
    profile_version, status, provider, and metrics for historical selection in frontend.
    """
    # Ensure prompts exist and are approved
    await client.post(f"/api/brands/{profiled_brand.id}/prompts/generate", json={
        "prompt_count": 5,
        "force_regenerate": True
    })

    # Trigger scan 1
    scan1_res = await client.post(f"/api/brands/{profiled_brand.id}/visibility/scans", json={
        "provider": "mock",
        "max_prompts": 5,
        "force_rescan": True
    })
    assert scan1_res.status_code == 202
    scan1_id = scan1_res.json()["id"]
    await VisibilityEvaluatorService.execute_scan(scan1_id, db=test_db_session)

    # Fetch scans list
    history_res = await client.get(f"/api/brands/{profiled_brand.id}/visibility/scans")
    assert history_res.status_code == 200
    data = history_res.json()
    assert "items" in data
    assert len(data["items"]) >= 1

    item = data["items"][0]
    assert "id" in item
    assert "profile_version" in item
    assert item["profile_version"] >= 1
    assert "provider" in item
    assert item["provider"] == "mock"
    assert "visibility_score" in item
    assert item["visibility_score"] is not None


@pytest.mark.asyncio
async def test_visibility_results_citation_separation(client: AsyncClient, profiled_brand, test_db_session: AsyncSession):
    """
    Verify scan results contract separates provider_citations from response_citations.
    """
    # Create scan and execute
    await client.post(f"/api/brands/{profiled_brand.id}/prompts/generate", json={
        "prompt_count": 5,
        "force_regenerate": True
    })
    scan_res = await client.post(f"/api/brands/{profiled_brand.id}/visibility/scans", json={
        "provider": "mock",
        "max_prompts": 5,
        "force_rescan": True
    })
    assert scan_res.status_code == 202
    scan_id = scan_res.json()["id"]
    await VisibilityEvaluatorService.execute_scan(scan_id, db=test_db_session)

    # Inspect results
    detail_res = await client.get(f"/api/brands/{profiled_brand.id}/visibility/scans/{scan_id}/results")
    assert detail_res.status_code == 200
    results = detail_res.json()["results"]
    assert len(results) > 0
    first = results[0]
    assert "provider_citations" in first
    assert isinstance(first["provider_citations"], list)
    assert "response_citations" in first
    assert isinstance(first["response_citations"], list)


@pytest.mark.asyncio
async def test_null_metrics_serialization(client: AsyncClient, profiled_brand, test_db_session: AsyncSession):
    """
    Verify that pending/running scans preserve null metrics without coercing to 0.0 or 0%.
    """
    scan = VisibilityScan(
        brand_id=profiled_brand.id,
        profile_version=1,
        status="pending",
        provider="mock",
        model_name="mock-deterministic",
        prompts_selected=5,
        prompts_completed=0,
        prompts_failed=0,
        visibility_score=None,
        mention_rate=None,
        recommendation_rate=None,
        average_position=None
    )
    test_db_session.add(scan)
    await test_db_session.commit()
    await test_db_session.refresh(scan)

    res = await client.get(f"/api/brands/{profiled_brand.id}/visibility/scans/{scan.id}")
    assert res.status_code == 200
    data = res.json()
    assert data["visibility_score"] is None
    assert data["mention_rate"] is None
    assert data["recommendation_rate"] is None
    assert data["average_position"] is None


@pytest.mark.asyncio
async def test_invalid_brand_access_rejection(client: AsyncClient):
    """Verify requesting non-existent brand returns 404 across Engine 2 & 3 endpoints."""
    bad_id = "00000000-0000-0000-0000-000000000000"
    p_gen = await client.post(f"/api/brands/{bad_id}/prompts/generate", json={"prompt_count": 5})
    assert p_gen.status_code == 404

    p_list = await client.get(f"/api/brands/{bad_id}/prompts")
    assert p_list.status_code == 404

    v_scans = await client.get(f"/api/brands/{bad_id}/visibility/scans")
    assert v_scans.status_code == 404

    v_create = await client.post(f"/api/brands/{bad_id}/visibility/scans", json={"provider": "mock"})
    assert v_create.status_code == 404
