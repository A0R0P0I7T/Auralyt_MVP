"""Visibility Diagnosis and Action-Recommendation Service.

Synthesizes empirical observations across Engine 1 facts, Engine 2 prompts,
and Engine 3 evaluation results into structured, evidence-backed diagnostic findings.
"""
import uuid
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Brand, BrandFact, VisibilityScan, VisibilityResult, utc_now
from app.schemas.diagnosis import DiagnosticFinding, DiagnosisReport

logger = logging.getLogger(__name__)


class VisibilityDiagnosisService:
    """Core diagnostic engine mapping visibility gaps to root causes and testable remediation actions."""

    @staticmethod
    async def diagnose_scan(scan_id: str, brand_id: str, db: AsyncSession) -> DiagnosisReport:
        """
        Executes evidence-backed diagnostic analysis on a visibility scan.
        Abstains safely when sample size or evaluation data is insufficient.
        """
        # Fetch brand and scan
        brand = await db.get(Brand, brand_id)
        if not brand:
            raise ValueError("Brand not found.")

        scan = await db.get(VisibilityScan, scan_id)
        if not scan or scan.brand_id != brand_id:
            raise ValueError("Visibility scan not found.")

        # Fetch detailed results with eagerly loaded prompt
        res_stmt = select(VisibilityResult).options(
            selectinload(VisibilityResult.prompt)
        ).where(
            VisibilityResult.scan_id == scan_id
        ).order_by(VisibilityResult.created_at)
        res_exec = await db.execute(res_stmt)
        results: List[VisibilityResult] = res_exec.scalars().all()


        # Fetch active Engine 1 brand facts
        facts_stmt = select(BrandFact).where(
            BrandFact.brand_id == brand_id,
            BrandFact.profile_version == scan.profile_version,
            BrandFact.is_rejected.is_(False)
        )
        facts_exec = await db.execute(facts_stmt)
        facts: List[BrandFact] = facts_exec.scalars().all()

        # 1. Safeguard: Check data sufficiency & abstain if sample too small or aborted
        if scan.status in ("pending", "running", "failed") or len(results) < 3 or scan.prompts_completed < 3:
            report = DiagnosisReport(
                scan_id=scan.id,
                brand_id=brand.id,
                business_name=brand.business_name,
                domain=brand.domain,
                status="insufficient_data",
                overall_visibility_score=scan.visibility_score,
                mention_rate=scan.mention_rate,
                recommendation_rate=scan.recommendation_rate,
                total_prompts_evaluated=len(results),
                findings_count=0,
                findings=[],
                abstention_reason=f"Scan sample too small or incomplete (completed {scan.prompts_completed}/{scan.prompts_selected} prompts, status: {scan.status}). Abstaining to prevent unreliable conclusions.",
                generated_at=utc_now()
            )
            return report

        findings: List[DiagnosticFinding] = []
        fact_by_type: Dict[str, List[BrandFact]] = {}
        for f in facts:
            fact_by_type.setdefault(f.fact_type, []).append(f)

        # Group results by prompt category
        # If result.prompt_candidate is loaded or extract from prompt text
        cat_results: Dict[str, List[VisibilityResult]] = {}
        for r in results:
            # Category can be deduced from prompt candidate or default
            cat = "general"
            if r.prompt and hasattr(r.prompt, "category"):
                cat = r.prompt.category
            cat_results.setdefault(cat, []).append(r)

        # Compute competitor visibility frequency
        competitor_counts: Dict[str, int] = {}
        competitor_recommendations: Dict[str, int] = {}
        for r in results:
            for c in (r.competitor_mentions or []):
                competitor_counts[c] = competitor_counts.get(c, 0) + 1
            if r.recommendation_status == "not_recommended" and r.competitor_mentions:
                for c in r.competitor_mentions:
                    competitor_recommendations[c] = competitor_recommendations.get(c, 0) + 1

        top_competitors = sorted(competitor_counts.keys(), key=lambda k: competitor_counts[k], reverse=True)[:5]
        top_endorsed_competitors = sorted(competitor_recommendations.keys(), key=lambda k: competitor_recommendations[k], reverse=True)[:3]

        # 2. Rule: Category Blindspot Detection
        for cat, r_list in cat_results.items():
            if len(r_list) >= 2:
                cat_mentions = sum(1 for r in r_list if r.brand_mentioned)
                cat_comp_mentions = sum(1 for r in r_list if r.competitor_mentions)
                if cat_mentions == 0 and cat_comp_mentions > 0:
                    diff_facts = fact_by_type.get("differentiator", [])
                    has_diff_in_profile = len(diff_facts) > 0
                    explanation = (
                        f"AI models consistently recommend competitors for '{cat}' queries while omitting {brand.business_name}. "
                        f"{'While differentiators are documented on the website, they may not be indexed by AI search providers.' if has_diff_in_profile else 'The brand profile also lacks explicit comparative differentiators.'}"
                    )
                    findings.append(DiagnosticFinding(
                        finding_id=f"FIND-BLIND-{cat.upper()}",
                        finding_type="category_blindspot",
                        severity="high",
                        affected_category=cat,
                        observation=f"Target brand was completely omitted in {len(r_list)} '{cat}' queries (0% mention rate), whereas competitors ({', '.join(top_competitors[:3])}) were recognized.",
                        plausible_explanation=explanation,
                        evidence_prompt_ids=[r.prompt_id for r in r_list],
                        relevant_competitors=top_competitors[:3],
                        relevant_fact_ids=[f.id for f in diff_facts if f.id],
                        recommended_action=f"Publish a dedicated, indexable solutions page addressing '{cat}' and highlighting specific workflow advantages over {', '.join(top_competitors[:2]) if top_competitors else 'incumbent solutions'}.",
                        action_rationale=f"AI training and retrieval grounding require explicit entity-category associations to surface brands during unbranded {cat} queries.",
                        measurable_follow_up=f"Re-evaluate organic visibility with 10 focused '{cat}' prompts; target a mention rate >= 40%.",
                        confidence=0.88
                    ))

        # 3. Rule: Citation Domain Deficit
        all_citations = []
        target_citations = []
        for r in results:
            if r.citations:
                all_citations.extend(r.citations)
            t_cits = r.raw_response_metadata.get("target_brand_citations", []) if r.raw_response_metadata else []
            target_citations.extend(t_cits)

        if len(all_citations) >= 2 and len(target_citations) == 0:
            sd_facts = [f for f in facts if f.extraction_method == "json_ld_schema"]
            has_sd = len(sd_facts) > 0
            findings.append(DiagnosticFinding(
                finding_id="FIND-CIT-DEFICIT",
                finding_type="citation_deficit",
                severity="medium",
                affected_category="citations",
                observation=f"AI responses included {len(all_citations)} web citations, but none linked to {brand.domain}.",
                plausible_explanation="AI search engines rely on canonical URLs, structured Schema.org data, and technical documentation when generating grounded source links.",
                evidence_prompt_ids=[r.prompt_id for r in results if r.citations][:5],
                relevant_competitors=[],
                relevant_fact_ids=[f.id for f in sd_facts if f.id],
                recommended_action=f"Deploy Schema.org Organization and SoftwareApplication structured data on https://{brand.domain} with explicit sameAs social links and verify sitemap indexability.",
                action_rationale="Proper structured markup makes core domain URLs more authoritative and easily parseable by AI search grounding crawlers.",
                measurable_follow_up="Re-run visibility scan under search grounding mode and verify target brand citations appear in at least 15% of responses.",
                confidence=0.82
            ))

        # 4. Rule: Endorsement Gap
        total_eval = len(results)
        total_mentions = sum(1 for r in results if r.brand_mentioned)
        total_recs = sum(1 for r in results if r.recommendation_status == "recommended")
        mention_rate = total_mentions / total_eval if total_eval > 0 else 0.0
        rec_rate = total_recs / total_eval if total_eval > 0 else 0.0

        if mention_rate >= 0.35 and rec_rate < 0.20 and top_endorsed_competitors:
            findings.append(DiagnosticFinding(
                finding_id="FIND-ENDORSEMENT-GAP",
                finding_type="endorsement_gap",
                severity="high",
                affected_category="recommendations",
                observation=f"Brand is recognized in {round(mention_rate * 100)}% of answers, but recommended as category leader in only {round(rec_rate * 100)}%. Competitors {', '.join(top_endorsed_competitors)} are consistently preferred.",
                plausible_explanation="The AI model knows your product exists, but lacks evidence of enterprise reliability, security, compliance, or widespread customer validation.",
                evidence_prompt_ids=[r.prompt_id for r in results if r.brand_mentioned and r.recommendation_status != "recommended"][:5],
                relevant_competitors=top_endorsed_competitors,
                relevant_fact_ids=[f.id for f in facts if f.fact_type in ("differentiator", "target_audience") and f.id],
                recommended_action=f"Publish third-party compliance proofs (e.g., SOC2, ISO), ROI statistics, and public case studies comparing enterprise features against {top_endorsed_competitors[0]}.",
                action_rationale="AI models favor established brands for leadership queries when smaller competitors lack documented enterprise validation signals.",
                measurable_follow_up="Run 10 recommendation-intent prompts; verify recommendation rate increases to >= 35%.",
                confidence=0.85
            ))

        # 5. Rule: Competitive Strength Recognition
        leader_ranks = [r for r in results if r.visibility_rank == 1 or r.comparative_position == "leader"]
        if leader_ranks:
            strong_prompts = [r.prompt_text for r in leader_ranks[:3]]
            findings.append(DiagnosticFinding(
                finding_id="FIND-COMPETITIVE-STRENGTH",
                finding_type="competitive_strength",
                severity="low",
                affected_category="leadership",
                observation=f"{brand.business_name} achieved Rank #1 / Leadership position in {len(leader_ranks)} prompt response(s).",
                plausible_explanation="The product has established clear category authority or superior association in this specific domain context.",
                evidence_prompt_ids=[r.prompt_id for r in leader_ranks],
                relevant_competitors=[],
                relevant_fact_ids=[f.id for f in facts if f.fact_type == "product_service" and f.id][:3],
                recommended_action="Maintain leadership momentum by publishing regular product release notes and technical deep dives.",
                action_rationale="Sustained domain publication prevents competitors from eroding existing AI visibility advantages.",
                measurable_follow_up="Verify rank #1 stability across repeatability tests over multiple benchmark cycles.",
                confidence=0.90
            ))

        # Sort findings by severity: high -> medium -> low -> info
        severity_order = {"high": 1, "medium": 2, "low": 3, "info": 4}
        findings.sort(key=lambda f: severity_order.get(f.severity, 5))

        report = DiagnosisReport(
            scan_id=scan.id,
            brand_id=brand.id,
            business_name=brand.business_name,
            domain=brand.domain,
            status="sufficient_data",
            overall_visibility_score=scan.visibility_score,
            mention_rate=scan.mention_rate,
            recommendation_rate=scan.recommendation_rate,
            total_prompts_evaluated=len(results),
            findings_count=len(findings),
            findings=findings,
            abstention_reason=None,
            generated_at=utc_now()
        )

        # Cache in scan metadata
        if scan.config_metadata is None:
            scan.config_metadata = {}
        scan.config_metadata["diagnosis_report"] = report.model_dump(mode="json")
        await db.commit()


        return report
