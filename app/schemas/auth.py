"""Pydantic schemas for authentication, users, and organizations."""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field, EmailStr, ConfigDict


class UserRegisterRequest(BaseModel):
    """Payload to register a new user and organization."""
    email: EmailStr = Field(description="User primary email address")
    password: str = Field(min_length=8, max_length=128, description="User password (min 8 characters)")
    full_name: Optional[str] = Field(default=None, max_length=255, description="Full name")
    organization_name: Optional[str] = Field(default=None, max_length=255, description="Initial organization name")


class UserLoginRequest(BaseModel):
    """Payload for user login."""
    email: str = Field(description="Registered email address")
    password: str = Field(description="User password")


class OrganizationResponse(BaseModel):
    """Organization details with caller's role."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    role: str = "member"
    created_at: datetime


class UserResponse(BaseModel):
    """Safe user profile response (excluding hashed_password)."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    full_name: Optional[str] = None
    is_active: bool
    is_superuser: bool
    created_at: datetime


class TokenResponse(BaseModel):
    """Authentication token response."""
    access_token: str
    token_type: str = "bearer"
    user: UserResponse
    organization: OrganizationResponse


class AuthMeResponse(BaseModel):
    """Current authenticated user profile and available organizations."""
    user: UserResponse
    organizations: List[OrganizationResponse]
    active_organization: OrganizationResponse


class ClaimLegacyRequest(BaseModel):
    """Payload to claim legacy unassigned brands into the caller's active organization."""
    brand_ids: Optional[List[str]] = Field(default=None, description="Specific brand IDs to claim. If empty, claims all unassigned brands.")
