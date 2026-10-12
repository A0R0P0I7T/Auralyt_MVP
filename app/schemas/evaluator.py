"""Pydantic schemas for Engine 3: AI Visibility Evaluator."""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class VisibilityScanCreateRequest(BaseModel):
    """Payload to initiate an AI Visibility scan."""
    prompt_ids: Optional[List[str]] = Field(default=None, description="Specific approved prompt IDs to scan. Defaults to all approved prompts.")
    provider: Optional[str] = Field(default="mock", description="AI Provider to query: 'mock' or 'gemini'")
    model_name: Optional[str] = Field(default=None, description="Model identifier override")
    force_rescan: bool = Field(default=False, description="Bypass cache/idempotency and execute fresh scan")
    max_prompts: Optional[int] = Field(default=20, ge=1, le=50, description="Max prompts to evaluate in this scan run")


class VisibilityResultResponse(BaseModel):
    """Detailed evaluation result for a single prompt query."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    scan_id: str
    brand_id: str
    prompt_id: str
    prompt_text: str
    provider: str
    model_name: str
    execution_status: str
    raw_response_text: Optional[str] = None
    latency_ms: Optional[int] = None
    tokens_used: Optional[int] = None
    error_details: Optional[str] = None

    # Structured Evaluation
    brand_mentioned: bool
    mention_context: Optional[str] = None
    recommendation_status: str
    competitor_mentions: List[str] = Field(default_factory=list)
    comparative_position: str
    citations: List[str] = Field(default_factory=list)
    provider_citations: List[str] = Field(default_factory=list)
    response_citations: List[str] = Field(default_factory=list)
    sentiment_score: Optional[float] = None
    visibility_rank: Optional[int] = None
    evaluation_reasoning: Optional[str] = None
    created_at: datetime


class VisibilityScanResponse(BaseModel):
    """Summary of an AI Visibility scan run."""
    model_config = ConfigDict(from_attributes=True)

    id: str
    brand_id: str
    profile_version: int
    status: str
    provider: str
    model_name: str
    prompts_selected: int
    prompts_completed: int
    prompts_failed: int

    visibility_score: Optional[float] = None
    mention_rate: Optional[float] = None
    recommendation_rate: Optional[float] = None
    average_position: Optional[float] = None
    total_tokens_used: Optional[int] = None
    duration_seconds: Optional[float] = None
    error_summary: Optional[str] = None
    created_at: datetime
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None


class VisibilityScanDetailResponse(BaseModel):
    """Detailed scan response including full list of prompt evaluation results."""
    scan: VisibilityScanResponse
    results: List[VisibilityResultResponse] = Field(default_factory=list)


class VisibilityScanListResponse(BaseModel):
    """List of historical visibility scans for a brand."""
    items: List[VisibilityScanResponse]
    total: int
