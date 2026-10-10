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


class Brand(Base):
    __tablename__ = "brands"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    organization_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    domain: Mapped[str] = mapped_column(String(255), index=True, nullable=False)
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    industry: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    target_market: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    language: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    profile_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Relationships
    runs: Mapped[List["ProfileRun"]] = relationship("ProfileRun", back_populates="brand", cascade="all, delete-orphan", order_by="desc(ProfileRun.started_at)")
    pages: Mapped[List["CrawledPage"]] = relationship("CrawledPage", back_populates="brand", cascade="all, delete-orphan")
    facts: Mapped[List["BrandFact"]] = relationship("BrandFact", back_populates="brand", cascade="all, delete-orphan")
    prompt_runs: Mapped[List["PromptRun"]] = relationship("PromptRun", back_populates="brand", cascade="all, delete-orphan", order_by="desc(PromptRun.created_at)")
    prompts: Mapped[List["PromptCandidate"]] = relationship("PromptCandidate", back_populates="brand", cascade="all, delete-orphan")

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

    page_limit: Mapped[int] = mapped_column(Integer, default=30)
    pages_discovered: Mapped[int] = mapped_column(Integer, default=0)
    pages_attempted: Mapped[int] = mapped_column(Integer, default=0)
    pages_succeeded: Mapped[int] = mapped_column(Integer, default=0)
    pages_skipped: Mapped[int] = mapped_column(Integer, default=0)
    pages_failed: Mapped[int] = mapped_column(Integer, default=0)

    warnings: Mapped[List[str]] = mapped_column(JSON, default=list)
    error_summary: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="runs")
    pages: Mapped[List["CrawledPage"]] = relationship("CrawledPage", back_populates="profile_run", cascade="all, delete-orphan")


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

    # fact_type: business_name, industry, company_description, product_service, product_feature, target_audience, use_case, pricing, differentiator, faq, contact_info, supported_language
    fact_type: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    fact_value: Mapped[Any] = mapped_column(JSON, nullable=False)

    source_page_id: Mapped[Optional[str]] = mapped_column(String(36), ForeignKey("crawled_pages.id", ondelete="SET NULL"), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(1024), nullable=True)
    evidence_snippet: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    extraction_method: Mapped[str] = mapped_column(String(64), default="deterministic", nullable=False)
    confidence: Mapped[float] = mapped_column(Float, default=1.0, nullable=False)
    user_confirmed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False, index=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="facts")
    source_page: Mapped[Optional["CrawledPage"]] = relationship("CrawledPage", back_populates="facts")

    __table_args__ = (
        Index("ix_brand_facts_type_brand", "brand_id", "fact_type"),
    )


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
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    user_edited: Mapped[bool] = mapped_column(Boolean, default=False)
    edit_history: Mapped[List[dict]] = mapped_column(JSON, default=list)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utc_now, onupdate=utc_now)

    # Relationships
    brand: Mapped["Brand"] = relationship("Brand", back_populates="prompts")
    run: Mapped["PromptRun"] = relationship("PromptRun", back_populates="prompts")

    __table_args__ = (
        Index("ix_prompt_candidates_brand_cat", "brand_id", "category"),
        Index("ix_prompt_candidates_brand_ver", "brand_id", "profile_version"),
    )

