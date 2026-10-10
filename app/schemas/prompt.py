"""Pydantic schemas for Engine 2: Prompt Intelligence."""
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class PromptGenerateRequest(BaseModel):
    prompt_count: int = Field(default=20, ge=5, le=50, description="Total number of prompts to generate")
    categories: Optional[List[str]] = Field(default=None, description="Optional filter of prompt categories to generate")
    language: Optional[str] = Field(default=None, description="Target language override (defaults to brand language)")
    force_regenerate: bool = Field(default=False, description="If True, bypasses cache and regenerates prompts for current profile version")


class PromptRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    brand_id: str
    profile_version: int
    status: str
    prompt_count_requested: int
    prompts_generated: int
    provider: str
    model_name: Optional[str] = None
    tokens_used: Optional[int] = None
    duration_seconds: Optional[float] = None
    error_summary: Optional[str] = None
    created_at: datetime
    completed_at: Optional[datetime] = None


class PromptCandidateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    brand_id: str
    prompt_run_id: str
    profile_version: int
    text: str
    category: str
    intent: str
    buying_stage: str
    target_audience: Optional[str] = None
    target_product_service: Optional[str] = None
    language: str
    provenance_fact_ids: List[str] = []
    grounding_evidence: List[str] = []
    scores: Dict[str, Any] = {}
    quality_score: float
    is_approved: bool
    is_archived: bool
    user_edited: bool
    created_at: datetime
    updated_at: datetime


class PromptUpdateRequest(BaseModel):
    text: Optional[str] = Field(default=None, min_length=5, max_length=1000)
    is_approved: Optional[bool] = None
    is_archived: Optional[bool] = None


class PromptListResponse(BaseModel):
    items: List[PromptCandidateResponse]
    total: int
    page: int
    page_size: int
    total_pages: int
    profile_version: int
    coverage_summary: Dict[str, Any] = {}


class PromptCoverageSummary(BaseModel):
    brand_id: str
    profile_version: int
    total_prompts: int
    approved_prompts: int
    archived_prompts: int
    categories: Dict[str, int]
    buying_stages: Dict[str, int]
    intents: Dict[str, int]
    average_quality_score: float
