"""Internal data models for the Engine 2 prompt generation pipeline."""
from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field

from app.core.brand_identity import registrable_domain, registrable_label


class GroundedFact(BaseModel):
    id: Optional[str] = None
    fact_type: str
    fact_value: Any
    confidence: float = 1.0
    user_confirmed: bool = False
    source_url: Optional[str] = None
    evidence_snippet: Optional[str] = None
    supporting_evidence: List[Dict[str, Any]] = []
    extraction_method: Optional[str] = None


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

    def get_forbidden_brand_tokens(self) -> List[str]:
        """Return list of lowercase tokens associated with the target brand identity."""
        tokens = set()
        if self.business_name:
            b_clean = self.business_name.strip().lower()
            if len(b_clean) >= 3:
                tokens.add(b_clean)
            # Add significant word tokens (e.g. 'OpenRouter' -> 'openrouter', 'Aurora AI' -> 'aurora')
            for part in b_clean.split():
                if len(part) >= 4 and part not in ("platform", "technologies", "software", "solutions", "group", "cloud", "tools"):
                    tokens.add(part)
        if self.domain:
            d_clean = self.domain.lower().replace("www.", "").strip()
            tokens.add(d_clean)
            tokens.add(registrable_domain(d_clean))
            host = registrable_label(d_clean)
            if len(host) >= 3 and host not in ("app", "com", "net", "org", "dev", "io"):
                tokens.add(host)
        return sorted(tokens, key=len, reverse=True)

    def clean_text_of_brand(self, text: str) -> str:
        """Strip brand identity mentions, possessives, and domain tokens from text."""
        if not text:
            return ""
        import re
        result = text
        for token in self.get_forbidden_brand_tokens():
            # Possessive (e.g. "Nike's ", "OpenRouter's ")
            result = re.sub(rf"\b{re.escape(token)}'s\b", "", result, flags=re.IGNORECASE)
            result = re.sub(rf"\b{re.escape(token)}’s\b", "", result, flags=re.IGNORECASE)
            # Direct word boundary match
            result = re.sub(rf"\b{re.escape(token)}\b", "", result, flags=re.IGNORECASE)
        # Clean extra punctuation and double whitespace
        result = re.sub(r"\s+", " ", result).strip()
        result = re.sub(r"^[,\-–—:\s]+|[,\-–—:\s]+$", "", result).strip()
        return result

    def get_primary_category(self) -> Optional[str]:
        """Derive high-level industry or category grounded strictly in profile evidence."""
        if self.industry and self.industry.strip():
            return self.industry.strip()
        for f in self.facts:
            if f.fact_type in ("industry", "category"):
                val = f.fact_value.get("name") if isinstance(f.fact_value, dict) else str(f.fact_value)
                if val and val.strip():
                    return val.strip()
        # Fallback to first non-branded product or use case if available
        for p in self.get_clean_products():
            if len(p) >= 4:
                return p
        for u in self.get_clean_use_cases():
            if len(u) >= 4:
                return u
        return None

    def get_clean_products(self) -> List[str]:
        """Return products cleaned of target brand names."""
        cleaned = []
        for p in self.products_and_services:
            c = self.clean_text_of_brand(p)
            if c and len(c) >= 3 and c not in cleaned:
                cleaned.append(c)
        return cleaned

    def get_clean_audiences(self) -> List[str]:
        """Return audiences cleaned of target brand names."""
        cleaned = []
        for a in self.target_audiences:
            c = self.clean_text_of_brand(a)
            if c and len(c) >= 3 and c not in cleaned:
                cleaned.append(c)
        return cleaned

    def get_clean_use_cases(self) -> List[str]:
        """Return use cases cleaned of target brand names."""
        cleaned = []
        for u in self.use_cases:
            c = self.clean_text_of_brand(u)
            if c and len(c) >= 3 and c not in cleaned:
                cleaned.append(c)
        return cleaned

    def get_clean_differentiators(self) -> List[str]:
        """Return differentiators cleaned of target brand names."""
        cleaned = []
        for d in self.differentiators:
            c = self.clean_text_of_brand(d)
            if c and len(c) >= 3 and c not in cleaned:
                cleaned.append(c)
        return cleaned

    def get_domain_archetype(self) -> str:
        """
        Classifies the brand's verified domain into an archetype:
        - 'footwear_apparel': Athletic footwear, running shoes, sneakers, trainers, sportswear
        - 'developer_infrastructure': Cloud infrastructure, APIs, SDKs, model routing, dev tools
        - 'enterprise_saas': Project management, CRM, ERP, customer service, analytics
        - 'creative_tools': UI/UX design, AI video, image generation, creative suites
        - 'consumer_ecommerce': Online stores, retail goods, direct-to-consumer products
        - 'general': Fallback for other domains
        """
        corpus = " ".join([
            self.industry or "",
            " ".join(self.products_and_services),
            " ".join(self.use_cases),
            self.tagline_or_description or "",
            " ".join(self.differentiators),
        ]).lower()

        footwear_keywords = (
            "footwear", "running shoe", "running shoes", "athletic shoe", "athletic shoes",
            "sneakers", "trainers", "marathon shoe", "road running", "trail running",
            "sports shoe", "cushioned shoe", "apparel", "sportswear", "activewear"
        )
        if any(kw in corpus for kw in footwear_keywords):
            return "footwear_apparel"

        dev_infra_keywords = (
            "developer tools", "cloud infrastructure", "api gateway", "model routing",
            "llm api", "hosting platform", "deployment platform", "ci/cd", "devops",
            "database", "sdk", "backend", "serverless", "kubernetes", "open-source software"
        )
        if any(kw in corpus for kw in dev_infra_keywords):
            return "developer_infrastructure"

        creative_keywords = (
            "design tool", "video generation", "creative suite", "vector graphics",
            "image generation", "animation", "ui design", "3d rendering", "video editor"
        )
        if any(kw in corpus for kw in creative_keywords):
            return "creative_tools"

        enterprise_keywords = (
            "project management", "issue tracking", "crm", "erp", "ticketing system",
            "customer support", "business intelligence", "team collaboration", "b2b saas",
            "workflow automation", "compliance management"
        )
        if any(kw in corpus for kw in enterprise_keywords):
            return "enterprise_saas"

        ecommerce_keywords = (
            "e-commerce", "online store", "shopping cart", "retail platform", "merchandise"
        )
        if any(kw in corpus for kw in ecommerce_keywords):
            return "consumer_ecommerce"

        return "general"

    def get_clean_subcategories(self) -> List[str]:
        """
        Extracts verified subcategories or product categories from facts and classified taxonomy,
        cleaned of brand names and suitable for natural query slotting.
        Avoids substituting raw specific product names as category concepts.
        """
        subcats = []
        archetype = self.get_domain_archetype()

        corpus = " ".join([
            self.industry or "",
            " ".join(self.products_and_services),
            " ".join(self.use_cases),
            self.tagline_or_description or "",
        ]).lower()

        if archetype in ("footwear_apparel", "sportswear_sporting_goods"):
            footwear_subcat_patterns = [
                "running shoes", "trail running shoes", "road running shoes",
                "athletic footwear", "trainers", "sneakers", "marathon shoes",
                "cushioned running shoes", "lightweight trainers", "everyday running shoes"
            ]
            for pat in footwear_subcat_patterns:
                if pat in corpus and pat not in subcats:
                    subcats.append(pat)

            apparel_subcat_patterns = [
                "athletic apparel", "sports clothing", "running gear", "activewear",
                "training t-shirts", "workout tops", "athletic pants"
            ]
            for pat in apparel_subcat_patterns:
                if pat in corpus and pat not in subcats:
                    subcats.append(pat)

            gear_subcat_patterns = [
                "training bags", "gym duffel bags", "sports backpacks", "fitness gear", "outdoor equipment"
            ]
            for pat in gear_subcat_patterns:
                if pat in corpus and pat not in subcats:
                    subcats.append(pat)

        elif archetype in ("developer_infrastructure", "saas_software"):
            tech_patterns = [
                "developer tools", "cloud infrastructure", "api platforms",
                "model routing", "database systems", "workflow automation software"
            ]
            for pat in tech_patterns:
                if pat in corpus and pat not in subcats:
                    subcats.append(pat)

        if not subcats:
            cat = self.get_primary_category()
            if cat:
                clean_cat = self.clean_text_of_brand(cat)
                if len(clean_cat) >= 3 and not any(p in clean_cat.lower() for p in ("select size", "sale", "new & featured")):
                    subcats.append(clean_cat)

        return subcats or ["athletic footwear and gear" if archetype in ("footwear_apparel", "sportswear_sporting_goods") else "solutions in this category"]

    def get_article_topics(self) -> List[str]:
        """
        Extracts educational, buying-guide, or comparison topics derived from
        verified blog/article facts.
        """
        topics = []
        for f in self.facts:
            # Industry or company overview facts are not article topics
            if f.fact_type in ("industry", "business_name", "supported_language", "company_description"):
                continue

            is_article_source = False
            for supp in f.supporting_evidence:
                if supp.get("source_type") in ("article_topic", "blog_article") or "article" in supp.get("source_type", ""):
                    is_article_source = True
                    break
            if f.extraction_method in ("article_topic_heuristic", "blog_post_extractor"):
                is_article_source = True

            val = f.fact_value
            text_val = val if isinstance(val, str) else (val.get("title") or val.get("name") if isinstance(val, dict) else str(val))
            if text_val and (is_article_source or any(k in str(text_val).lower() for k in ("how to choose", "vs", "versus", "guide to", "best for", "what to look for"))):
                cleaned = self.clean_text_of_brand(str(text_val))
                if cleaned and len(cleaned) >= 8 and cleaned not in topics:
                    topics.append(cleaned)
        return topics


class PlannedPromptSlot(BaseModel):
    category: str
    intent: str
    buying_stage: str
    subcategory: Optional[str] = None
    target_dimension: Optional[str] = None  # e.g., product name, audience segment, differentiator
    dimension_value: Optional[str] = None
    source_fact_ids: List[str] = []
    evidence_snippet: Optional[str] = None
    archetype: Optional[str] = None
    is_article_inspired: bool = False


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
    subcategory: Optional[str] = None
    archetype: Optional[str] = None
    target_audience: Optional[str] = None
    target_product_service: Optional[str] = None
    language: str = "en"
    provenance_fact_ids: List[str] = []
    grounding_evidence: List[str] = []
    scores: Dict[str, float] = {}
    quality_score: float = 1.0
    is_approved: bool = False
    lifecycle_status: str = "proposed"  # generated -> validated -> proposed -> approved/rejected -> tracked
    rejection_reason: Optional[str] = None
    template_version: Optional[str] = None
