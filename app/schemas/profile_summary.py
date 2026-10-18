from typing import List, Optional, Dict, Any
from pydantic import BaseModel
from app.schemas.brand import BrandResponse
from app.schemas.profile_run import ProfileRunResponse
from app.schemas.brand_fact import BrandFactResponse


class ProfileSummaryResponse(BaseModel):
    brand: BrandResponse
    active_run: Optional[ProfileRunResponse] = None
    profile_version: int

    # Synthesized Sections for Human Verification and Engine 2 Consumption
    business_overview: Dict[str, Any]
    products_and_services: List[Dict[str, Any]]
    target_audience: List[Dict[str, Any]]
    use_cases: List[Dict[str, Any]]
    pricing_information: List[Dict[str, Any]]
    differentiators: List[Dict[str, Any]]
    faqs: List[Dict[str, Any]]
    contact_and_company_info: Dict[str, Any]
    supported_languages: List[str]

    # Full Provenance Facts
    facts: List[BrandFactResponse]

    # Data Quality & Coverage Summary
    coverage_summary: Dict[str, Any]
    verification_progress: Dict[str, Any]
    crawl_summary: Optional[Dict[str, Any]] = None
