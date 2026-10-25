"""Stage A: Profile Normalization for Engine 2 Prompt Intelligence."""
import re
import logging
from typing import Dict, Any, List, Optional
from app.prompts.models import NormalizedBrandProfile, GroundedFact

logger = logging.getLogger(__name__)


def decompose_compound_capabilities(text: str) -> List[str]:
    """
    Decomposes multi-clause compound capability strings
    (e.g., 'answer questions, write, create images, complete work, and code')
    into individual, atomic user intents so prompts express a single coherent goal.
    """
    clean = text.strip().strip("\"'").rstrip(".")
    if "," in clean or " and " in clean.lower():
        parts = re.split(r",\s*(?:and\s+)?|\s+and\s+", clean, flags=re.IGNORECASE)
        decomposed = [p.strip().strip("\"'").rstrip(".") for p in parts if p.strip().strip("\"'")]
        if len(decomposed) >= 2 and all(len(p) <= 60 for p in decomposed):
            return decomposed
    return [clean] if clean else []


UI_NAVIGATION_NOISE_PATTERNS = {
    "select size", "size guide", "add to cart", "add to bag", "buy now", "quick buy",
    "sale", "clearance", "new & featured", "new and featured", "featured", "shop all",
    "view all", "all products", "shop now", "order status", "track order", "store locator",
    "find a store", "sign in", "sign up", "log in", "login", "register", "my account",
    "customer care", "help center", "contact us", "faq", "faqs", "terms and conditions",
    "terms & conditions", "privacy policy", "cookie policy", "all rights reserved",
    "official online store", "online store", "gift cards", "wishlist", "cart", "checkout",
    "menu", "search", "close", "back to top", "home"
}


def is_navigation_or_ui_noise(text: Optional[str]) -> bool:
    if not text:
        return True
    t = text.strip().lower()
    if t in UI_NAVIGATION_NOISE_PATTERNS:
        return True
    if "official online store" in t or "select size" in t:
        return True
    if t.startswith("buy ") and "online" in t and len(t) < 40:
        return True
    if t in ("women", "men", "kids", "boys", "girls", "unisex") and len(t.split()) == 1:
        return True
    return False


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
            if bool(_get_attr_or_key(rf, "is_rejected", False)):
                continue
            g_fact = GroundedFact(
                id=_get_attr_or_key(rf, "id"),
                fact_type=_get_attr_or_key(rf, "fact_type", "unknown"),
                fact_value=_get_attr_or_key(rf, "fact_value"),
                confidence=float(_get_attr_or_key(rf, "confidence", 1.0) or 1.0),
                user_confirmed=bool(_get_attr_or_key(rf, "user_confirmed", False)),
                source_url=_get_attr_or_key(rf, "source_url"),
                evidence_snippet=_get_attr_or_key(rf, "evidence_snippet") or _get_attr_or_key(rf, "provenance"),
                supporting_evidence=_get_attr_or_key(rf, "supporting_evidence", []) or [],
                extraction_method=_get_attr_or_key(rf, "extraction_method", "unknown")
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
                if bool(_get_attr_or_key(p, "is_rejected", False)):
                    continue
                p_val = p.get("value", p) if "value" in p else p
                if isinstance(p_val, dict):
                    p_name = p_val.get("name") or p_val.get("title") or p_val.get("product_service")
                elif isinstance(p_val, str):
                    p_name = p_val
                else:
                    p_name = None
                if p_name and isinstance(p_name, str) and not is_navigation_or_ui_noise(p_name):
                    clean_name = p_name.strip()
                    if clean_name not in products:
                        products.append(clean_name)
            elif isinstance(p, str) and not is_navigation_or_ui_noise(p):
                clean_name = p.strip()
                if clean_name not in products:
                    products.append(clean_name)

        # Pull from facts if empty
        if not products:
            for f in grounded_facts:
                if f.fact_type in ("product_service", "product_feature"):
                    val = f.fact_value
                    name = val.get("name") if isinstance(val, dict) else str(val)
                    if name and isinstance(name, str) and not is_navigation_or_ui_noise(name):
                        clean_name = name.strip()
                        if clean_name not in products:
                            products.append(clean_name)

        # 3. Target Audiences
        raw_audiences = data.get("target_audience", [])
        audiences: List[str] = []
        for a in raw_audiences:
            if isinstance(a, dict):
                if bool(_get_attr_or_key(a, "is_rejected", False)):
                    continue
                a_val = a.get("value", a) if "value" in a else a
                if isinstance(a_val, dict):
                    a_name = a_val.get("segment") or a_val.get("audience") or a_val.get("target_audience")
                elif isinstance(a_val, str):
                    a_name = a_val
                else:
                    a_name = None
                if a_name and isinstance(a_name, str) and a_name.strip() not in audiences:
                    audiences.append(a_name.strip())
            elif isinstance(a, str) and a.strip() not in audiences:
                audiences.append(a.strip())

        if not audiences:
            for f in grounded_facts:
                if f.fact_type == "target_audience":
                    val = f.fact_value
                    name = val.get("segment") if isinstance(val, dict) else str(val)
                    if name and name.strip() not in audiences:
                        audiences.append(name.strip())

        # 4. Use Cases
        raw_use_cases = data.get("use_cases", [])
        use_cases: List[str] = []
        for uc in raw_use_cases:
            if isinstance(uc, dict):
                if bool(_get_attr_or_key(uc, "is_rejected", False)):
                    continue
                uc_val = uc.get("value", uc) if "value" in uc else uc
                if isinstance(uc_val, dict):
                    uc_title = uc_val.get("title") or uc_val.get("use_case") or uc_val.get("description")
                elif isinstance(uc_val, str):
                    uc_title = uc_val
                else:
                    uc_title = None
                if uc_title and isinstance(uc_title, str):
                    for item in decompose_compound_capabilities(uc_title):
                        if item and item.strip() and item.strip() not in use_cases:
                            use_cases.append(item.strip())
            elif isinstance(uc, str):
                for item in decompose_compound_capabilities(uc):
                    if item and item.strip() and item.strip() not in use_cases:
                        use_cases.append(item.strip())

        if not use_cases:
            for f in grounded_facts:
                if f.fact_type == "use_case":
                    val = f.fact_value
                    name = (val.get("title") or val.get("use_case") or val.get("description")) if isinstance(val, dict) else str(val)
                    if name:
                        for item in decompose_compound_capabilities(str(name)):
                            if item and item.strip() and item.strip() not in use_cases:
                                use_cases.append(item.strip())

        # 5. Pricing Models
        raw_pricing = data.get("pricing_information", [])
        pricing_models: List[str] = []
        for pr in raw_pricing:
            if isinstance(pr, dict):
                if bool(_get_attr_or_key(pr, "is_rejected", False)):
                    continue
                pr_val = pr.get("value", pr) if "value" in pr else pr
                if isinstance(pr_val, dict):
                    model_str = pr_val.get("plan_name") or pr_val.get("model") or pr_val.get("details")
                elif isinstance(pr_val, str):
                    model_str = pr_val
                else:
                    model_str = None
                if model_str and isinstance(model_str, str) and model_str.strip() not in pricing_models:
                    pricing_models.append(model_str.strip())
            elif isinstance(pr, str) and pr.strip() not in pricing_models:
                pricing_models.append(pr.strip())

        if not pricing_models:
            for f in grounded_facts:
                if f.fact_type == "pricing":
                    val = f.fact_value
                    name = val.get("plan_name") if isinstance(val, dict) else str(val)
                    if name and name.strip() not in pricing_models:
                        pricing_models.append(name.strip())

        # 6. Differentiators
        raw_diffs = data.get("differentiators", [])
        differentiators: List[str] = []
        for d in raw_diffs:
            if isinstance(d, dict):
                if bool(_get_attr_or_key(d, "is_rejected", False)):
                    continue
                d_val = d.get("value", d) if "value" in d else d
                if isinstance(d_val, dict):
                    d_str = d_val.get("claim") or d_val.get("differentiator") or d_val.get("description")
                elif isinstance(d_val, str):
                    d_str = d_val
                else:
                    d_str = None
                if d_str and isinstance(d_str, str) and d_str.strip() not in differentiators:
                    differentiators.append(d_str.strip())
            elif isinstance(d, str) and d.strip() not in differentiators:
                differentiators.append(d.strip())

        if not differentiators:
            for f in grounded_facts:
                if f.fact_type == "differentiator":
                    val = f.fact_value
                    name = val.get("claim") if isinstance(val, dict) else str(val)
                    if name and name.strip() not in differentiators:
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
