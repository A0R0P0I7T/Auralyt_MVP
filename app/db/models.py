import uuid
from datetime import datetime, timezone
from typing import List, Optional, Any
from sqlalchemy import (
    String, Text, Integer, Float, Boolean, DateTime, ForeignKey, JSON, Index, func
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.base import Base


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    slug: Mapped[str] = mapped_column(String(100), unique=True, index=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Relationships
    memberships: Mapped[List["OrganizationMember"]] = relationship("OrganizationMember", back_populates="organization", cascade="all, delete-orphan")
    brands: Mapped[List["Brand"]] = relationship("Brand", back_populates="organization")


class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    is_superuser: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Relationships
    memberships: Mapped[List["OrganizationMember"]] = relationship("OrganizationMember", back_populates="user", cascade="all, delete-orphan")


class OrganizationMember(Base):
    __tablename__ = "organization_members"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[str] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    role: Mapped[str] = mapped_column(String(32), default="owner", nullable=False)  # owner, admin, member
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    # Relationships
    organization: Mapped["Organization"] = relationship("Organization", back_populates="memberships")
    user: Mapped["User"] = relationship("User", back_populates="memberships")

    __table_args__ = (
        Index("ix_org_members_user_org", "user_id", "organization_id", unique=True),
    )


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True)
    domain: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    target_market: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    profile_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship("Organization", back_populates="brands")
    runs: Mapped[List["ProfileRun"]] = relationship("ProfileRun", back_populates="brand", cascade="all, delete-orphan", order_by="desc(ProfileRun.started_at)")
    pages: Mapped[List["CrawledPage"]] = relationship("CrawledPage", back_populates="brand", cascade="all, delete-orphan")
    facts: Mapped[List["BrandFact"]] = relationship("BrandFact", back_populates="brand", cascade="all, delete-orphan")
    prompt_runs: Mapped[List["PromptRun"]] = relationship("PromptRun", back_populates="brand", cascade="all, delete-orphan", order_by="desc(PromptRun.created_at)")
    prompts: Mapped[List["PromptCandidate"]] = relationship("PromptCandidate", back_populates="brand", cascade="all, delete-orphan")
    visibility_scans: Mapped[List["VisibilityScan"]] = relationship("VisibilityScan", back_populates="brand", cascade="all, delete-orphan", order_by="desc(VisibilityScan.created_at)")

    __table_args__ = (
        Index("ix_brands_domain_org", "domain", "organization_id"),
    )


class ProfileRun(Base):
    __tablename__ = "profile_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id: Mapped[str] = mapped_column(String(36), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True)
    
    # Status: pending, running, completed, completed_with_warnings, failed, cancelled
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)
    
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    profile_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False, index=True)

    page_limit: Mapped[int] = mapped_column(Integer, default=30)
    pages_discovered: Mapped[int] = mapped_column(Integer, default=0)
    pages_attempted: Mapped[int] = mapped_column(Integer, default=0)
    pages_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    pages_skipped: Mapped[int] = mapped_column(Integer, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0)

    warnings: Mapped[List[str]] = mapped_column(JSON, default=list)
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    crawl_summary: Mapped[Optional[dict]] = mapped_column(JSON, default=dict, nullable=True)

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="runs")
    pages: Mapped[List["CrawledPage"]] = relationship("CrawledPage", back_populates="profile_run", cascade="all, delete-orphan")

    def __init__(self, **kwargs):
        kwargs.setdefault("profile_version", 1)
        super().__init__(**kwargs)


class CrawledPage(Base):
    __tablename__ = "crawled_pages"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id: Mapped[str] = mapped_column(String(36), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("profile_runs.id", ondelete="CASCADE"), nullable=False, index=True)

    requested_url: Mapped[str] = mapped_column(String(1024), nullable=False)
    final_url: Mapped[str] = mapped_column(String(1024), nullable=False, index=True)
    canonical_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    http_status: Mapped[int] = mapped_column(Integer, nullable=False)
    
    title: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    meta_description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    headings: Mapped[dict] = mapped_column(JSON, default=lambda: {"h1": [], "h2": []})
    extracted_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    structured_data: Mapped[List[dict]] = mapped_column(JSON, default=list)
    internal_links: Mapped[List[str]] = mapped_column(JSON, default=list)
    external_links: Mapped[List[str]] = mapped_column(JSON, default=list)
    
    page_type: Mapped[str] = mapped_column(String(50), default="other", index=True)  # homepage, about, pricing, product_service, contact, faq, blog, docs, other
    language: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), index=True, nullable=False)
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    extraction_status: Mapped[str] = mapped_column(String(32), default="success")  # success, partial, failed
    error_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    used_js: Mapped[bool] = mapped_column(Boolean, default=False)

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="pages")
    profile_run: Mapped["ProfileRun"] = relationship("ProfileRun", back_populates="pages")
    facts: Mapped[List["BrandFact"]] = relationship("BrandFact", back_populates="source_page")


class BrandFact(Base):
    __tablename__ = "brand_facts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id: Mapped[str] = mapped_column(String(36), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    fact_key: Mapped[Optional[str]] = mapped_column(String(512), nullable=True, index=True)

    # fact_type: business_name, industry, company_description, product_service, product_feature, target_audience, use_case, pricing, differentiator, faq, contact_info, supported_language
    fact_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    fact_value: Mapped[Any] = mapped_column(JSON, nullable=False)

    source_page_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("crawled_pages.id", ondelete="SET NULL"), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    evidence_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    supporting_evidence: Mapped[List[dict]] = mapped_column(JSON, default=list)
    extraction_method: Mapped[str] = mapped_column(String(64), default="deterministic", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    user_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_rejected: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_superseded: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    is_stale: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    superseded_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="facts")
    source_page: Mapped[Optional["CrawledPage"]] = relationship("CrawledPage", back_populates="facts")

    __table_args__ = (
        Index("ix_brand_facts_type_brand", "brand_id", "fact_type"),
    )

    def __init__(self, **kwargs):
        kwargs.setdefault("is_rejected", False)
        kwargs.setdefault("user_confirmed", False)
        kwargs.setdefault("is_superseded", False)
        kwargs.setdefault("is_stale", False)
        kwargs.setdefault("supporting_evidence", [])
        super().__init__(**kwargs)


class PromptRun(Base):
    __tablename__ = "prompt_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id: Mapped[str] = mapped_column(String(36), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Status: pending, running, completed, failed, cancelled
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)
    prompt_count_requested: Mapped[int] = mapped_column(Integer, default=20)
    prompts_generated: Mapped[int] = mapped_column(Integer, default=0)
    provider: Mapped[str] = mapped_column(String(64), default="deterministic")
    model_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="prompt_runs")
    prompts: Mapped[List["PromptCandidate"]] = relationship("PromptCandidate", back_populates="run", cascade="all, delete-orphan")


class PromptCandidate(Base):
    __tablename__ = "prompt_candidates"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id: Mapped[str] = mapped_column(String(36), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True)
    prompt_run_id: Mapped[str] = mapped_column(String(36), ForeignKey("prompt_runs.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    intent: Mapped[str] = mapped_column(String(64), default="informational", nullable=False)
    buying_stage: Mapped[str] = mapped_column(String(64), default="consideration", nullable=False)
    target_audience: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    target_product_service: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    language: Mapped[str] = mapped_column(String(20), default="en", nullable=False)

    provenance_fact_ids: Mapped[List[str]] = mapped_column(JSON, default=list)
    grounding_evidence: Mapped[List[str]] = mapped_column(JSON, default=list)
    scores: Mapped[dict] = mapped_column(JSON, default=dict)
    quality_score: Mapped[float] = mapped_column(Float, default=1.0, index=True)

    is_approved: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    lifecycle_status: Mapped[str] = mapped_column(String(32), default="approved", nullable=False, index=True)
    review_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    edit_history: Mapped[List[dict]] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="prompts")
    run: Mapped["PromptRun"] = relationship("PromptRun", back_populates="prompts")
    visibility_results: Mapped[List["VisibilityResult"]] = relationship("VisibilityResult", back_populates="prompt", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_prompt_candidates_brand_cat", "brand_id", "category"),
        Index("ix_prompt_candidates_brand_ver", "brand_id", "profile_version"),
    )


class VisibilityScan(Base):
    __tablename__ = "visibility_scans"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    brand_id: Mapped[str] = mapped_column(String(36), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_version: Mapped[int] = mapped_column(Integer, nullable=False, index=True)

    # Status: pending, running, completed, completed_with_errors, failed, cancelled
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), default="mock", nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), default="mock-evaluator", nullable=False)

    prompts_selected: Mapped[int] = mapped_column(Integer, default=0)
    prompts_completed: Mapped[int] = mapped_column(Integer, default=0)
    prompts_failed: Mapped[int] = mapped_column(Integer, default=0)

    visibility_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # 0.0 - 100.0
    mention_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True)      # 0.0 - 1.0
    recommendation_rate: Mapped[Optional[float]] = mapped_column(Float, nullable=True) # 0.0 - 1.0
    average_position: Mapped[Optional[float]] = mapped_column(Float, nullable=True)

    total_tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    config_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="visibility_scans")
    results: Mapped[List["VisibilityResult"]] = relationship("VisibilityResult", back_populates="scan", cascade="all, delete-orphan", order_by="desc(VisibilityResult.created_at)")

    __table_args__ = (
        Index("ix_visibility_scans_brand_status", "brand_id", "status"),
    )


class VisibilityResult(Base):
    __tablename__ = "visibility_results"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    scan_id: Mapped[str] = mapped_column(String(36), ForeignKey("visibility_scans.id", ondelete="CASCADE"), nullable=False, index=True)
    brand_id: Mapped[str] = mapped_column(String(36), ForeignKey("brands.id", ondelete="CASCADE"), nullable=False, index=True)
    prompt_id: Mapped[str] = mapped_column(String(36), ForeignKey("prompt_candidates.id", ondelete="CASCADE"), nullable=False, index=True)

    prompt_text: Mapped[str] = mapped_column(Text, nullable=False)
    provider: Mapped[str] = mapped_column(String(64), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)

    # Status: success, error, timeout
    execution_status: Mapped[str] = mapped_column(String(32), default="success", nullable=False)
    raw_response_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    raw_response_metadata: Mapped[dict] = mapped_column(JSON, default=dict)

    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    tokens_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_details: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Structured Evaluation Dimensions
    brand_mentioned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)
    mention_context: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # recommendation_status: recommended, neutral_mention, not_recommended, not_mentioned, unknown
    recommendation_status: Mapped[str] = mapped_column(String(32), default="unknown", nullable=False, index=True)

    # competitor_mentions: list of detected competitor brand names
    competitor_mentions: Mapped[List[str]] = mapped_column(JSON, default=list)

    # comparative_position: leader, recommended_alternative, contender, mentioned_only, unfavorable, not_mentioned, unknown
    comparative_position: Mapped[str] = mapped_column(String(64), default="unknown", nullable=False)

    # citations: verified URLs or sources present in response or metadata
    citations: Mapped[List[str]] = mapped_column(JSON, default=list)
    provider_citations: Mapped[List[str]] = mapped_column(JSON, default=list)
    response_citations: Mapped[List[str]] = mapped_column(JSON, default=list)

    sentiment_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)  # -1.0 to 1.0
    visibility_rank: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)   # 1-indexed position in recommendations
    evaluation_reasoning: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)

    # Relationships
    scan: Mapped["VisibilityScan"] = relationship("VisibilityScan", back_populates="results")
    prompt: Mapped["PromptCandidate"] = relationship("PromptCandidate", back_populates="visibility_results")

    __table_args__ = (
        Index("ix_visibility_results_brand_and_mention", "brand_id", "brand_mentioned"),
        Index("ix_visibility_results_scan_prompt", "scan_id", "prompt_id"),
    )
