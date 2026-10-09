"""Brand Profiler Service.
Orchestrates crawling, page persistence, deterministic fact extraction,
human verification, and profile versioning.
"""
import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Optional, Dict, Any, List, Tuple
from sqlalchemy import select, update, delete, desc
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.config import settings
from app.db.session import async_session_factory
from app.db.models import Brand, ProfileRun, CrawledPage, BrandFact, utc_now
from app.crawler.security import validate_and_resolve_url, SecurityValidationError
from app.crawler.engine import ScraplingCrawler
from app.extractor.fact_synthesizer import FactSynthesizer

logger = logging.getLogger(__name__)


class ProfilerService:
    @staticmethod
    async def onboard_brand(
        website_url: str,
        business_name: Optional[str] = None,
        industry: Optional[str] = None,
        target_market: Optional[str] = None,
        language: Optional[str] = None,
        page_limit: int = 30,
        organization_id: Optional[str] = None,
        db: Optional[AsyncSession] = None
    ) -> Tuple[Brand, ProfileRun]:
        # 1. URL Validation & SSRF Check
        normalized_url, resolved_ip, hostname = validate_and_resolve_url(website_url)

        close_session = False
        if db is None:
            db = async_session_factory()
            close_session = True

        try:
            # 2. Get or create Brand
            stmt = select(Brand).where(Brand.domain == hostname)
            if organization_id:
                stmt = stmt.where(Brand.organization_id == organization_id)
            result = await db.execute(stmt)
            brand = result.scalars().first()

            inferred_name = business_name or hostname.replace("www.", "").split(".")[0].capitalize()

            if not brand:
                brand = Brand(
                    domain=hostname,
                    business_name=inferred_name,
                    industry=industry,
                    target_market=target_market,
                    language=language,
                    organization_id=organization_id,
                    profile_version=1
                )
                db.add(brand)
                await db.flush()
            else:
                # Update provided metadata
                if business_name:
                    brand.business_name = business_name
                if industry:
                    brand.industry = industry
                if target_market:
                    brand.target_market = target_market
                if language:
                    brand.language = language

            # 3. Create ProfileRun
            run = ProfileRun(
                brand_id=brand.id,
                status="pending",
                page_limit=min(page_limit, settings.HARD_MAX_PAGE_LIMIT),
                started_at=None,
                completed_at=None
            )
            db.add(run)
            await db.commit()
            await db.refresh(brand)
            await db.refresh(run)

            # 4. Trigger asynchronous profiling execution in background
            asyncio.create_task(ProfilerService.execute_profile_run(run.id, normalized_url))

            return brand, run

        finally:
            if close_session:
                await db.close()

    @staticmethod
    async def execute_profile_run(run_id: str, start_url: str) -> None:
        """Background task that performs crawling, extraction, and fact persistence."""
        async with async_session_factory() as db:
            run = await db.get(ProfileRun, run_id)
            if not run:
                logger.error(f"ProfileRun {run_id} not found.")
                return

            brand = await db.get(Brand, run.brand_id)
            if not brand:
                logger.error(f"Brand {run.brand_id} not found for run {run_id}.")
                return

            run.status = "running"
            run.started_at = utc_now()
            await db.commit()

            start_time = time.time()

            async def progress_callback(metrics: Dict[str, int]):
                async with async_session_factory() as prog_db:
                    p_run = await prog_db.get(ProfileRun, run_id)
                    if p_run:
                        p_run.pages_discovered = metrics.get("pages_discovered", 0)
                        p_run.pages_attempted = metrics.get("pages_attempted", 0)
                        p_run.pages_succeeded = metrics.get("pages_succeeded", 0)
                        p_run.pages_skipped = metrics.get("pages_skipped", 0)
                        p_run.pages_failed = metrics.get("pages_failed", 0)
                        await prog_db.commit()

            crawler = ScraplingCrawler(
                base_url=start_url,
                page_limit=run.page_limit,
                max_depth=settings.MAX_CRAWL_DEPTH,
                on_progress=progress_callback
            )

            try:
                extracted_pages_data = await crawler.run()
                duration = time.time() - start_time

                # Persist CrawledPage models
                page_models: List[CrawledPage] = []
                for p_dict in extracted_pages_data:
                    c_page = CrawledPage(
                        brand_id=brand.id,
                        profile_run_id=run.id,
                        requested_url=p_dict["requested_url"],
                        final_url=p_dict["final_url"],
                        canonical_url=p_dict.get("canonical_url"),
                        http_status=p_dict["http_status"],
                        title=p_dict.get("title"),
                        meta_description=p_dict.get("meta_description"),
                        headings=p_dict.get("headings", {}),
                        extracted_text=p_dict.get("extracted_text", ""),
                        structured_data=p_dict.get("structured_data", []),
                        internal_links=p_dict.get("internal_links", []),
                        external_links=p_dict.get("external_links", []),
                        page_type=p_dict.get("page_type", "other"),
                        language=p_dict.get("language"),
                        content_hash=p_dict.get("content_hash", ""),
                        extraction_status=p_dict.get("extraction_status", "success"),
                        error_details=p_dict.get("error_details"),
                        used_js=p_dict.get("used_js", False)
                    )
                    db.add(c_page)
                    page_models.append(c_page)

                await db.flush()

                # Synthesize Brand Facts
                synthesizer = FactSynthesizer(
                    brand_id=brand.id,
                    profile_version=brand.profile_version,
                    user_business_name=brand.business_name,
                    user_industry=brand.industry,
                    user_target_market=brand.target_market,
                    user_language=brand.language
                )
                new_facts = synthesizer.synthesize_facts(page_models)

                # CRITICAL RULE: Preserve existing user-confirmed facts!
                stmt = select(BrandFact).where(
                    BrandFact.brand_id == brand.id,
                    BrandFact.user_confirmed == True
                )
                res = await db.execute(stmt)
                confirmed_facts = res.scalars().all()
                confirmed_keys = {(f.fact_type, str(f.fact_value)) for f in confirmed_facts}

                # Delete old unconfirmed facts for this brand
                delete_stmt = delete(BrandFact).where(
                    BrandFact.brand_id == brand.id,
                    BrandFact.user_confirmed == False
                )
                await db.execute(delete_stmt)

                # Persist new facts that do not duplicate confirmed facts
                for nf in new_facts:
                    key = (nf.fact_type, str(nf.fact_value))
                    if key not in confirmed_keys:
                        db.add(nf)

                # Update Run Completion Status
                run.completed_at = utc_now()
                run.duration_seconds = round(duration, 2)
                run.pages_discovered = crawler.pages_discovered
                run.pages_attempted = crawler.pages_attempted
                run.pages_succeeded = crawler.pages_succeeded
                run.pages_skipped = crawler.pages_skipped
                run.pages_failed = crawler.pages_failed
                run.warnings = crawler.warnings

                if crawler.warnings:
                    run.status = "completed_with_warnings"
                else:
                    run.status = "completed"

                await db.commit()
                logger.info(f"Profile run {run_id} finished successfully in {duration:.1f}s")

            except Exception as e:
                logger.exception(f"Profile run {run_id} encountered fatal error: {e}")
                run.status = "failed"
                run.completed_at = utc_now()
                run.duration_seconds = round(time.time() - start_time, 2)
                run.error_summary = str(e)
                run.warnings = crawler.warnings
                await db.commit()

    @staticmethod
    async def get_brand_profile_summary(brand_id: str, db: AsyncSession) -> Optional[Dict[str, Any]]:
        brand = await db.get(Brand, brand_id)
        if not brand:
            return None

        # Fetch latest run
        run_stmt = select(ProfileRun).where(ProfileRun.brand_id == brand_id).order_by(desc(ProfileRun.started_at))
        run_res = await db.execute(run_stmt)
        active_run = run_res.scalars().first()

        # Fetch all facts
        facts_stmt = select(BrandFact).where(BrandFact.brand_id == brand_id).order_by(desc(BrandFact.confidence))
        facts_res = await db.execute(facts_stmt)
        facts = facts_res.scalars().all()

        # Group and synthesize sections
        overview = {
            "business_name": brand.business_name,
            "domain": brand.domain,
            "industry": brand.industry,
            "target_market": brand.target_market,
            "description": None,
        }

        desc_fact = next((f for f in facts if f.fact_type == "company_description"), None)
        if desc_fact:
            overview["description"] = desc_fact.fact_value

        products = []
        features = []
        audiences = []
        use_cases = []
        pricing = []
        differentiators = []
        faqs = []
        contact_info = {"emails": [], "phones": [], "social_profiles": []}
        supported_langs = set()

        for f in facts:
            f_val = f.fact_value
            if f.fact_type == "product_service":
                products.append({"fact_id": f.id, "value": f_val, "provenance": f.source_url, "snippet": f.evidence_snippet, "confirmed": f.user_confirmed, "confidence": f.confidence})
            elif f.fact_type == "product_feature":
                features.append({"fact_id": f.id, "value": f_val, "provenance": f.source_url, "snippet": f.evidence_snippet, "confirmed": f.user_confirmed, "confidence": f.confidence})
            elif f.fact_type == "target_audience":
                audiences.append({"fact_id": f.id, "value": f_val, "provenance": f.source_url, "snippet": f.evidence_snippet, "confirmed": f.user_confirmed, "confidence": f.confidence})
            elif f.fact_type == "use_case":
                use_cases.append({"fact_id": f.id, "value": f_val, "provenance": f.source_url, "snippet": f.evidence_snippet, "confirmed": f.user_confirmed, "confidence": f.confidence})
            elif f.fact_type == "pricing":
                pricing.append({"fact_id": f.id, "value": f_val, "provenance": f.source_url, "snippet": f.evidence_snippet, "confirmed": f.user_confirmed, "confidence": f.confidence})
            elif f.fact_type == "differentiator":
                differentiators.append({"fact_id": f.id, "value": f_val, "provenance": f.source_url, "snippet": f.evidence_snippet, "confirmed": f.user_confirmed, "confidence": f.confidence})
            elif f.fact_type == "faq":
                faqs.append({"fact_id": f.id, "value": f_val, "provenance": f.source_url, "snippet": f.evidence_snippet, "confirmed": f.user_confirmed, "confidence": f.confidence})
            elif f.fact_type == "supported_language":
                supported_langs.add(str(f_val))
            elif f.fact_type == "contact_info" and isinstance(f_val, dict):
                ctype = f_val.get("type")
                if ctype == "email":
                    contact_info["emails"].append(f_val.get("value"))
                elif ctype == "social_profile":
                    contact_info["social_profiles"].append(f_val.get("url"))

        total_facts = len(facts)
        confirmed_count = sum(1 for f in facts if f.user_confirmed)

        coverage_summary = {
            "total_pages_crawled": active_run.pages_succeeded if active_run else 0,
            "total_facts_extracted": total_facts,
            "warnings_count": len(active_run.warnings) if active_run else 0,
            "profile_status": active_run.status if active_run else "unknown",
        }

        verification_progress = {
            "total_facts": total_facts,
            "confirmed_facts": confirmed_count,
            "unconfirmed_facts": total_facts - confirmed_count,
            "verification_rate": round(confirmed_count / total_facts, 2) if total_facts > 0 else 0.0
        }

        return {
            "brand": brand,
            "active_run": active_run,
            "profile_version": brand.profile_version,
            "business_overview": overview,
            "products_and_services": products,
            "target_audience": audiences,
            "use_cases": use_cases,
            "pricing_information": pricing,
            "differentiators": differentiators,
            "faqs": faqs,
            "contact_and_company_info": contact_info,
            "supported_languages": sorted(list(supported_langs)),
            "facts": facts,
            "coverage_summary": coverage_summary,
            "verification_progress": verification_progress
        }
