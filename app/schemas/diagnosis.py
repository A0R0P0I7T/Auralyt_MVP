"""Pydantic schemas for the Visibility Diagnosis & Action-Recommendation Service."""
from typing import List, Optional, Dict, Any
from datetime import datetime
from pydantic import BaseModel, Field


class DiagnosticFinding(BaseModel):
    finding_id: str = Field(..., description="Unique deterministic identifier for the finding")
    finding_type: str = Field(..., description="Type of finding: category_blindspot, citation_deficit, endorsement_gap, competitive_strength, profile_coverage_gap")
    severity: str = Field(..., description="Severity or priority: high, medium, low, info")
    affected_category: Optional[str] = Field(None, description="Affected prompt intent category or dimension")
    observation: str = Field(..., description="Empirical observation grounded in evaluated scan results")
    plausible_explanation: str = Field(..., description="Plausible explanatory hypothesis, clearly separated from verified facts")
    evidence_prompt_ids: List[str] = Field(default_factory=list, description="IDs of prompt results supporting this observation")
    relevant_competitors: List[str] = Field(default_factory=list, description="Competitor brands involved in the comparative gap")
    relevant_fact_ids: List[str] = Field(default_factory=list, description="Associated Engine 1 brand fact IDs")
    recommended_action: str = Field(..., description="Specific, evidence-backed action to remediate the visibility gap")
    action_rationale: str = Field(..., description="Why the recommended action directly addresses the observed gap")
    measurable_follow_up: str = Field(..., description="Concrete follow-up test to verify improvement in subsequent scans")
    confidence: float = Field(default=0.85, description="Heuristic confidence score for this finding")


class DiagnosisReport(BaseModel):
    scan_id: str
    brand_id: str
    business_name: str
    domain: str
    status: str = Field(..., description="Data sufficiency status: sufficient_data, insufficient_data")
    overall_visibility_score: Optional[float] = None
    mention_rate: Optional[float] = None
    recommendation_rate: Optional[float] = None
    total_prompts_evaluated: int
    findings_count: int
    findings: List[DiagnosticFinding] = Field(default_factory=list)
    abstention_reason: Optional[str] = None
    generated_at: datetime
