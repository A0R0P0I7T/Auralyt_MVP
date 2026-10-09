from datetime import datetime
from typing import Optional
from pydantic import BaseModel, HttpUrl, Field, ConfigDict


class BrandOnboardRequest(BaseModel):
    website_url: str = Field(..., description="The primary website URL to profile (e.g., https://example.com)")
    business_name: Optional[str] = Field(None, description="Optional company or business name")
    industry: Optional[str] = Field(None, description="Optional industry or category (e.g., SaaS, E-commerce)")
    target_market: Optional[str] = Field(None, description="Optional target market/country (e.g., US, Global, India)")
    language: Optional[str] = Field(None, description="Optional preferred website language (e.g., en)")
    page_limit: Optional[int] = Field(default=30, ge=1, le=50, description="Max pages to crawl (1-50, default 30)")


class BrandUpdateRequest(BaseModel):
    business_name: Optional[str] = None
    industry: Optional[str] = None
    target_market: Optional[str] = None
    language: Optional[str] = None


class BrandResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    organization_id: Optional[str] = None
    domain: str
    business_name: str
    industry: Optional[str] = None
    target_market: Optional[str] = None
    language: Optional[str] = None
    profile_version: int
    created_at: datetime
    updated_at: datetime

