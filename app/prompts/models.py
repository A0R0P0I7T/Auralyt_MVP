"""Internal data models for the Engine 2 prompt generation pipeline."""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field


class GroundedFact(BaseModel):
    id: Optional[str] = None
    fact_type: str
    fact_value: Any
    confidence: float = 1.0
    user_confirmed: bool = False
    source_url: Optional[str] = None
    evidence_snippet: Optional[str] = None


class NormalizedBrandProfile(BaseModel):
    brand_id: str
    domain: str
    business_name: str
    industry: Optional[str] = None
    target_market: Optional[str] = None
    primary_language: str = "en"
    profile_version: int

    # Core Grounded Entities
    tagline_or_description: Optional[str] = None
    products_and_services: List[str] = []
    target_audiences: List[str] = []
    use_cases: List[str] = []
    pricing_models: List[str] = []
    differentiators: List[str] = []
    faqs: List[Dict[str, str]] = []
    supported_languages: List[str] = []

    # All Grounded Facts with Provenance
    facts: List[GroundedFact] = []
    is_empty: bool = False


class PlannedPromptSlot(BaseModel):
    category: str
    intent: str
    buying_stage: str
    target_dimension: Optional[str] = None  # e.g., product name, audience segment, differentiator
    dimension_value: Optional[str] = None
    source_fact_ids: List[str] = []
    evidence_snippet: Optional[str] = None


class CoveragePlan(BaseModel):
    total_slots_requested: int
    slots: List[PlannedPromptSlot] = []
    category_distribution: Dict[str, int] = {}
    active_dimensions: List[str] = []


class GeneratedPromptCandidate(BaseModel):
    text: str
    category: str
    intent: str
    buying_stage: str
    target_audience: Optional[str] = None
    target_product_service: Optional[str] = None
    language: str = "en"
    provenance_fact_ids: List[str] = []
    grounding_evidence: List[str] = []
    scores: Dict[str, float] = {}
    quality_score: float = 1.0
