"""FastAPI Dependencies for Authentication, Tenant Isolation, and Ownership Verification."""
from typing import Optional, List, Tuple
from fastapi import Request, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.db.models import User, Organization, OrganizationMember, Brand
from app.auth.security import decode_access_token


async def get_token_from_request(request: Request) -> Optional[str]:
    """
    Extract authentication token from 'Authorization: Bearer <token>' header
    or fallback to the secure HTTP-Only cookie.
    """
    auth_header = request.headers.get("Authorization")
    if auth_header and auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1].strip()
        if token:
            return token

    cookie_token = request.cookies.get(settings.AUTH_COOKIE_NAME)
    if cookie_token:
        return cookie_token.strip()

    return None


async def get_current_user(
    request: Request,
    db: AsyncSession = Depends(get_db)
) -> User:
    """
    Validate caller's token and retrieve the active User record.
    Returns HTTP 401 with 'WWW-Authenticate: Bearer' header if invalid or missing.
    """
    token = await get_token_from_request(request)
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authentication required. Please provide a valid Bearer token or session cookie.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    payload = decode_access_token(token)
    if not payload or not payload.get("sub"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired authentication credentials.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    user_id = payload["sub"]
    user = await db.get(User, user_id)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Authenticated user no longer exists.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User account is deactivated."
        )

    return user


async def get_current_org(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
) -> Organization:
    """
    Derive the caller's authorized organization strictly from verified database records.
    Never trusts client-supplied organization IDs as proof of authorization.
    """
    stmt = (
        select(Organization, OrganizationMember.role)
        .join(OrganizationMember, Organization.id == OrganizationMember.organization_id)
        .where(OrganizationMember.user_id == current_user.id)
    )
    res = await db.execute(stmt)
    user_memberships = res.all()

    if not user_memberships:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="User does not belong to any active organization."
        )

    # If caller explicitly requested a specific organization via header, verify membership
    requested_org_id = request.headers.get("X-Organization-ID")
    if requested_org_id:
        for org, role in user_memberships:
            if org.id == requested_org_id:
                return org
        # Reject unauthorized organization selection
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: You do not have authorized access to the requested organization."
        )

    # Default to caller's primary / first organization
    return user_memberships[0][0]


async def verify_brand_access(
    brand_id: str,
    db: AsyncSession,
    current_org: Organization
) -> Brand:
    """
    Enforce tenant boundary: Verify the requested brand belongs to the caller's authorized organization.
    Returns non-disclosing HTTP 404 if the brand does not exist or belongs to another organization,
    preventing cross-tenant resource enumeration.
    """
    brand = await db.get(Brand, brand_id)
    if not brand:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found.")

    if brand.organization_id != current_org.id:
        # Non-disclosing 404 to avoid leaking existence of other tenants' brands or unassigned legacy brands.
        # Unassigned legacy brands cannot be claimed merely by requesting them.
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Brand not found.")

    return brand
