"""Tests for Engine 2 Prompt Review Lifecycle and Engine 3 handoff verification."""
import pytest
import pytest_asyncio
from httpx import AsyncClient
from app.db.models import Brand, ProfileRun, BrandFact, PromptCandidate
from app.evaluator.service import VisibilityEvaluatorService


@pytest_asyncio.fixture
async def reviewable_brand(test_db_session, test_org):
    """Fixture providing a brand with ground-truth facts for review testing."""
    brand = Brand(
        domain="salescloud-review.io",
        business_name="SalesCloud",
        industry="SaaS",
        target_market="B2B",
        language="en",
        organization_id=test_org.id,
        profile_version=1,
    )
    test_db_session.add(brand)
    await test_db_session.flush()

    run = ProfileRun(
        brand_id=brand.id,
        status="completed",
        page_limit=1,
        pages_discovered=1,
        pages_succeeded=1,
    )
    test_db_session.add(run)
    await test_db_session.flush()

    fact = BrandFact(
        brand_id=brand.id,
        profile_version=1,
        fact_type="business_overview",
        fact_value={"description": "B2B sales intelligence and CRM enrichment platform."},
        confidence=0.95,
        user_confirmed=True,
        source_url="https://salescloud-review.io",
        evidence_snippet="SalesCloud powers modern B2B prospecting.",
    )
    test_db_session.add(fact)
    await test_db_session.commit()
    return brand


@pytest.mark.asyncio
async def test_prompt_review_endpoint_lifecycle(client: AsyncClient, reviewable_brand: Brand, test_db_session):
    """Verify single prompt review lifecycle: proposed -> approved/rejected with text edits."""
    # 1. Generate candidates
    gen_res = await client.post(
        f"/api/brands/{reviewable_brand.id}/prompts/generate",
        json={"prompt_count": 8, "force_regenerate": True}
    )
    assert gen_res.status_code == 202

    # 2. List prompts
    list_res = await client.get(f"/api/brands/{reviewable_brand.id}/prompts")
    assert list_res.status_code == 200
    items = list_res.json()["items"]
    assert len(items) >= 5
    target_prompt = items[0]
    prompt_id = target_prompt["id"]

    # 3. Review: edit text and approve
    review_res = await client.put(
        f"/api/brands/{reviewable_brand.id}/prompts/{prompt_id}/review",
        json={
            "lifecycle_status": "approved",
            "text": "What are the best B2B sales intelligence platforms in 2026?",
            "review_notes": "Reviewed and tailored for sales query benchmark"
        }
    )
    assert review_res.status_code == 200
    data = review_res.json()
    assert data["lifecycle_status"] == "approved"
    assert data["is_approved"] is True
    assert data["text"] == "What are the best B2B sales intelligence platforms in 2026?"
    assert data["user_edited"] is True
    assert data["review_notes"] == "Reviewed and tailored for sales query benchmark"

    # 4. Review: reject another prompt
    reject_target = items[1]
    reject_res = await client.put(
        f"/api/brands/{reviewable_brand.id}/prompts/{reject_target['id']}/review",
        json={
            "lifecycle_status": "rejected",
            "review_notes": "Out of scope query"
        }
    )
    assert reject_res.status_code == 200
    rej_data = reject_res.json()
    assert rej_data["lifecycle_status"] == "rejected"
    assert rej_data["is_approved"] is False


@pytest.mark.asyncio
async def test_prompt_batch_review_endpoint(client: AsyncClient, reviewable_brand: Brand):
    """Verify batch review endpoint approves/rejects multiple prompts."""
    # 1. Generate
    await client.post(
        f"/api/brands/{reviewable_brand.id}/prompts/generate",
        json={"prompt_count": 6, "force_regenerate": True}
    )

    # 2. Get list
    list_res = await client.get(f"/api/brands/{reviewable_brand.id}/prompts")
    items = list_res.json()["items"]
    pids = [p["id"] for p in items[:3]]

    # 3. Batch approve
    batch_res = await client.post(
        f"/api/brands/{reviewable_brand.id}/prompts/batch-review",
        json={
            "prompt_ids": pids,
            "lifecycle_status": "approved",
            "review_notes": "Batch verified by QA"
        }
    )
    assert batch_res.status_code == 200
    res_list = batch_res.json()
    assert len(res_list) == 3
    for p in res_list:
        assert p["lifecycle_status"] == "approved"
        assert p["is_approved"] is True


@pytest.mark.asyncio
async def test_engine3_handoff_rejects_unapproved_or_rejected_prompts(
    client: AsyncClient, reviewable_brand: Brand, test_db_session, monkeypatch
):
    """Verify Engine 3 accepts exactly approved prompts and rejects unapproved/rejected IDs."""
    # Generate prompts
    await client.post(
        f"/api/brands/{reviewable_brand.id}/prompts/generate",
        json={"prompt_count": 6, "force_regenerate": True}
    )

    list_res = await client.get(f"/api/brands/{reviewable_brand.id}/prompts")
    items = list_res.json()["items"]
    approved_id = items[0]["id"]
    rejected_id = items[1]["id"]

    # Explicitly approve one and reject the other
    await client.put(
        f"/api/brands/{reviewable_brand.id}/prompts/{approved_id}/review",
        json={"lifecycle_status": "approved"}
    )
    await client.put(
        f"/api/brands/{reviewable_brand.id}/prompts/{rejected_id}/review",
        json={"lifecycle_status": "rejected"}
    )

    # Attempting to start scan with the rejected prompt MUST fail
    with pytest.raises(ValueError) as excinfo:
        await VisibilityEvaluatorService.create_scan(
            brand_id=reviewable_brand.id,
            prompt_ids=[approved_id, rejected_id],
            db=test_db_session
        )
    assert "not approved" in str(excinfo.value).lower()

    # Starting scan with ONLY the approved prompt succeeds
    scan = await VisibilityEvaluatorService.create_scan(
        brand_id=reviewable_brand.id,
        prompt_ids=[approved_id],
        db=test_db_session
    )
    assert scan.id is not None
    assert scan.prompts_selected == 1
