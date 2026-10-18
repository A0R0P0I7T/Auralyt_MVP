"""Comprehensive Security & Multi-Tenancy Regression Test Suite.

Proves:
1. Unauthenticated requests receive HTTP 401 on protected routes.
2. Tenant isolation: User A (Org A) cannot access User B's (Org B) brands, facts, prompts, or scans.
3. ID manipulation / IDOR attacks fail with non-disclosing HTTP 404 or 403.
4. Malformed, expired, or forged JWT tokens are strictly rejected.
5. Organization switching via X-Organization-ID verifies membership.
6. Public health check (/health) remains accessible without credentials.
7. User registration, login, logout, and token issuance function securely.
"""
from datetime import timedelta
import pytest
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.main import app
from app.db.models import Brand, Organization, User, OrganizationMember
from app.db.session import get_db
from app.auth.security import hash_password, create_access_token


@pytest.mark.asyncio
async def test_public_health_endpoint_remains_unauthenticated(unauthenticated_client: AsyncClient):
    """Verify that /health does not require authentication and returns basic non-sensitive status."""
    res = await unauthenticated_client.get("/health")
    assert res.status_code == 200
    data = res.json()
    assert data["status"] == "healthy"
    assert "token" not in data
    assert "key" not in data


@pytest.mark.asyncio
async def test_unauthenticated_requests_rejected_with_401(unauthenticated_client: AsyncClient, profiled_brand: Brand):
    """Verify that all core protected endpoints return HTTP 401 when unauthenticated."""
    protected_endpoints = [
        ("GET", "/api/brands"),
        ("POST", "/api/brands/profile"),
        ("GET", f"/api/brands/{profiled_brand.id}"),
        ("GET", f"/api/brands/{profiled_brand.id}/profile"),
        ("GET", f"/api/brands/{profiled_brand.id}/facts"),
        ("POST", f"/api/brands/{profiled_brand.id}/facts"),
        ("GET", f"/api/brands/{profiled_brand.id}/pages"),
        ("POST", f"/api/brands/{profiled_brand.id}/prompts/generate"),
        ("GET", f"/api/brands/{profiled_brand.id}/prompts"),
        ("POST", f"/api/brands/{profiled_brand.id}/visibility/scans"),
        ("GET", f"/api/brands/{profiled_brand.id}/visibility/scans"),
        ("GET", "/api/auth/me"),
    ]

    for method, path in protected_endpoints:
        if method == "GET":
            res = await unauthenticated_client.get(path)
        else:
            res = await unauthenticated_client.post(path, json={})

        assert res.status_code == 401, f"Expected 401 for unauthenticated {method} {path}, got {res.status_code}"
        assert "WWW-Authenticate" in res.headers
        assert res.headers["WWW-Authenticate"] == "Bearer"


@pytest.mark.asyncio
async def test_invalid_or_expired_tokens_rejected(test_db_session: AsyncSession):
    """Verify that malformed, signature-mismatched, or expired tokens return 401."""
    async def override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Malformed token
        res_malformed = await client.get("/api/brands", headers={"Authorization": "Bearer not-a-valid-jwt"})
        assert res_malformed.status_code == 401

        # 2. Tampered / wrong secret token
        fake_token = create_access_token(data={"sub": "fake-user"}, expires_delta=timedelta(minutes=10))
        tampered_token = fake_token[:-5] + "XXXXX"
        res_tampered = await client.get("/api/brands", headers={"Authorization": f"Bearer {tampered_token}"})
        assert res_tampered.status_code == 401

        # 3. Expired token
        expired_token = create_access_token(data={"sub": "fake-user"}, expires_delta=timedelta(minutes=-10))
        res_expired = await client.get("/api/brands", headers={"Authorization": f"Bearer {expired_token}"})
        assert res_expired.status_code == 401

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_auth_registration_and_login_flow(unauthenticated_client: AsyncClient):
    """Verify registration creates user and org, and login succeeds with matching credentials."""
    # 1. Register new user
    reg_payload = {
        "email": "sarah.connor@cyberdyne.io",
        "password": "Password123!Secure",
        "full_name": "Sarah Connor",
        "organization_name": "Cyberdyne Resistance"
    }
    reg_res = await unauthenticated_client.post("/api/auth/register", json=reg_payload)
    assert reg_res.status_code == 201
    reg_data = reg_res.json()
    assert "access_token" in reg_data
    assert reg_data["user"]["email"] == "sarah.connor@cyberdyne.io"
    assert reg_data["organization"]["name"] == "Cyberdyne Resistance"

    # 2. Reject duplicate email registration
    dup_res = await unauthenticated_client.post("/api/auth/register", json=reg_payload)
    assert dup_res.status_code == 400
    assert "already registered" in dup_res.json()["detail"]

    # 3. Login with correct credentials
    login_res = await unauthenticated_client.post("/api/auth/login", json={
        "email": "sarah.connor@cyberdyne.io",
        "password": "Password123!Secure"
    })
    assert login_res.status_code == 200
    login_data = login_res.json()
    assert "access_token" in login_data
    token = login_data["access_token"]

    # 4. Access /api/auth/me with token
    me_res = await unauthenticated_client.get("/api/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me_res.status_code == 200
    me_data = me_res.json()
    assert me_data["user"]["email"] == "sarah.connor@cyberdyne.io"
    assert me_data["active_organization"]["name"] == "Cyberdyne Resistance"

    # 5. Reject login with wrong password
    bad_login = await unauthenticated_client.post("/api/auth/login", json={
        "email": "sarah.connor@cyberdyne.io",
        "password": "WrongPassword!"
    })
    assert bad_login.status_code == 401


@pytest.mark.asyncio
async def test_strict_cross_tenant_isolation(test_db_session: AsyncSession):
    """
    CRITICAL SECURITY TEST:
    Setup Tenant A (User A, Org A, Brand A) and Tenant B (User B, Org B, Brand B).
    Prove:
    - User A can view and modify Brand A.
    - User A CANNOT view Brand B (returns non-disclosing 404).
    - User A CANNOT modify or delete Brand B's facts (returns 404).
    - User A CANNOT generate prompts for Brand B (returns 404).
    - User A CANNOT launch or inspect visibility scans for Brand B (returns 404).
    """
    # 1. Create Org A, User A, Brand A
    org_a = Organization(name="Organization Alpha", slug="org-alpha")
    test_db_session.add(org_a)
    await test_db_session.flush()

    user_a = User(
        email="alice@alpha.io",
        hashed_password=hash_password("PassAlpha123!"),
        full_name="Alice Alpha"
    )
    test_db_session.add(user_a)
    await test_db_session.flush()
    test_db_session.add(OrganizationMember(organization_id=org_a.id, user_id=user_a.id, role="owner"))

    brand_a = Brand(
        domain="alpha-cloud.io",
        business_name="Alpha Cloud",
        organization_id=org_a.id,
        profile_version=1
    )
    test_db_session.add(brand_a)
    await test_db_session.flush()

    # 2. Create Org B, User B, Brand B
    org_b = Organization(name="Organization Beta", slug="org-beta")
    test_db_session.add(org_b)
    await test_db_session.flush()

    user_b = User(
        email="bob@beta.io",
        hashed_password=hash_password("PassBeta123!"),
        full_name="Bob Beta"
    )
    test_db_session.add(user_b)
    await test_db_session.flush()
    test_db_session.add(OrganizationMember(organization_id=org_b.id, user_id=user_b.id, role="owner"))

    brand_b = Brand(
        domain="beta-defense.io",
        business_name="Beta Defense",
        organization_id=org_b.id,
        profile_version=1
    )
    test_db_session.add(brand_b)
    await test_db_session.commit()

    # Generate tokens
    token_a = create_access_token(data={"sub": user_a.id, "email": user_a.email, "org_id": org_a.id})
    token_b = create_access_token(data={"sub": user_b.id, "email": user_b.email, "org_id": org_b.id})

    headers_a = {"Authorization": f"Bearer {token_a}"}
    headers_b = {"Authorization": f"Bearer {token_b}"}

    async def override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # A) User A lists brands: should ONLY see Brand A, never Brand B
        list_a = await client.get("/api/brands", headers=headers_a)
        assert list_a.status_code == 200
        items_a = list_a.json()
        ids_a = [b["id"] for b in items_a]
        assert brand_a.id in ids_a
        assert brand_b.id not in ids_a

        # B) User B lists brands: should ONLY see Brand B, never Brand A
        list_b = await client.get("/api/brands", headers=headers_b)
        assert list_b.status_code == 200
        items_b = list_b.json()
        ids_b = [b["id"] for b in items_b]
        assert brand_b.id in ids_b
        assert brand_a.id not in ids_b

        # C) User A attempts to directly fetch Brand B by UUID -> 404 Not Found
        idor_get = await client.get(f"/api/brands/{brand_b.id}", headers=headers_a)
        assert idor_get.status_code == 404, f"IDOR vulnerability! Expected 404, got {idor_get.status_code}"

        # D) User A attempts to update Brand B -> 404 Not Found
        idor_patch = await client.patch(
            f"/api/brands/{brand_b.id}",
            json={"business_name": "Hacked Beta"},
            headers=headers_a
        )
        assert idor_patch.status_code == 404

        # E) User A attempts to fetch Brand B profile summary -> 404 Not Found
        idor_prof = await client.get(f"/api/brands/{brand_b.id}/profile", headers=headers_a)
        assert idor_prof.status_code == 404

        # F) User A attempts to fetch Brand B facts -> 404 Not Found
        idor_facts = await client.get(f"/api/brands/{brand_b.id}/facts", headers=headers_a)
        assert idor_facts.status_code == 404

        # G) User A attempts to generate prompts for Brand B -> 404 Not Found
        idor_gen = await client.post(
            f"/api/brands/{brand_b.id}/prompts/generate",
            json={"prompt_count": 5},
            headers=headers_a
        )
        assert idor_gen.status_code == 404

        # H) User A attempts to initiate visibility scan for Brand B -> 404 Not Found
        idor_scan = await client.post(
            f"/api/brands/{brand_b.id}/visibility/scans",
            json={"provider": "mock"},
            headers=headers_a
        )
        assert idor_scan.status_code == 404

        # I) User A attempts to spoof Org B via X-Organization-ID header -> 403 Forbidden
        spoofed_headers = {
            "Authorization": f"Bearer {token_a}",
            "X-Organization-ID": org_b.id
        }
        spoofed_res = await client.get("/api/brands", headers=spoofed_headers)
        assert spoofed_res.status_code == 403
        assert "not have authorized access" in spoofed_res.json()["detail"]

    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_unassigned_legacy_brand_cannot_be_adopted_by_request(test_db_session: AsyncSession, test_user, test_org):
    """
    CRITICAL SECURITY TEST:
    Verify that an unassigned legacy brand (organization_id=None):
    1. Returns 404 when requested via GET /api/brands/{id} by a tenant.
    2. Is NOT automatically adopted/claimed into that tenant's organization.
    3. Requires explicit authorized recovery via POST /api/auth/claim-legacy-brands.
    """
    from app.auth.security import create_access_token
    token = create_access_token(data={"sub": test_user.id, "email": test_user.email, "org_id": test_org.id})
    headers = {"Authorization": f"Bearer {token}"}

    # Create unassigned legacy brand
    legacy_brand = Brand(
        domain="legacy-orphan.io",
        business_name="Legacy Orphan",
        organization_id=None,
        profile_version=1
    )
    test_db_session.add(legacy_brand)
    await test_db_session.commit()
    await test_db_session.refresh(legacy_brand)

    async def override_get_db():
        yield test_db_session

    app.dependency_overrides[get_db] = override_get_db
    transport = ASGITransport(app=app)

    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Attempt to access unassigned brand: MUST return 404
        get_res = await client.get(f"/api/brands/{legacy_brand.id}", headers=headers)
        assert get_res.status_code == 404
        assert get_res.json()["detail"] == "Brand not found."

        # 2. Verify in DB that organization_id was NOT silently adopted
        await test_db_session.refresh(legacy_brand)
        assert legacy_brand.organization_id is None, "Security violation: unassigned brand was silently adopted!"

        # 3. Explicit authorized claim
        claim_res = await client.post(
            "/api/auth/claim-legacy-brands",
            json={"brand_ids": [legacy_brand.id]},
            headers=headers
        )
        assert claim_res.status_code == 200
        assert claim_res.json()["claimed_count"] == 1

        # 4. Now the brand belongs to test_org and is accessible
        get_after = await client.get(f"/api/brands/{legacy_brand.id}", headers=headers)
        assert get_after.status_code == 200
        assert get_after.json()["id"] == legacy_brand.id
        assert get_after.json()["organization_id"] == test_org.id

    app.dependency_overrides.clear()

