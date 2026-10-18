"""API Endpoints for Authentication, Registration, Session, and Tenant Management."""
import re
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Response, Request, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.db.session import get_db
from app.db.models import User, Organization, OrganizationMember, Brand
from app.schemas.auth import (
    UserRegisterRequest,
    UserLoginRequest,
    TokenResponse,
    UserResponse,
    OrganizationResponse,
    AuthMeResponse,
    ClaimLegacyRequest,
)
from app.auth.security import hash_password, verify_password, create_access_token
from app.auth.dependencies import get_current_user, get_current_org

router = APIRouter(prefix="/auth", tags=["Authentication & Multi-Tenancy"])


def _generate_slug(text: str) -> str:
    """Generate a clean URL-friendly slug."""
    slug = re.sub(r'[^a-zA-Z0-9]+', '-', text.lower()).strip('-')
    return slug[:80] or "org"


def _set_auth_cookie(response: Response, token: str) -> None:
    """Attach secure session cookie to response."""
    response.set_cookie(
        key=settings.AUTH_COOKIE_NAME,
        value=token,
        httponly=True,
        secure=settings.AUTH_COOKIE_SECURE,
        samesite=settings.AUTH_COOKIE_SAMESITE,
        max_age=settings.ACCESS_TOKEN_EXPIRE_MINUTES * 60,
        path="/"
    )


@router.post(
    "/register",
    response_model=TokenResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new user account and initial organization"
)
async def register(
    payload: UserRegisterRequest,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """
    Creates a new user, hashes password securely with bcrypt,
    scaffolds an initial organization, establishes owner membership,
    and returns a signed JWT access token.
    """
    email_clean = payload.email.strip().lower()

    # Check if email already registered
    existing_q = await db.execute(select(User).where(User.email == email_clean))
    if existing_q.scalars().first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address is already registered."
        )

    # Create User
    user = User(
        email=email_clean,
        hashed_password=hash_password(payload.password),
        full_name=payload.full_name.strip() if payload.full_name else None,
        is_active=True,
        is_superuser=False
    )
    db.add(user)
    await db.flush()

    # Create initial Organization
    org_name = (payload.organization_name or "").strip() or f"{user.full_name or email_clean.split('@')[0]}'s Org"
    base_slug = _generate_slug(org_name)
    slug = base_slug

    # Ensure slug uniqueness
    slug_q = await db.execute(select(Organization).where(Organization.slug == slug))
    if slug_q.scalars().first():
        slug = f"{base_slug}-{user.id[:6]}"

    org = Organization(
        name=org_name,
        slug=slug
    )
    db.add(org)
    await db.flush()

    # Create Membership as owner
    membership = OrganizationMember(
        organization_id=org.id,
        user_id=user.id,
        role="owner"
    )
    db.add(membership)
    await db.commit()
    await db.refresh(user)
    await db.refresh(org)

    # Issue JWT token
    token = create_access_token(data={"sub": user.id, "email": user.email, "org_id": org.id})
    _set_auth_cookie(response, token)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
        organization=OrganizationResponse(
            id=org.id,
            name=org.name,
            slug=org.slug,
            role="owner",
            created_at=org.created_at
        )
    )


@router.post(
    "/login",
    response_model=TokenResponse,
    summary="Authenticate with email and password"
)
async def login(
    payload: UserLoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    """
    Authenticates user credentials, sets an HTTP-Only session cookie,
    and returns a signed JWT access token.
    """
    email_clean = payload.email.strip().lower()

    stmt = select(User).where(User.email == email_clean)
    res = await db.execute(stmt)
    user = res.scalars().first()

    if not user or not verify_password(payload.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password.",
            headers={"WWW-Authenticate": "Bearer"}
        )

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Your account has been deactivated. Please contact support."
        )

    # Fetch user memberships
    m_stmt = (
        select(Organization, OrganizationMember.role)
        .join(OrganizationMember, Organization.id == OrganizationMember.organization_id)
        .where(OrganizationMember.user_id == user.id)
    )
    m_res = await db.execute(m_stmt)
    memberships = m_res.all()

    if not memberships:
        # User has no org, create default one
        org = Organization(
            name=f"{user.full_name or email_clean.split('@')[0]}'s Org",
            slug=f"org-{user.id[:8]}"
        )
        db.add(org)
        await db.flush()
        m = OrganizationMember(organization_id=org.id, user_id=user.id, role="owner")
        db.add(m)
        await db.commit()
        await db.refresh(org)
        primary_org = org
        primary_role = "owner"
    else:
        primary_org, primary_role = memberships[0]

    token = create_access_token(data={"sub": user.id, "email": user.email, "org_id": primary_org.id})
    _set_auth_cookie(response, token)

    return TokenResponse(
        access_token=token,
        token_type="bearer",
        user=UserResponse.model_validate(user),
        organization=OrganizationResponse(
            id=primary_org.id,
            name=primary_org.name,
            slug=primary_org.slug,
            role=primary_role,
            created_at=primary_org.created_at
        )
    )


@router.post(
    "/logout",
    summary="Clear session authentication cookie"
)
async def logout(response: Response):
    """Logs out user by clearing the HTTP-Only authentication cookie."""
    response.delete_cookie(
        key=settings.AUTH_COOKIE_NAME,
        path="/"
    )
    return {"message": "Logged out successfully."}


@router.get(
    "/me",
    response_model=AuthMeResponse,
    summary="Get current user profile and authorized organizations"
)
async def get_me(
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
):
    """Inspects caller identity and all organizations they are authorized to access."""
    stmt = (
        select(Organization, OrganizationMember.role)
        .join(OrganizationMember, Organization.id == OrganizationMember.organization_id)
        .where(OrganizationMember.user_id == current_user.id)
    )
    res = await db.execute(stmt)
    memberships = res.all()

    org_responses = [
        OrganizationResponse(
            id=o.id,
            name=o.name,
            slug=o.slug,
            role=role,
            created_at=o.created_at
        )
        for o, role in memberships
    ]

    active_role = "member"
    for o, role in memberships:
        if o.id == current_org.id:
            active_role = role
            break

    return AuthMeResponse(
        user=UserResponse.model_validate(current_user),
        organizations=org_responses,
        active_organization=OrganizationResponse(
            id=current_org.id,
            name=current_org.name,
            slug=current_org.slug,
            role=active_role,
            created_at=current_org.created_at
        )
    )


@router.post(
    "/claim-legacy-brands",
    summary="Claim unassigned legacy brands into caller's active organization"
)
async def claim_legacy_brands(
    payload: Optional[ClaimLegacyRequest] = None,
    current_user: User = Depends(get_current_user),
    current_org: Organization = Depends(get_current_org),
    db: AsyncSession = Depends(get_db)
):
    """
    Safely assigns pre-existing legacy brands (where organization_id IS NULL)
    to the authenticated caller's active organization.
    """
    stmt = select(Brand).where(Brand.organization_id.is_(None))
    if payload and payload.brand_ids:
        stmt = stmt.where(Brand.id.in_(payload.brand_ids))

    res = await db.execute(stmt)
    unassigned_brands = res.scalars().all()

    count = 0
    for b in unassigned_brands:
        b.organization_id = current_org.id
        count += 1

    await db.commit()
    return {
        "message": f"Successfully claimed {count} legacy brand(s) into organization '{current_org.name}'.",
        "claimed_count": count
    }
