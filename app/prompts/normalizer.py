"""Stage A: Profile Normalization for Engine 2 Prompt Intelligence."""
import logging
from typing import Dict, Any, List, Optional
from app.prompts.models import NormalizedBrandProfile, GroundedFact

logger = logging.getLogger(__name__)


def _get_attr_or_key(obj: Any, key: str, default: Any = None) -> Any:
    if obj is None:
        return default
    if isinstance(obj, dict):
        return obj.get(key, default)
    return getattr(obj, key, default)


class ProfileNormalizer:
    """Normalizes Engine 1 ProfileSummaryResponse into typed internal representation."""

    @staticmethod
    def normalize(profile_data: Any) -> NormalizedBrandProfile:
        if hasattr(profile_data, "model_dump"):
            data = profile_data.model_dump()
        elif isinstance(profile_data, dict):
            data = profile_data
        else:
            raise ValueError(f"Unsupported profile_data type: {type(profile_data)}")

        brand_info = data.get("brand")
        brand_id = str(_get_attr_or_key(brand_info, "id", "") or "")
        domain = str(_get_attr_or_key(brand_info, "domain", "") or "")
        raw_bname = _get_attr_or_key(brand_info, "business_name")
        business_name = str(raw_bname) if raw_bname else domain.replace("www.", "").split(".")[0].capitalize()
        industry = _get_attr_or_key(brand_info, "industry")
        target_market = _get_attr_or_key(brand_info, "target_market")
        primary_lang = _get_attr_or_key(brand_info, "language") or "en"
        profile_version = int(data.get("profile_version", 1))

        # Parse Grounded Facts (supports dicts and BrandFact model instances)
        raw_facts = data.get("facts", [])
        grounded_facts: List[GroundedFact] = []
        for rf in raw_facts:
            g_fact = GroundedFact(
                id=_get_attr_or_key(rf, "id"),
                fact_type=_get_attr_or_key(rf, "fact_type", "unknown"),
                fact_value=_get_attr_or_key(rf, "fact_value"),
                confidence=float(_get_attr_or_key(rf, "confidence", 1.0) or 1.0),
                user_confirmed=bool(_get_attr_or_key(rf, "user_confirmed", False)),
                source_url=_get_attr_or_key(rf, "source_url"),
                evidence_snippet=_get_attr_or_key(rf, "evidence_snippet") or _get_attr_or_key(rf, "provenance")
            )
            grounded_facts.append(g_fact)

        # Extract structured dimensions
        # 1. Business Overview / Description
        biz_overview = data.get("business_overview", {})
        description = biz_overview.get("description") or biz_overview.get("summary")
        if not description:
            # Fallback from facts
            desc_facts = [f for f in grounded_facts if f.fact_type in ("business_name", "company_description")]
            if desc_facts:
                val = desc_facts[0].fact_value
                description = val if isinstance(val, str) else str(val)

        # 2. Products and Services
        raw_prods = data.get("products_and_services", [])
        products: List[str] = []
        for p in raw_prods:
            if isinstance(p, dict):
                p_name = p.get("name") or p.get("title") or p.get("product_service")
                if p_name and isinstance(p_name, str) and p_name not in products:
                    products.append(p_name.strip())
            elif isinstance(p, str) and p.strip() not in products:
                products.append(p.strip())

        # Pull from facts if empty
        if not products:
            for f in grounded_facts:
                if f.fact_type in ("product_service", "product_feature"):
                    val = f.fact_value
                    name = val.get("name") if isinstance(val, dict) else str(val)
                    if name and name not in products:
                        products.append(name.strip())

        # 3. Target Audiences
        raw_audiences = data.get("target_audience", [])
        audiences: List[str] = []
        for a in raw_audiences:
            if isinstance(a, dict):
                a_name = a.get("segment") or a.get("audience") or a.get("target_audience")
                if a_name and isinstance(a_name, str) and a_name not in audiences:
                    audiences.append(a_name.strip())
            elif isinstance(a, str) and a.strip() not in audiences:
                audiences.append(a.strip())

        if not audiences:
            for f in grounded_facts:
                if f.fact_type == "target_audience":
                    val = f.fact_value
                    name = val.get("segment") if isinstance(val, dict) else str(val)
                    if name and name not in audiences:
                        audiences.append(name.strip())

        # 4. Use Cases
        raw_use_cases = data.get("use_cases", [])
        use_cases: List[str] = []
        for uc in raw_use_cases:
            if isinstance(uc, dict):
                uc_title = uc.get("title") or uc.get("use_case") or uc.get("description")
                if uc_title and isinstance(uc_title, str) and uc_title not in use_cases:
                    use_cases.append(uc_title.strip())
            elif isinstance(uc, str) and uc.strip() not in use_cases:
                use_cases.append(uc.strip())

        if not use_cases:
            for f in grounded_facts:
                if f.fact_type == "use_case":
                    val = f.fact_value
                    name = val.get("title") if isinstance(val, dict) else str(val)
                    if name and name not in use_cases:
                        use_cases.append(name.strip())

        # 5. Pricing Models
        raw_pricing = data.get("pricing_information", [])
        pricing_models: List[str] = []
        for pr in raw_pricing:
            if isinstance(pr, dict):
                model_str = pr.get("model") or pr.get("plan_name") or pr.get("details")
                if model_str and isinstance(model_str, str) and model_str not in pricing_models:
                    pricing_models.append(model_str.strip())
            elif isinstance(pr, str) and pr.strip() not in pricing_models:
                pricing_models.append(pr.strip())

        if not pricing_models:
            for f in grounded_facts:
                if f.fact_type == "pricing":
                    val = f.fact_value
                    name = val.get("model") if isinstance(val, dict) else str(val)
                    if name and name not in pricing_models:
                        pricing_models.append(name.strip())

        # 6. Differentiators
        raw_diffs = data.get("differentiators", [])
        differentiators: List[str] = []
        for d in raw_diffs:
            if isinstance(d, dict):
                d_str = d.get("claim") or d.get("differentiator") or d.get("description")
                if d_str and isinstance(d_str, str) and d_str not in differentiators:
                    differentiators.append(d_str.strip())
            elif isinstance(d, str) and d.strip() not in differentiators:
                differentiators.append(d.strip())

        if not differentiators:
            for f in grounded_facts:
                if f.fact_type == "differentiator":
                    val = f.fact_value
                    name = val.get("claim") if isinstance(val, dict) else str(val)
                    if name and name not in differentiators:
                        differentiators.append(name.strip())

        # 7. FAQs
        raw_faqs = data.get("faqs", [])
        faqs: List[Dict[str, str]] = []
        for faq in raw_faqs:
            if isinstance(faq, dict) and "question" in faq:
                faqs.append({
                    "question": str(faq.get("question", "")).strip(),
                    "answer": str(faq.get("answer", "")).strip()
                })

        # 8. Supported Languages
        supported_langs = data.get("supported_languages", [])
        if not supported_langs and primary_lang:
            supported_langs = [primary_lang]

        # Determine if profile is empty
        is_empty = (
            len(grounded_facts) == 0
            and len(products) == 0
            and len(audiences) == 0
            and not description
        )

        return NormalizedBrandProfile(
            brand_id=brand_id,
            domain=domain,
            business_name=business_name,
            industry=industry,
            target_market=target_market,
            primary_language=primary_lang,
            profile_version=profile_version,
            tagline_or_description=description,
            products_and_services=products,
            target_audiences=audiences,
            use_cases=use_cases,
            pricing_models=pricing_models,
            differentiators=differentiators,
            faqs=faqs,
            supported_languages=supported_langs,
            facts=grounded_facts,
            is_empty=is_empty
        )
