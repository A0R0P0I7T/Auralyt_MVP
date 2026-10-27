"""Category Classification Stage for Engine 2 Prompt Intelligence.
Classifies a brand's verified profile into a structured, versioned industry & category taxonomy
before category-specific prompt planning and template selection.
"""
import re
import logging
from typing import List, Dict, Optional, Tuple, Any
from pydantic import BaseModel, Field

from app.prompts.models import NormalizedBrandProfile, GroundedFact

logger = logging.getLogger(__name__)

CLASSIFICATION_VERSION = "v2_taxonomic"


class BrandClassificationResult(BaseModel):
    primary_industry: str
    business_model: str
    primary_category: str
    secondary_categories: List[str] = []
    brand_name: str
    brand_domain: str
    classification_confidence: float = 1.0
    confidence: float = 1.0
    supporting_fact_ids: List[str] = []
    supporting_evidence: List[str] = []
    classification_version: str = CLASSIFICATION_VERSION
    warnings: List[str] = []
    # Explicit subcategory partition mapping product names and concepts to subcategory keys
    subcategories: Dict[str, List[str]] = Field(default_factory=dict)
    domain_archetype: str = "general"


class CategoryClassifier:
    """Classifies brand profile evidence into structured, versioned categories."""

    _cache: Dict[Tuple[str, int], BrandClassificationResult] = {}

    @classmethod
    def classify(
        cls,
        profile: NormalizedBrandProfile,
        force_refresh: bool = False
    ) -> BrandClassificationResult:
        cache_key = (profile.brand_id, profile.profile_version)
        if not force_refresh and cache_key in cls._cache:
            return cls._cache[cache_key]

        result = cls._perform_classification(profile)
        cls._cache[cache_key] = result
        return result

    @classmethod
    def _perform_classification(cls, profile: NormalizedBrandProfile) -> BrandClassificationResult:
        brand_name = profile.business_name or "Unknown Brand"
        brand_domain = profile.domain or "unknown.com"

        supporting_fact_ids: List[str] = []
        supporting_evidence: List[str] = []
        warnings: List[str] = []

        # 1. Collect evidence text and trace fact IDs
        evidence_corpus_parts = []
        if profile.industry:
            evidence_corpus_parts.append(profile.industry)
        if profile.tagline_or_description:
            evidence_corpus_parts.append(profile.tagline_or_description)

        for fact in profile.facts:
            val = fact.fact_value
            text_val = val if isinstance(val, str) else (val.get("name") or val.get("description") or str(val) if isinstance(val, dict) else str(val))
            if fact.fact_type in ("industry", "category", "company_description", "business_overview"):
                supporting_fact_ids.append(fact.id or "")
                evidence_corpus_parts.append(text_val)
                if fact.evidence_snippet:
                    supporting_evidence.append(fact.evidence_snippet)

        for p in profile.get_clean_products():
            evidence_corpus_parts.append(p)

        for u in profile.get_clean_use_cases():
            evidence_corpus_parts.append(u)

        corpus = " ".join(evidence_corpus_parts).lower()
        supporting_fact_ids = [fid for fid in set(supporting_fact_ids) if fid]

        # 2. Subcategory partitioning of products
        subcategories: Dict[str, List[str]] = {
            "footwear": [],
            "apparel": [],
            "equipment_gear": [],
            "software_tool": [],
            "cloud_service": [],
            "professional_service": [],
            "general_product": [],
        }

        footwear_pats = (
            r"\b(?:shoes?|footwear|sneakers?|trainers?|boots?|running shoes?|cleats?|sandals?|loafers?)\b"
        )
        apparel_pats = (
            r"\b(?:shirts?|t-shirts?|tee|tops?|pants?|trousers?|shorts?|jackets?|hoodies?|sweatshirts?|leggings?|tracksuits?|bra|clothing|apparel|dress(?:es)?)\b"
        )
        gear_pats = (
            r"\b(?:bags?|duffels?|backpacks?|tents?|sleeping bags?|cycles?|bikes?|mats?|bottles?|rackets?|balls?|equipment|weights?|dumbbells?|gloves?|helmets?)\b"
        )
        software_pats = (
            r"\b(?:platform|software|api|sdk|saas|app|tool|dashboard|portal|cli|database|engine|flow|agent|suite|system|solution|model)\b"
        )
        service_pats = (
            r"\b(?:consulting|advisory|maintenance|repair|subscription|delivery|service)\b"
        )

        for prod in profile.get_clean_products():
            prod_lower = prod.lower()
            matched = False
            if re.search(footwear_pats, prod_lower):
                subcategories["footwear"].append(prod)
                matched = True
            elif re.search(apparel_pats, prod_lower):
                subcategories["apparel"].append(prod)
                matched = True
            elif re.search(gear_pats, prod_lower):
                subcategories["equipment_gear"].append(prod)
                matched = True
            elif re.search(software_pats, prod_lower):
                subcategories["software_tool"].append(prod)
                subcategories["developer_tools"] = subcategories.get("developer_tools", [])
                subcategories["developer_tools"].append(prod)
                matched = True
            elif re.search(service_pats, prod_lower):
                subcategories["professional_service"].append(prod)
                matched = True
            if not matched:
                subcategories["general_product"].append(prod)

        # 3. Detect Primary Industry, Business Model, and Category
        is_sporting_goods = any(k in corpus for k in (
            "sporting goods", "sports equipment", "sports gear", "athletic shoes",
            "running shoe", "sports clothing", "sportswear", "activewear", "fitness equipment",
            "outdoor equipment", "camping", "hiking", "trail running"
        )) or (len(subcategories["footwear"]) > 0 and (len(subcategories["apparel"]) > 0 or len(subcategories["equipment_gear"]) > 0))

        is_crm = any(k in corpus for k in (
            "crm", "sales pipeline", "lead management", "lead prospecting", "prospecting",
            "pipeline management", "sales intelligence", "sales automation", "revops",
            "waterfall enrichment", "outbound sales", "outbound outreach", "cold outreach",
            "close more deals", "sales play", "sales plays", "sales workflow"
        ))

        is_developer = any(k in corpus for k in (
            "developer tools", "cloud infrastructure", "api gateway", "model routing",
            "llm api", "sdk toolkit", "api routing", "latency optimization", "backend engineering",
            "devops", "kubernetes", "database engine", "api ergonomics", "developer experience",
            "openrouter"
        ))

        is_marketing = any(k in corpus for k in (
            "marketing automation", "email campaigns", "customer segmentation",
            "newsletter analytics", "email marketing", "inbound marketing", "campaign management"
        ))

        is_fintech = any(k in corpus for k in (
            "fintech", "financialservice", "financial software", "payment gateway",
            "automated billing", "invoice reconciliation", "payment processing",
            "merchant processing", "subscription billing", "automated invoicing"
        ))

        is_healthcare = any(k in corpus for k in (
            "medicalorganization", "healthcare", "hipaa", "ehr", "patient scheduling",
            "clinical practice", "clinical records", "telehealth", "medical practice",
            "healthcare technology"
        ))

        is_professional_service = any(k in corpus for k in (
            "consulting firm", "advisory services", "management consulting",
            "professional services", "legal services", "client services",
            "financial advisory", "logistics services"
        ))

        is_retail_ecommerce = any(k in corpus for k in (
            "ecommerce", "online store", "shopping cart", "retail store",
            "consumer goods", "online shopping", "merchandise"
        ))

        # Confidence calculation
        confidence = 0.5
        if supporting_fact_ids:
            confidence += 0.25
        if len(profile.get_clean_products()) >= 2:
            confidence += 0.15
        if profile.industry and len(profile.industry) >= 3:
            confidence += 0.10
        confidence = min(round(confidence, 2), 1.0)

        if is_sporting_goods:
            primary_industry = "Sporting Goods & Retail"
            business_model = "E-Commerce and Retail"
            primary_category = "Sporting Goods"
            secondary_categories = []
            if subcategories["footwear"]:
                secondary_categories.append("Footwear")
            if subcategories["apparel"]:
                secondary_categories.append("Apparel")
            if subcategories["equipment_gear"]:
                secondary_categories.append("Equipment & Gear")
            if not secondary_categories:
                secondary_categories = ["Footwear", "Apparel", "Sportswear"]
            domain_archetype = "sportswear_sporting_goods"

        elif is_crm:
            primary_industry = "Sales Intelligence & CRM Software"
            business_model = "B2B SaaS"
            primary_category = "CRM & Sales Intelligence"
            secondary_categories = ["Sales Pipeline Management", "B2B Prospecting", "Outbound Automation", "Revenue Operations"]
            domain_archetype = "crm_sales"
            subcategories["crm_sales"] = profile.get_clean_products() or ["CRM & Sales Software"]

        elif is_developer:
            primary_industry = "Software & Cloud Technology"
            business_model = "B2B SaaS and Developer Services"
            primary_category = "Developer Infrastructure"
            secondary_categories = ["Cloud Infrastructure", "API Services", "Developer Tooling"]
            domain_archetype = "saas_software"
            subcategories["developer_tools"] = profile.get_clean_products() or ["Developer Infrastructure"]

        elif is_marketing:
            primary_industry = "Marketing Automation & Growth"
            business_model = "B2B SaaS"
            primary_category = "Marketing Automation"
            secondary_categories = ["Email Marketing", "Customer Segmentation", "Lifecycle Campaigns"]
            domain_archetype = "marketing_automation"
            subcategories["marketing_automation"] = profile.get_clean_products() or ["Marketing Automation Tool"]

        elif is_fintech:
            primary_industry = "Financial Technology & Payments"
            business_model = "Fintech SaaS"
            primary_category = "Fintech & Payments"
            secondary_categories = ["Payment Processing", "Billing & Invoicing", "Financial Automation"]
            domain_archetype = "fintech"
            subcategories["fintech"] = profile.get_clean_products() or ["Payment Software"]

        elif is_healthcare:
            primary_industry = "Healthcare Technology & Healthtech"
            business_model = "Healthcare SaaS"
            primary_category = "Healthcare Technology"
            secondary_categories = ["Clinical Management", "Patient Scheduling", "Health Records"]
            domain_archetype = "healthcare_tech"
            subcategories["healthcare_tech"] = profile.get_clean_products() or ["Healthcare Software"]

        elif is_professional_service:
            primary_industry = "Professional Services"
            business_model = "Client Services"
            primary_category = "Professional Services"
            secondary_categories = ["Consulting", "Advisory Services"]
            domain_archetype = "services_professional"
            subcategories["professional_services"] = profile.get_clean_products() or ["Consulting Services"]

        elif is_retail_ecommerce:
            primary_industry = "Retail & E-Commerce"
            business_model = "E-Commerce"
            primary_category = "Consumer Goods"
            secondary_categories = ["Retail Merchandise", "Online Shopping"]
            domain_archetype = "ecommerce_retail"
            subcategories["ecommerce_retail"] = profile.get_clean_products() or ["Consumer Products"]

        elif any(k in corpus for k in ("software", "saas", "platform", "app", "application", "businessapplication", "softwareapplication", "workflow")):
            primary_industry = "Business Software & Technology"
            business_model = "B2B SaaS"
            primary_category = "Business Software"
            secondary_categories = ["Cloud Applications", "Productivity Software"]
            domain_archetype = "general_business_software"
            subcategories["general_business_software"] = profile.get_clean_products() or ["Business Software"]

        else:
            primary_industry = profile.industry or ""
            business_model = "Commercial Business"
            primary_category = profile.get_primary_category() or ""
            domain_archetype = "uncertain_category"
            if not primary_category:
                secondary_categories = []
                warnings.append("Profile evidence was insufficient; missing industry, category, and verified facts.")
                confidence = 0.2
            else:
                secondary_categories = ["Commercial Solutions"]
                warnings.append("Profile evidence was sparse; category cannot be reliably confirmed from homepage.")
                confidence = max(0.4, confidence - 0.2)
            subcategories["uncertain_category"] = profile.get_clean_products() or ["Commercial Solutions"]

        return BrandClassificationResult(
            primary_industry=primary_industry,
            business_model=business_model,
            primary_category=primary_category,
            secondary_categories=secondary_categories,
            brand_name=brand_name,
            brand_domain=brand_domain,
            classification_confidence=confidence,
            confidence=confidence,
            supporting_fact_ids=supporting_fact_ids,
            supporting_evidence=supporting_evidence[:5],
            classification_version=CLASSIFICATION_VERSION,
            warnings=warnings,
            subcategories=subcategories,
            domain_archetype=domain_archetype
        )
