from datetime import datetime
from typing import Optional, Any
from pydantic import BaseModel, Field, ConfigDict


class BrandFactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    brand_id: str
    profile_version: int
    fact_key: Optional[str] = None
    fact_type: str
    fact_value: Any
    source_page_id: Optional[str] = None
    source_url: Optional[str] = None
    evidence_snippet: Optional[str] = None
    supporting_evidence: Optional[list[dict]] = Field(default_factory=list)
    extraction_method: str
    confidence: float
    user_confirmed: bool
    is_rejected: bool = False
    is_superseded: bool = False
    is_stale: bool = False
    last_seen_at: Optional[datetime] = None
    superseded_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime



class BrandFactCreateRequest(BaseModel):
    fact_type: str = Field(..., description="Category of fact (e.g., product_service, use_case, target_audience)")
    fact_value: Any = Field(..., description="The factual statement or structured data")
    source_url: Optional[str] = None
    evidence_snippet: Optional[str] = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    user_confirmed: bool = Field(default=True, description="Manual facts are confirmed by default")
    is_rejected: bool = Field(default=False, description="Whether the fact has been rejected")


class BrandFactUpdateRequest(BaseModel):
    fact_value: Optional[Any] = None
    user_confirmed: Optional[bool] = None
    is_rejected: Optional[bool] = None
