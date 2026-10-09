from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, ConfigDict


class CrawledPageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    brand_id: str
    profile_run_id: str
    requested_url: str
    final_url: str
    canonical_url: Optional[str] = None
    http_status: int
    title: Optional[str] = None
    meta_description: Optional[str] = None
    headings: Dict[str, List[str]]
    extracted_text: str
    structured_data: List[Dict[str, Any]]
    internal_links: List[str]
    external_links: List[str]
    page_type: str
    language: Optional[str] = None
    content_hash: str
    fetched_at: datetime
    extraction_status: str
    error_details: Optional[str] = None
    used_js: bool


class CrawledPageListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    requested_url: str
    final_url: str
    http_status: int
    title: Optional[str] = None
    page_type: str
    extraction_status: str
    fetched_at: datetime
    used_js: bool


class CrawledPageListResponse(BaseModel):
    items: List[CrawledPageListItem]
    total: int
    page: int
    page_size: int
    total_pages: int

