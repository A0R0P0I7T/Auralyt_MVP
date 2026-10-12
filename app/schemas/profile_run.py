from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, ConfigDict


class ProfileRunCreateRequest(BaseModel):
    page_limit: Optional[int] = Field(default=30, ge=1, le=50, description="Max pages to crawl for this run")


class ProfileRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    brand_id: str
    profile_version: int
    status: str
    started_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    duration_seconds: Optional[float] = None
    page_limit: int
    pages_discovered: int
    pages_attempted: int
    pages_succeeded: int
    pages_skipped: int
    pages_failed: int
    warnings: List[str]
    error_summary: Optional[str] = None
    crawl_summary: Optional[Dict[str, Any]] = None
