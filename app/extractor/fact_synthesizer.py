"""Deterministic Brand Fact Synthesizer and Provenance Tracker.
Extracts structured brand profile evidence from crawled pages and structured data
without requiring paid LLM calls. Maintains complete provenance and confidence scores.
"""
import re
import json
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse
from app.db.models import CrawledPage, BrandFact


def canonical_fact_key(fact_type: str, value: Any) -> str:
    """Return a stable identity for the claim, excluding page-specific metadata."""
    if isinstance(value, dict):
        identity_fields = {
            "product_service": ("name",),
            "product_feature": (),
            "pricing": ("plan_name", "amount", "currency", "unit", "billing_basis", "associated_product"),
            "contact_info": ("type", "value", "url"),
            "faq": ("question",),
        }.get(fact_type)
        if identity_fields:
            value = {key: value.get(key) for key in identity_fields}
    normalized = json.dumps(value, sort_keys=True, ensure_ascii=True, separators=(",", ":")) if not isinstance(value, str) else re.sub(r"\s+", " ", value).strip().lower()
    return f"{fact_type}:{normalized.lower()}"


def _deduplicate_facts(facts: List[BrandFact]) -> List[BrandFact]:
    """Collapse equivalent claims while retaining every supporting source."""
    merged: Dict[str, BrandFact] = {}
    for fact in facts:
        key = canonical_fact_key(fact.fact_type, fact.fact_value)
        fact.fact_key = key
        fact.last_seen_at = fact.updated_at
        if key not in merged:
            if not fact.supporting_evidence:
                fact.supporting_evidence = [{
                    "source_url": fact.source_url,
                    "snippet": fact.evidence_snippet,
                    "source_type": fact.extraction_method,
                    "provenance_type": "structured_metadata" if "json" in fact.extraction_method else "verbatim_text",
                    "heuristic_confidence": fact.confidence
                }]
            merged[key] = fact
            continue
        existing = merged[key]
        evidence = list(existing.supporting_evidence or [])
        candidate = {
            "source_url": fact.source_url,
            "snippet": fact.evidence_snippet,
            "source_type": fact.extraction_method,
            "provenance_type": "structured_metadata" if "json" in fact.extraction_method else "verbatim_text",
            "heuristic_confidence": fact.confidence
        }
        if candidate not in evidence:
            evidence.append(candidate)
        existing.supporting_evidence = evidence
        if fact.confidence > existing.confidence:
            existing.confidence = fact.confidence
            existing.source_page_id = fact.source_page_id
            existing.source_url = fact.source_url
            existing.evidence_snippet = fact.evidence_snippet
    return list(merged.values())



EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"(\+?[0-9]{1,3}[-.\s]?)?(\(?\d{3}\)?[-.\s]?)[\d.-]{7,10}")
PRICING_TIER_REGEX = re.compile(r"\b(Free|Starter|Basic|Standard|Plus|Pro|Professional|Premium|Growth|Business|Enterprise|Team|Personal|Developer|Core)\b", re.I)
PRICE_CURRENCY_REGEX = re.compile(r"(\$|€|£|₹)\s?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:/\s*(?:month|mo|year|yr|user|seat))?", re.I)
ALLOWANCE_INDICATORS = (
    "of list price inference", "list price inference", "with no fees", "allowance",
    "byok limit", "byok limits", "spend limit", "credit limit", "included credit",
    "included credits", "free credit", "free credits", "usage limit", "monthly allowance",
    "free requests", "free tier allowance", "inference / month with no fees",
    "inference / month", "tokens / month with no fees", "requests / month with no fees"
)
USAGE_UNIT_REGEX = re.compile(
    r"(?:/\s*(?:m\b|million|k\b|thousand|1m|1k|1,000|token|tokens|input\s*tokens?|output\s*tokens?|credit|credits|request|requests|query|queries|gb|character|characters|image|images|sec|second|hour)|"
    r"per\s+(?:m\b|million|k\b|thousand|1m|1k|1,000|token|tokens|input\s*tokens?|output\s*tokens?|credit|credits|request|requests|query|queries|gb|character|characters|image|images|sec|second|hour))",
    re.I
)

DISALLOWED_PRODUCT_NAMES = {
    # Continents & Regions
    "africa", "americas", "asia pacific", "europe", "middle east",
    "north america", "south america", "latin america", "oceania", "antarctica",
    "united states", "global", "worldwide", "international",
    # Generic Navigation & Support / Auth Actions
    "get help", "help", "contact us", "customer service", "sign in", "sign up",
    "log in", "cart", "bag", "checkout", "view cart", "order status", "track order",
    "track your order", "order tracking", "size guide", "size chart", "gift cards",
    "gift card", "filter by", "sort by", "shop by size", "shipping policy", "refund policy",
    "shipping & delivery", "returns", "return policy", "terms of sale", "privacy policy",
    "cookie settings", "site feedback", "find a store", "become a member",
    "send us feedback", "about us", "careers", "news", "investors", "sustainability",
    "menu", "navigation", "footer", "header", "quick links", "company", "explore",
    "trending now", "shop by category", "featured", "trending", "latest in clothing",
    "featured footwear", "shop all", "shop", "all products", "categories", "overview",
    "what we do", "capabilities", "solutions", "all-in-one", "features", "reviews",
    "specifications", "description", "details", "materials", "size & fit",
    # Marketing action verbs & generic section headings
    "measure", "recommend", "act", "deploy", "scale", "ship", "build", "collaborate",
    "all platform features", "frequently asked questions", "faq", "talk to us",
    "vlad magdalin"
}

GENERIC_SINGLE_WORD_HEADINGS = {
    "measure", "recommend", "act", "build", "ship", "deploy", "scale",
    "product", "products", "resources", "company", "trust", "solutions",
    "platform", "pricing", "customers", "docs", "documentation", "enterprise",
    "blog", "news", "features", "careers", "legal", "security", "overview",
    "about", "contact", "support", "help", "login", "signup", "register",
    "community", "partners", "integrations", "templates", "guides", "changelog"
}

NON_PRODUCT_PREFIXES = (
    "get ", "talk to ", "contact ", "sign ", "explore ", "learn ", "see ",
    "try ", "join ", "read ", "watch ", "execute ", "turn ", "understand ",
    "know ", "start ", "build for ", "loved by ", "trusted by ", "from ",
    "all platform ", "teams ship ", "connect your ", "how teams ", "find ", "choose ",
    "power ", "trusted in ", "proven at ", "driven by ", "integrate your "
)

AUDIENCE_ROLE_WORDS = {
    # Engineering, Design & Operations
    "team", "teams", "developer", "developers", "engineer", "engineers",
    "designer", "designers", "creator", "creators", "marketer", "marketers",
    "founder", "founders", "builder", "builders", "architect", "architects",
    "coder", "coders", "programmer", "programmers", "operator", "operators",
    # Business, Enterprise & SMB
    "enterprise", "enterprises", "business", "businesses", "company", "companies",
    "startup", "startups", "scaleup", "scaleups", "organization", "organizations",
    "agency", "agencies", "customer", "customers", "user", "users", "client", "clients",
    "professional", "professionals", "individual", "individuals", "smb", "smbs", "b2b", "b2c",
    "leader", "leaders", "manager", "managers", "executive", "executives", "director", "directors",
    # Specialized, Commerce & Creative
    "freelancer", "freelancers", "consultant", "consultants", "contractor", "contractors",
    "writer", "writers", "author", "authors", "blogger", "bloggers",
    "analyst", "analysts", "scientist", "scientists", "researcher", "researchers", "academic", "academics",
    "institution", "institutions", "nonprofit", "nonprofits", "non-profit", "non-profits",
    "school", "schools", "university", "universities",
    "retailer", "retailers", "merchant", "merchants", "buyer", "buyers", "seller", "sellers",
    "specialist", "specialists", "practitioner", "practitioners",
    # Consumer & Sports
    "runner", "runners", "athlete", "athletes", "enthusiast", "enthusiasts",
    "beginner", "beginners", "expert", "experts", "student", "students", "people", "everyone",
    "consumer", "consumers", "community", "communities"
}

AUDIENCE_DISALLOWED_WORDS = {
    "speed", "scale", "performance", "privacy", "security", "the future",
    "modern web", "the cloud", "simplicity", "reliability", "efficiency",
    "collaboration", "growth", "today's reality", "the ai era", "tomorrow",
    "production", "the pavement", "any screen", "all devices"
}


LEGAL_AND_DOC_TERMS = {
    "recitals", "recital", "license grant", "definitions", "amendment", "notices",
    "in-region routing", "routing", "restrictions", "data processing", "proprietary rights",
    "organizational account management", "ai model terms", "fees and minimum spend requirement",
    "minimum spend requirement", "fees and payment", "acceptable use", "terms of service",
    "terms of use", "privacy policy", "cookie policy", "confidentiality", "indemnification",
    "limitation of liability", "governing law", "arbitration", "severability", "warranties",
    "intellectual property", "order form", "statement of work", "service level agreement",
    "dispute resolution", "general provisions", "termination", "enterprise access agreement",
    "service agreement", "master services agreement", "code of conduct", "audit rights",
    "subprocessors", "sub-processors", "security practices", "license", "licenses"
}


def is_valid_product_candidate(name: str, brand_name: str = "") -> bool:
    # Clean zero-width and non-breaking space characters
    clean = re.sub(r"[\u200b\u200c\u200d\ufeff\xa0]", " ", name).strip()
    clean = re.sub(r"\s+", " ", clean).strip()
    lower = clean.lower()
    if not clean:
        return False
    if brand_name and lower == brand_name.strip().lower():
        return False
    if lower in DISALLOWED_PRODUCT_NAMES or lower in LEGAL_AND_DOC_TERMS:
        return False
    if clean.startswith("#"):
        return False
    if any(lower.startswith(pfx) for pfx in NON_PRODUCT_PREFIXES):
        return False
    if clean.endswith((".", "!", "?")):
        return False
    if lower.endswith(" in action"):
        return False
    # Reject numbered legal clauses (e.g., 2.1 License, 2.2 AI Model Terms, 5.1 Fees, Schedule 1:, Exhibit A)
    if re.match(r"^\d+\.\d+", clean):
        return False
    if re.match(r"^(\d+(\.\d+)*|[a-zA-Z]\.|\([a-z0-9]+\))\s+", clean):
        return False
    # Reject SKU, item #, style codes, and inventory identifiers
    if re.match(r"^(sku[:\s\-]|item\s*#|style\s*#|style\s+code|upc[:\s]|product\s+id[:\s])", lower):
        return False
    # Reject legal clauses, contracts, disclaimers, and boilerplate agreements
    if any(k in lower for k in (
        "terms of", "privacy policy", "cookie policy", "disclaimer", "indemnification",
        "governing law", "arbitration", "severability", "limitation of liability",
        "confidentiality", "warranties", "intellectual property", "acceptable use",
        "fees and payment", "term and termination", "general provisions",
        "enterprise access agreement", "access agreement", "service agreement",
        "model terms", "data processing", "proprietary rights", "account management",
        "minimum spend", "license agreement"
    )):
        return False
    if clean.endswith((" Agreement", " Terms", " Policy", " Addendum", " Clause", " Provisions")):
        return False
    if any(lower.startswith(pfx) for pfx in ("schedule", "exhibit", "section ", "article ", "clause ")):
        return False
    # Reject doc/guide headings (e.g. "Using in-region routing", "How to configure", "Introduction to...")
    if any(lower.startswith(pfx) for pfx in (
        "using ", "how to ", "how we ", "how it ", "what is ", "what are ",
        "understanding ", "getting started", "guide to ", "quickstart",
        "overview of ", "introduction to ", "feature availability", "troubleshooting",
        "about ", "view ", "click ", "read "
    )):
        return False
    # Reject internal sentence breaks while preserving tech extensions like Next.js or v0.dev
    if any(punct in clean for punct in ("!", "?")):
        return False
    if re.search(r"\.\s+[A-Za-z]", clean):
        return False
    if "—" in clean or "--" in clean:
        return False
    words = clean.split()
    if not (1 <= len(words) <= 7):
        return False
    if len(clean) > 55:
        return False
    if len(words) == 1 and lower in GENERIC_SINGLE_WORD_HEADINGS:
        return False
    return True


def is_valid_use_case(val: str) -> bool:
    clean = re.sub(r"[\u200b\u200c\u200d\ufeff\xa0]", " ", val).strip(" \t\r\n,;:-–—\"'“”()[]")
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean or len(clean) < 8 or len(clean) > 110:
        return False
    lower = clean.lower()

    # Must start with letter/number
    if not clean[0].isalnum():
        return False

    # Reject leading grammar fragments or dangling words
    if re.match(r"^(s[\s,]|are\b|is\b|was\b|were\b|grew\b|has\b|have\b|and\b|or\b|but\b|so\b|because\b|with\b|for\b|in\b|on\b|at\b|to\b|from\b|between\b|split\b|versus\b|vs\b|compared\b|as\b|while\b|can\b|will\b|resembling\b|ranging\b|including\b|such as\b)", lower):
        return False

    # Reject trailing dangling prepositions/conjunctions
    if re.search(r"\b(and|or|with|for|the|a|an|to|of|in|on|at|by|from|between|versus|vs|such as|including)$", lower):
        return False

    words = clean.split()
    if not (2 <= len(words) <= 12):
        return False

    # Reject pricing, token volume, benchmark comparisons, rate limits, performance metrics
    if any(bad in lower for bad in (
        "chinese oss", "row oss", "open-source software", "market share",
        "benchmark", "disclaimer", "all rights reserved", "limitation",
        "token", "tokens", "per token", "pricing", "price", "cost", "$", "€", "£",
        "request limit", "rate limit", "latency", "tpm", "rpm", "context window",
        "according to", "said ", "says ", "terms of", "privacy", "cookie",
        "copyright", "trademark", "warranty", "confidential", "model quality",
        "model reliability", "high quality", "request limits", "supported language"
    )):
        return False

    return True


def is_valid_target_audience(val: str) -> bool:
    clean = re.sub(r"[\u200b\u200c\u200d\ufeff\xa0]", " ", val).strip(" \t\r\n,;:-–—\"'“”()[]")
    clean = clean.rstrip(".").strip()
    clean = re.sub(r"\s+", " ", clean).strip()
    if not clean or len(clean) < 5 or len(clean) > 85:
        return False
    lower = clean.lower()

    if not clean[0].isalnum():
        return False

    if re.match(r"^(s[\s,]|are\b|is\b|was\b|were\b|and\b|or\b|but\b|with\b|for\b|to\b|from\b|in\b|on\b|at\b)", lower):
        return False

    words = clean.split()
    if not (1 <= len(words) <= 12):
        return False

    if any(bad in lower for bad in (
        "chinese oss", "row oss", "benchmark", "token", "pricing", "$", "request limit",
        "rate limit", "latency", "terms of", "privacy", "disclaimer", "all rights reserved",
        "model quality", "reliability", "language", "python", "javascript", "caption:",
        "communication between", "said "
    )):
        return False

    if lower in AUDIENCE_DISALLOWED_WORDS:
        return False
    if any(lower.startswith(bad) or lower == bad for bad in ("enterprise scale", "speed", "performance", "privacy", "security", "the future", "modern aesthetics")):
        return False

    # Must contain recognized audience role words or persona indicators
    words_set = set(re.findall(r"\b[a-zA-Z]+\b", lower))
    if not words_set.intersection(AUDIENCE_ROLE_WORDS) and not any(k in lower for k in ("who want", "looking to", "those who", "built for")):
        return False

    return True


class FactSynthesizer:
    def __init__(
        self,
        brand_id: str,
        profile_version: int = 1,
        user_business_name: Optional[str] = None,
        user_industry: Optional[str] = None,
        user_target_market: Optional[str] = None,
        user_language: Optional[str] = None
    ):
        self.brand_id = brand_id
        self.profile_version = profile_version
        self.user_business_name = user_business_name
        self.user_industry = user_industry
        self.user_target_market = user_target_market
        self.user_language = user_language

    def synthesize_facts(self, pages: List[CrawledPage]) -> List[BrandFact]:
        """
        Synthesizes a list of BrandFact records from the list of crawled pages.
        """
        facts: List[BrandFact] = []
        if not pages:
            return facts

        homepage = next((p for p in pages if p.page_type == "homepage"), pages[0])

        # 1. User Inputs (Highest Confidence)
        if self.user_business_name:
            facts.append(BrandFact(
                brand_id=self.brand_id,
                profile_version=self.profile_version,
                fact_type="business_name",
                fact_value=self.user_business_name,
                source_url=homepage.final_url,
                evidence_snippet=f"User specified business name: {self.user_business_name}",
                extraction_method="user_input",
                confidence=1.0,
                user_confirmed=True
            ))

        if self.user_industry:
            facts.append(BrandFact(
                brand_id=self.brand_id,
                profile_version=self.profile_version,
                fact_type="industry",
                fact_value=self.user_industry,
                source_url=homepage.final_url,
                evidence_snippet=f"User specified industry: {self.user_industry}",
                supporting_evidence=[{
                    "source_url": homepage.final_url,
                    "snippet": f"User specified industry: {self.user_industry}",
                    "source_type": "user_input",
                    "provenance_type": "user_specified",
                    "heuristic_confidence": 1.0
                }],
                extraction_method="user_input",
                confidence=1.0,
                user_confirmed=True
            ))
        else:
            inferred_cat = self._extract_industry_or_category(homepage, pages)
            if inferred_cat:
                facts.append(inferred_cat)


        if self.user_target_market:
            facts.append(BrandFact(
                brand_id=self.brand_id,
                profile_version=self.profile_version,
                fact_type="geographic_market",
                fact_value=self.user_target_market,
                source_url=homepage.final_url,
                evidence_snippet=f"User specified target market: {self.user_target_market}",
                extraction_method="user_input",
                confidence=1.0,
                user_confirmed=True
            ))

        # 2. Extract Business Name if not set by user
        if not self.user_business_name:
            bname, bpage, bsnippet, bmethod, bconf = self._extract_business_name(homepage, pages)
            if bname:
                facts.append(BrandFact(
                    brand_id=self.brand_id,
                    profile_version=self.profile_version,
                    fact_type="business_name",
                    fact_value=bname,
                    source_page_id=bpage.id if bpage else None,
                    source_url=bpage.final_url if bpage else homepage.final_url,
                    evidence_snippet=bsnippet,
                    extraction_method=bmethod,
                    confidence=bconf,
                    user_confirmed=False
                ))

        # 3. Company Description
        desc, dpage, dsnippet, dmethod, dconf = self._extract_company_description(homepage, pages)
        if desc:
            facts.append(BrandFact(
                brand_id=self.brand_id,
                profile_version=self.profile_version,
                fact_type="company_description",
                fact_value=desc,
                source_page_id=dpage.id if dpage else None,
                source_url=dpage.final_url if dpage else homepage.final_url,
                evidence_snippet=dsnippet,
                extraction_method=dmethod,
                confidence=dconf,
                user_confirmed=False
            ))

        # 4. JSON-LD Structured Data Extraction (Organization, Products, FAQs, Contacts)
        self._extract_structured_data_facts(pages, facts)

        # 5. Products & Services from Page Headings & Product Pages
        effective_bname = self.user_business_name or bname or ""
        self._extract_products_and_features(pages, facts, brand_name=effective_bname)

        # 6. Target Audience & Use Cases
        self._extract_audience_and_use_cases(pages, facts)

        # 6b. Educational Content & Buying Guides from Articles/Blogs
        self._extract_educational_and_buying_guide_topics(pages, facts, brand_name=effective_bname)

        # 7. Pricing Information
        self._extract_pricing_facts(pages, facts)

        # 8. FAQs from FAQ/Help pages
        self._extract_faq_facts(pages, facts)

        # 9. Contact & Company Details (Email, phone, social)
        self._extract_contact_info(pages, facts)

        # 10. Supported Languages
        self._extract_languages(pages, facts)

        return _deduplicate_facts(facts)

    def _extract_industry_or_category(

        self,
        homepage: CrawledPage,
        pages: List[CrawledPage]
    ) -> Optional[BrandFact]:
        """
        Infers an industry or category grounded strictly in crawl evidence (DEF-E1-01).
        Checks structured data, definitional sentences in meta description, titles, and headings.
        Abstains cleanly if evidence is insufficient.
        """
        # 1. Structured data (Schema.org)
        for p in pages:
            for sdata in (p.structured_data or []):
                for cat_field in ("applicationCategory", "category", "genre"):
                    cat_val = sdata.get(cat_field)
                    if cat_val and isinstance(cat_val, str) and 3 <= len(cat_val.strip()) <= 60:
                        c_clean = cat_val.strip()
                        return BrandFact(
                            brand_id=self.brand_id,
                            profile_version=self.profile_version,
                            fact_type="industry",
                            fact_value=c_clean,
                            source_page_id=p.id,
                            source_url=p.final_url,
                            evidence_snippet=c_clean,
                            supporting_evidence=[{
                                "source_url": p.final_url,
                                "snippet": c_clean,
                                "source_type": "json_ld",
                                "provenance_type": "structured_metadata",
                                "heuristic_confidence": 0.95
                            }],
                            extraction_method="json_ld_schema",
                            confidence=0.95,
                            user_confirmed=False
                        )

        # 2. Definitional sentence in meta description, title, or hero text
        # e.g., "Linear is an issue tracking and project management tool designed for..."
        def_pattern = re.compile(
            r"\b(?:is|provides|offers)\s+(?:an?|the)\s+([A-Za-z0-9\s\-/&]{3,50}?)\s+(?:platform|software|tool|app|solution|infrastructure|system|suite|service)\b",
            re.IGNORECASE
        )

        sources_to_check = []
        if homepage.meta_description:
            sources_to_check.append((homepage.meta_description, "meta_description", homepage, 0.88))
        if homepage.title:
            sources_to_check.append((homepage.title, "title_heuristic", homepage, 0.82))
        if homepage.extracted_text:
            paras = [p.strip() for p in homepage.extracted_text.split("\n\n") if len(p.strip()) > 20][:3]
            for para in paras:
                sources_to_check.append((para, "content_heuristic", homepage, 0.80))

        # Check other product/about pages if homepage didn't have it
        for page in pages:
            if page.id != homepage.id and page.page_type in ("about", "product_service"):
                if page.meta_description:
                    sources_to_check.append((page.meta_description, "meta_description", page, 0.85))
                if page.extracted_text:
                    first_p = page.extracted_text.split("\n\n")[0].strip()
                    if len(first_p) > 20:
                        sources_to_check.append((first_p, "content_heuristic", page, 0.78))

        for text_source, method, src_page, conf in sources_to_check:
            sentences = re.split(r"(?<=[.!?])\s+", text_source)
            for sent in sentences:
                m = def_pattern.search(sent)
                if m:
                    raw_cat = m.group(1).strip()
                    clean_words = [w for w in raw_cat.split() if w.lower() not in ("simple", "best", "all-in-one", "modern", "great", "powerful", "easy")]
                    if clean_words and len(" ".join(clean_words)) >= 4:
                        cat_str = " ".join(clean_words).title()
                        return BrandFact(
                            brand_id=self.brand_id,
                            profile_version=self.profile_version,
                            fact_type="industry",
                            fact_value=cat_str,
                            source_page_id=src_page.id if src_page else None,
                            source_url=src_page.final_url if src_page else homepage.final_url,
                            evidence_snippet=sent.strip(),
                            supporting_evidence=[{
                                "source_url": src_page.final_url if src_page else homepage.final_url,
                                "snippet": sent.strip(),
                                "source_type": method,
                                "provenance_type": "verbatim_text",
                                "heuristic_confidence": conf
                            }],
                            extraction_method=method,
                            confidence=conf,
                            user_confirmed=False
                        )

        # 3. Known industry taxonomy keyword clusters in page title, description, or headings
        CATEGORY_TAXONOMY = [
            (("issue tracking", "project management", "sprint planning", "bug tracking"), "Project Management & Issue Tracking"),
            (("developer tools", "ci/cd", "deployment platform", "frontend cloud", "hosting platform"), "Developer Tools & Cloud Infrastructure"),
            (("payments platform", "financial infrastructure", "payment processing", "billing platform"), "Fintech & Payments"),
            ((
                "artificial intelligence", "generative ai", "large language model", "large language models", "llm",
                "machine learning platform", "machine learning", "computer vision", "conversational ai",
                "ai assistant", "ai chat", "ai models", "ai model", "ai video", "video generation",
                "code with ai", "work with ai", "chat with ai", "powered by ai"
            ), "Artificial Intelligence & Machine Learning"),
            (("e-commerce", "online store", "shopping cart", "retail platform", "merchandise"), "E-Commerce & Retail"),
            (("cybersecurity", "identity management", "access management", "threat detection", "endpoint security"), "Cybersecurity & Identity"),
            (("customer support", "crm", "help desk", "customer service platform", "ticketing system"), "Customer Support & CRM"),
            (("design tool", "vector graphics", "creative suite", "ui design", "prototyping"), "Design & Creative Tools"),
            (("analytics platform", "business intelligence", "product analytics", "data visualization"), "Data Analytics & BI"),
            (("team collaboration", "team chat", "knowledge base", "workspace platform"), "Team Collaboration & Productivity"),
            (("running shoes", "athletic footwear", "sneakers", "trainers", "sports footwear", "trail running shoes", "road running shoes", "cushioned shoes"), "Footwear & Athletic Shoes"),
            (("apparel", "footwear", "clothing", "sportswear", "activewear"), "Apparel & Sportswear"),
        ]

        for text_source, method, src_page, conf in sources_to_check:
            text_lower = text_source.lower()
            if re.search(r"\b(?:is|with|using|built with|powered by)\s+ai\b", text_lower):
                sentences = re.split(r"(?<=[.!?])\s+", text_source)
                verbatim = next((s.strip() for s in sentences if re.search(r"\bai\b", s, re.I)), text_source[:200])
                return BrandFact(
                    brand_id=self.brand_id,
                    profile_version=self.profile_version,
                    fact_type="industry",
                    fact_value="Artificial Intelligence & Machine Learning",
                    source_page_id=src_page.id if src_page else None,
                    source_url=src_page.final_url if src_page else homepage.final_url,
                    evidence_snippet=verbatim,
                    supporting_evidence=[{
                        "source_url": src_page.final_url if src_page else homepage.final_url,
                        "snippet": verbatim,
                        "source_type": method,
                        "provenance_type": "verbatim_text",
                        "heuristic_confidence": 0.85
                    }],
                    extraction_method=method,
                    confidence=0.85,
                    user_confirmed=False
                )
            for keywords, tax_name in CATEGORY_TAXONOMY:
                for kw in keywords:
                    if kw in text_lower:
                        sentences = re.split(r"(?<=[.!?])\s+", text_source)
                        verbatim = next((s.strip() for s in sentences if kw in s.lower()), text_source[:200])
                        return BrandFact(
                            brand_id=self.brand_id,
                            profile_version=self.profile_version,
                            fact_type="industry",
                            fact_value=tax_name,
                            source_page_id=src_page.id if src_page else None,
                            source_url=src_page.final_url if src_page else homepage.final_url,
                            evidence_snippet=verbatim,
                            supporting_evidence=[{
                                "source_url": src_page.final_url if src_page else homepage.final_url,
                                "snippet": verbatim,
                                "source_type": "taxonomy_keyword",
                                "provenance_type": "verbatim_text",
                                "heuristic_confidence": 0.75
                            }],
                            extraction_method="taxonomy_keyword",
                            confidence=0.75,
                            user_confirmed=False
                        )

        # 4. Abstain cleanly if insufficient evidence
        return None

    def _extract_business_name(

        self,
        homepage: CrawledPage,
        pages: List[CrawledPage]
    ) -> Tuple[Optional[str], Optional[CrawledPage], Optional[str], str, float]:
        # Check structured data first
        for p in pages:
            for sdata in (p.structured_data or []):
                stype = sdata.get("@type")
                if stype in ("Organization", "Corporation", "LocalBusiness", "WebSite"):
                    name = sdata.get("name") or sdata.get("legalName")
                    if name and isinstance(name, str):
                        return name.strip(), p, f"Structured data {stype} name: {name}", "json_ld_schema", 0.95

        # Check title split on homepage: "Name - Slogan" or "Name | Slogan"
        if homepage.title:
            for sep in [" | ", " - ", " – ", " — ", " : "]:
                if sep in homepage.title:
                    candidate = homepage.title.split(sep)[0].strip()
                    if 2 <= len(candidate) <= 50:
                        return candidate, homepage, f"Page title segment: '{candidate}'", "title_heuristic", 0.85

            # If no separator, use title if concise
            if len(homepage.title.strip()) <= 40:
                return homepage.title.strip(), homepage, f"Full page title: '{homepage.title}'", "title_heuristic", 0.70

        # Fallback to domain name root
        domain_root = urlparse(homepage.final_url).hostname or ""
        domain_root = domain_root.replace("www.", "").split(".")[0].capitalize()
        return domain_root, homepage, f"Derived from domain name: {domain_root}", "domain_fallback", 0.50

    def _extract_company_description(
        self,
        homepage: CrawledPage,
        pages: List[CrawledPage]
    ) -> Tuple[Optional[str], Optional[CrawledPage], Optional[str], str, float]:
        # 1. From JSON-LD
        for p in pages:
            for sdata in (p.structured_data or []):
                if sdata.get("@type") in ("Organization", "Corporation", "WebSite"):
                    desc = sdata.get("description")
                    if desc and isinstance(desc, str) and len(desc.strip()) > 20:
                        return desc.strip(), p, f"JSON-LD description: {desc[:200]}...", "json_ld_schema", 0.95

        # 2. From homepage meta_description (only if true homepage or not support/customer service)
        if homepage.meta_description and len(homepage.meta_description.strip()) > 20:
            h_desc_lower = homepage.meta_description.lower()
            if not any(g in h_desc_lower for g in ("customer service", "help center", "get help")) and homepage.page_type not in ("faq", "contact"):
                return homepage.meta_description.strip(), homepage, f"Meta description: {homepage.meta_description[:200]}...", "meta_description", 0.90

        # 3. From About page
        about_page = next((p for p in pages if p.page_type == "about"), None)
        if about_page and about_page.extracted_text:
            first_para = about_page.extracted_text.split("\n\n")[0].strip()
            if len(first_para) > 30:
                return first_para, about_page, f"About page excerpt: {first_para[:200]}...", "content_heuristic", 0.80

        # 4. From Homepage first paragraph
        if homepage.page_type == "homepage" and homepage.extracted_text:
            paras = [p.strip() for p in homepage.extracted_text.split("\n\n") if len(p.strip()) > 40]
            if paras:
                return paras[0], homepage, f"Homepage hero text: {paras[0][:200]}...", "content_heuristic", 0.70

        # 5. From brand landing/regional storefront pages (excluding blogs, stories, case studies, help articles, and single product stories)
        NON_COMPANY_DESC_URL_KEYWORDS = (
            "/stories/", "/journal/", "/blog/", "/news/", "/case-studies/", "/case-study/",
            "/articles/", "/glossary/", "/careers/", "/author/", "/help/", "/support/", "/tags/", "/post/"
        )
        NON_COMPANY_DESC_PREFIXES = (
            "field test:", "behind the design:", "the lab ", "learn how ", "explore the ",
            "meet the ", "experience our next ", "article not found", "most orders ",
            "eligible students ", "if your feet ", "whatever the reason"
        )

        candidate_landing_descriptions: List[Tuple[int, str, CrawledPage]] = []
        for p in pages:
            if p.page_type in ("faq", "contact", "blog", "docs"):
                continue
            p_url_lower = (p.final_url or "").lower()
            if any(k in p_url_lower for k in NON_COMPANY_DESC_URL_KEYWORDS):
                continue
            if not p.meta_description or len(p.meta_description.strip()) <= 25:
                continue
            p_desc = p.meta_description.strip()
            p_desc_lower = p_desc.lower()
            if any(g in p_desc_lower for g in ("customer service", "help center", "get help", "article not found")):
                continue
            if any(p_desc_lower.startswith(pfx) for pfx in NON_COMPANY_DESC_PREFIXES):
                continue
            # Must not be a single garment or model action story
            if " goes on a journey" in p_desc_lower or "came to be" in p_desc_lower or "for overpronation" in p_desc_lower:
                continue

            score = 1
            if any(v in p_desc_lower for v in ("delivers", "provides", "platform for", "leading", "helps businesses", "is an", "is the")):
                score += 2
            parsed_path = urlparse(p.final_url).path.strip("/")
            if not parsed_path or len(parsed_path.split("/")) <= 2:
                score += 1
            candidate_landing_descriptions.append((score, p_desc, p))

        if candidate_landing_descriptions:
            candidate_landing_descriptions.sort(key=lambda x: x[0], reverse=True)
            best_score, best_desc, best_page = candidate_landing_descriptions[0]
            return best_desc, best_page, f"Landing page description: {best_desc[:200]}...", "meta_description", 0.75

        return None, None, None, "none", 0.0

    def _extract_structured_data_facts(self, pages: List[CrawledPage], facts: List[BrandFact]) -> None:
        for p in pages:
            for sdata in (p.structured_data or []):
                stype = sdata.get("@type")
                if not stype:
                    continue

                # Products / Services / ProductGroups
                if stype in ("Product", "ProductGroup", "IndividualProduct", "ProductModel", "SomeProducts", "Service", "SoftwareApplication"):
                    pname = sdata.get("name")
                    if pname and isinstance(pname, str):
                        clean_pname = pname.strip()
                        existing_sd_names = {
                            f.fact_value.get("name", "").lower()
                            for f in facts
                            if f.fact_type == "product_service" and isinstance(f.fact_value, dict)
                        }
                        if clean_pname.lower() not in existing_sd_names:
                            pdesc = sdata.get("description", "")
                            facts.append(BrandFact(
                                brand_id=self.brand_id,
                                profile_version=self.profile_version,
                                fact_type="product_service",
                                fact_value={"name": clean_pname, "description": str(pdesc).strip(), "type": stype},
                                source_page_id=p.id,
                                source_url=p.final_url,
                                evidence_snippet=f"JSON-LD {stype}: {clean_pname} — {str(pdesc)[:150]}",
                                extraction_method="json_ld_schema",
                                confidence=0.95,
                                user_confirmed=False
                            ))

                    # Extract target audience if declared in structured data
                    aud = sdata.get("audience")
                    if aud:
                        aud_str = None
                        if isinstance(aud, dict):
                            gender = str(aud.get("suggestedGender", "")).split("/")[-1]
                            min_age = str(aud.get("suggestedMinAge", ""))
                            aud_type = str(aud.get("audienceType", ""))
                            parts = [pt for pt in (aud_type, gender, f"age {min_age}+" if min_age else "") if pt]
                            if parts:
                                aud_str = ", ".join(parts)
                        elif isinstance(aud, str):
                            aud_str = aud.strip()
                        if aud_str:
                            facts.append(BrandFact(
                                brand_id=self.brand_id,
                                profile_version=self.profile_version,
                                fact_type="target_audience",
                                fact_value=aud_str,
                                source_page_id=p.id,
                                source_url=p.final_url,
                                evidence_snippet=f"Structured Data audience: {aud_str}",
                                extraction_method="json_ld_audience",
                                confidence=0.90,
                                user_confirmed=False
                            ))

                # FAQPage
                elif stype == "FAQPage":
                    main_entity = sdata.get("mainEntity", [])
                    if isinstance(main_entity, list):
                        for item in main_entity:
                            q = item.get("name") or item.get("question")
                            ans_obj = item.get("acceptedAnswer", {})
                            a = ans_obj.get("text") if isinstance(ans_obj, dict) else str(ans_obj)
                            if q and a:
                                facts.append(BrandFact(
                                    brand_id=self.brand_id,
                                    profile_version=self.profile_version,
                                    fact_type="faq",
                                    fact_value={"question": str(q).strip(), "answer": str(a).strip()},
                                    source_page_id=p.id,
                                    source_url=p.final_url,
                                    evidence_snippet=f"FAQ Schema: Q: {q} | A: {a[:150]}",
                                    extraction_method="json_ld_faq",
                                    confidence=0.95,
                                    user_confirmed=False
                                ))

    def _extract_products_and_features(self, pages: List[CrawledPage], facts: List[BrandFact], brand_name: str = "") -> None:
        effective_brand = brand_name or self.user_business_name or ""
        seen_products = {f.fact_value.get("name").lower() for f in facts if f.fact_type == "product_service" and isinstance(f.fact_value, dict)}

        for p in pages:
            # Strictly NEVER extract products from legal, docs, blog, contact, or other pages
            if p.page_type in ("legal", "blog", "docs", "faq", "contact", "other"):
                continue
            if any(term in (p.final_url or "").lower() for term in ("/terms", "/legal", "/privacy", "/license", "/agreement", "/blog", "/changelog")):
                continue

            # Check dedicated product/service pages and homepage H1s (excluding slogans)
            if p.page_type in ("product_service", "homepage"):
                headings = p.headings or {}
                h1_list = headings.get("h1", [])
                h2_list = headings.get("h2", []) if p.page_type == "product_service" else []

                page_has_product = False
                for heading in h1_list + h2_list:
                    h_clean = re.sub(r"[\u200b\u200c\u200d\ufeff\xa0]", " ", heading).strip()
                    h_clean = re.sub(r"\s+", " ", h_clean).strip()
                    h_lower = h_clean.lower()
                    if not is_valid_product_candidate(h_clean, effective_brand):
                        continue
                    if any(bad in h_lower for bad in ("privacy policy", "terms of", "cookie", "get help", "customer service", "agreement", "recital")):
                        continue
                    if 3 <= len(h_clean) <= 55 and h_lower not in seen_products:
                        seen_products.add(h_lower)
                        page_has_product = True
                        facts.append(BrandFact(
                            brand_id=self.brand_id,
                            profile_version=self.profile_version,
                            fact_type="product_service",
                            fact_value={"name": h_clean, "page_title": p.title, "url": p.final_url, "type": "product_service"},
                            source_page_id=p.id,
                            source_url=p.final_url,
                            evidence_snippet=h_clean,
                            supporting_evidence=[{
                                "source_url": p.final_url,
                                "snippet": h_clean,
                                "source_type": "heading_heuristic",
                                "provenance_type": "verbatim_text",
                                "heuristic_confidence": 0.85 if p.page_type == "product_service" else 0.75
                            }],
                            extraction_method="heading_heuristic",
                            confidence=0.85 if p.page_type == "product_service" else 0.75,
                            user_confirmed=False
                        ))

                # If no heading yielded a product on a product_service page, use the page title
                if p.page_type == "product_service" and not page_has_product and p.title:
                    cand = p.title.split("—")[0].split("|")[0].split(" - ")[0].strip()
                    cand = re.sub(r"[\u200b\u200c\u200d\ufeff\xa0]", " ", cand).strip()
                    cand = re.sub(r"\s+", " ", cand).strip()
                    cand_lower = cand.lower()
                    if is_valid_product_candidate(cand, effective_brand) and cand_lower not in seen_products:
                        seen_products.add(cand_lower)
                        facts.append(BrandFact(
                            brand_id=self.brand_id,
                            profile_version=self.profile_version,
                            fact_type="product_service",
                            fact_value={"name": cand, "page_title": p.title, "url": p.final_url, "type": "product_service"},
                            source_page_id=p.id,
                            source_url=p.final_url,
                            evidence_snippet=cand,
                            supporting_evidence=[{
                                "source_url": p.final_url,
                                "snippet": p.title or cand,
                                "source_type": "title_heuristic",
                                "provenance_type": "verbatim_text",
                                "heuristic_confidence": 0.80
                            }],
                            extraction_method="title_heuristic",
                            confidence=0.80,
                            user_confirmed=False
                        ))

            # Extract features from bullet points under Feature headings
            lines = (p.extracted_text or "").splitlines()
            in_features_block = False
            for line in lines:
                l_str = line.strip()
                if any(k in l_str.lower() for k in ("key features", "core capabilities", "features:", "what's included")):
                    in_features_block = True
                    continue
                if in_features_block:
                    if l_str.startswith(("-", "•", "*")):
                        feat = l_str.lstrip("-•* ").strip()
                        if 10 <= len(feat) <= 150:
                            facts.append(BrandFact(
                                brand_id=self.brand_id,
                                profile_version=self.profile_version,
                                fact_type="product_feature",
                                fact_value=feat,
                                source_page_id=p.id,
                                source_url=p.final_url,
                                evidence_snippet=feat,
                                supporting_evidence=[{
                                    "source_url": p.final_url,
                                    "snippet": feat,
                                    "source_type": "bullet_heuristic",
                                    "provenance_type": "verbatim_text",
                                    "heuristic_confidence": 0.75
                                }],
                                extraction_method="bullet_heuristic",
                                confidence=0.75,
                                user_confirmed=False
                            ))
                    elif len(l_str) > 0 and not l_str.startswith(("-", "•", "*")):
                        # End of list
                        in_features_block = False

    def _extract_audience_and_use_cases(self, pages: List[CrawledPage], facts: List[BrandFact]) -> None:
        seen_audience = set()
        seen_use_cases = set()
        seen_diffs = set()

        for f in facts:
            if f.fact_type == "target_audience" and isinstance(f.fact_value, str):
                seen_audience.add(f.fact_value.strip().lower())
            elif f.fact_type == "use_case" and isinstance(f.fact_value, str):
                seen_use_cases.add(f.fact_value.strip().lower())
            elif f.fact_type == "differentiator" and isinstance(f.fact_value, str):
                seen_diffs.add(f.fact_value.strip().lower())

        target_line_prefixes = [
            (re.compile(r"^(?:built|designed|made)\s+for\s*[:\-–—]?\s*(.+)$", re.I), "target_audience"),
            (re.compile(r"^(?:who\s+it'?s\s+for|who\s+uses\s+us|target\s+audience)\s*[:\-–—]?\s*(.+)$", re.I), "target_audience"),
            (re.compile(r"^(?:solutions?\s+for|use\s+cases?|solutions?)\s*[:\-–—]?\s*(.+)$", re.I), "use_case"),
            (re.compile(r"^(?:why\s+choose\s+us|our\s+advantage|differentiator)\s*[:\-–—]?\s*(.+)$", re.I), "differentiator"),
        ]

        for p in pages:
            # Only extract audience/use-cases from core brand narrative pages
            if p.page_type not in ("homepage", "about", "product_service"):
                continue
            if any(term in (p.final_url or "").lower() for term in ("/terms", "/legal", "/privacy", "/license", "/agreement", "/blog", "/changelog", "/docs", "/api")):
                continue

            lines = (p.extracted_text or "").splitlines()
            in_section_type = None

            for line in lines:
                l_str = line.strip()
                if not l_str:
                    continue
                l_lower = l_str.lower()

                # Check markdown section headings
                if re.match(r"^#{1,4}\s*(?:use\s+cases?|solutions?|key\s+applications?)\b", l_lower) or l_lower.rstrip(":") in ("use cases", "solutions", "applications", "key use cases"):
                    in_section_type = "use_case"
                    continue
                elif re.match(r"^#{1,4}\s*(?:target\s+audience|who\s+it'?s\s+for|built\s+for)\b", l_lower) or l_lower.rstrip(":") in ("target audience", "who it's for", "built for"):
                    in_section_type = "target_audience"
                    continue
                elif re.match(r"^#{1,4}\s*(?:why\s+choose\s+us|differentiators?|our\s+advantage)\b", l_lower):
                    in_section_type = "differentiator"
                    continue
                elif re.match(r"^#{1,4}\s+", l_str):
                    in_section_type = None

                # Process list items under active heading
                if in_section_type and l_str.startswith(("-", "•", "*")):
                    cand = l_str.lstrip("-•* ").strip()
                    cand_lower = cand.lower()

                    if in_section_type == "use_case" and is_valid_use_case(cand):
                        if cand_lower not in seen_use_cases:
                            seen_use_cases.add(cand_lower)
                            facts.append(BrandFact(
                                brand_id=self.brand_id,
                                profile_version=self.profile_version,
                                fact_type="use_case",
                                fact_value=cand,
                                source_page_id=p.id,
                                source_url=p.final_url,
                                evidence_snippet=cand,
                                supporting_evidence=[{
                                    "source_url": p.final_url,
                                    "snippet": l_str,
                                    "source_type": "heading_list_item",
                                    "provenance_type": "verbatim_text",
                                    "heuristic_confidence": 0.85
                                }],
                                extraction_method="heading_list_item",
                                confidence=0.85,
                                user_confirmed=False
                            ))
                    elif in_section_type == "target_audience" and is_valid_target_audience(cand):
                        if cand_lower not in seen_audience:
                            seen_audience.add(cand_lower)
                            facts.append(BrandFact(
                                brand_id=self.brand_id,
                                profile_version=self.profile_version,
                                fact_type="target_audience",
                                fact_value=cand,
                                source_page_id=p.id,
                                source_url=p.final_url,
                                evidence_snippet=cand,
                                supporting_evidence=[{
                                    "source_url": p.final_url,
                                    "snippet": l_str,
                                    "source_type": "heading_list_item",
                                    "provenance_type": "verbatim_text",
                                    "heuristic_confidence": 0.85
                                }],
                                extraction_method="heading_list_item",
                                confidence=0.85,
                                user_confirmed=False
                            ))
                    elif in_section_type == "differentiator" and len(cand) >= 8 and len(cand) <= 120:
                        if cand_lower not in seen_diffs:
                            seen_diffs.add(cand_lower)
                            facts.append(BrandFact(
                                brand_id=self.brand_id,
                                profile_version=self.profile_version,
                                fact_type="differentiator",
                                fact_value=cand,
                                source_page_id=p.id,
                                source_url=p.final_url,
                                evidence_snippet=cand,
                                supporting_evidence=[{
                                    "source_url": p.final_url,
                                    "snippet": l_str,
                                    "source_type": "heading_list_item",
                                    "provenance_type": "verbatim_text",
                                    "heuristic_confidence": 0.80
                                }],
                                extraction_method="heading_list_item",
                                confidence=0.80,
                                user_confirmed=False
                            ))
                    continue

                # Process labeled inline lines (e.g. "Use Cases: ...", "Built for: ...")
                for prefix_re, ftype in target_line_prefixes:
                    m = prefix_re.match(l_str)
                    if m:
                        raw_cand = m.group(1).strip()
                        cand = raw_cand.strip(" \t\r\n,;:-–—\"'“”()[]")
                        cand_lower = cand.lower()

                        if ftype == "use_case" and is_valid_use_case(cand):
                            if cand_lower not in seen_use_cases:
                                seen_use_cases.add(cand_lower)
                                facts.append(BrandFact(
                                    brand_id=self.brand_id,
                                    profile_version=self.profile_version,
                                    fact_type="use_case",
                                    fact_value=cand,
                                    source_page_id=p.id,
                                    source_url=p.final_url,
                                    evidence_snippet=l_str[:180],
                                    extraction_method="labeled_line",
                                    confidence=0.80,
                                    user_confirmed=False
                                ))
                        elif ftype == "target_audience" and is_valid_target_audience(cand):
                            if cand_lower not in seen_audience:
                                seen_audience.add(cand_lower)
                                facts.append(BrandFact(
                                    brand_id=self.brand_id,
                                    profile_version=self.profile_version,
                                    fact_type="target_audience",
                                    fact_value=cand,
                                    source_page_id=p.id,
                                    source_url=p.final_url,
                                    evidence_snippet=l_str[:180],
                                    extraction_method="labeled_line",
                                    confidence=0.80,
                                    user_confirmed=False
                                ))
                        elif ftype == "differentiator" and len(cand) >= 8 and len(cand) <= 120:
                            if cand_lower not in seen_diffs:
                                seen_diffs.add(cand_lower)
                                facts.append(BrandFact(
                                    brand_id=self.brand_id,
                                    profile_version=self.profile_version,
                                    fact_type="differentiator",
                                    fact_value=cand,
                                    source_page_id=p.id,
                                    source_url=p.final_url,
                                    evidence_snippet=l_str[:180],
                                    extraction_method="labeled_line",
                                    confidence=0.75,
                                    user_confirmed=False
                                ))
                        break

            if p.meta_description:
                meta_clean = p.meta_description.strip()
                use_intent_patterns = [
                    re.compile(r"\b(?:use|uses|using)\s+[A-Za-z0-9_\- ]+?\s+to\s+([^.!?—–;]+)", re.I),
                    re.compile(r"\b(?:built|designed|developed|created)\s+to\s+([^.!?—–;]+)", re.I),
                    re.compile(r"\b(?:helps?|allowing|enabling|allows|enables)\s+(?:users|teams|businesses|people|you|customers)?\s*to\s+([^.!?—–;]+)", re.I),
                ]
                for u_pat in use_intent_patterns:
                    m = u_pat.search(meta_clean)
                    if m:
                        clause = m.group(1).strip()
                        candidates = [c.strip() for c in re.split(r",|\band\b|;", clause) if c.strip()]
                        if is_valid_use_case(clause) and clause.lower() not in seen_use_cases:
                            seen_use_cases.add(clause.lower())
                            facts.append(BrandFact(
                                brand_id=self.brand_id,
                                profile_version=self.profile_version,
                                fact_type="use_case",
                                fact_value=clause,
                                source_page_id=p.id,
                                source_url=p.final_url,
                                evidence_snippet=meta_clean[:200],
                                supporting_evidence=[{
                                    "source_url": p.final_url,
                                    "snippet": meta_clean[:200],
                                    "source_type": "meta_description",
                                    "provenance_type": "meta_description",
                                    "heuristic_confidence": 0.85
                                }],
                                extraction_method="meta_description",
                                confidence=0.85,
                                user_confirmed=False
                            ))
                        for cand in candidates:
                            cand_clean = cand.strip(" \t\r\n,;:-–—\"'“”()[]")
                            cand_lower = cand_clean.lower()
                            if is_valid_use_case(cand_clean) and cand_lower not in seen_use_cases:
                                seen_use_cases.add(cand_lower)
                                facts.append(BrandFact(
                                    brand_id=self.brand_id,
                                    profile_version=self.profile_version,
                                    fact_type="use_case",
                                    fact_value=cand_clean,
                                    source_page_id=p.id,
                                    source_url=p.final_url,
                                    evidence_snippet=meta_clean[:200],
                                    supporting_evidence=[{
                                        "source_url": p.final_url,
                                        "snippet": meta_clean[:200],
                                        "source_type": "meta_description",
                                        "provenance_type": "meta_description",
                                        "heuristic_confidence": 0.85
                                    }],
                                    extraction_method="meta_description",
                                    confidence=0.85,
                                    user_confirmed=False
                                ))

                aud_intent_patterns = [
                    re.compile(r"\b(?:built|designed|made)\s+for\s+([^.!?—–;]+)", re.I),
                    re.compile(r"\b(?:empowers?|helps?)\s+([A-Za-z0-9_\- ]+?)\s+to\b", re.I),
                ]
                for a_pat in aud_intent_patterns:
                    m = a_pat.search(meta_clean)
                    if m:
                        clause = m.group(1).strip()
                        candidates = [c.strip() for c in re.split(r",|\band\b|;", clause) if c.strip()]
                        for cand in candidates:
                            cand_clean = cand.strip(" \t\r\n,;:-–—\"'“”()[]")
                            cand_lower = cand_clean.lower()
                            if is_valid_target_audience(cand_clean) and cand_lower not in seen_audience:
                                seen_audience.add(cand_lower)
                                facts.append(BrandFact(
                                    brand_id=self.brand_id,
                                    profile_version=self.profile_version,
                                    fact_type="target_audience",
                                    fact_value=cand_clean,
                                    source_page_id=p.id,
                                    source_url=p.final_url,
                                    evidence_snippet=meta_clean[:200],
                                    supporting_evidence=[{
                                        "source_url": p.final_url,
                                        "snippet": meta_clean[:200],
                                        "source_type": "meta_description",
                                        "provenance_type": "meta_description",
                                        "heuristic_confidence": 0.85
                                    }],
                                    extraction_method="meta_description",
                                    confidence=0.85,
                                    user_confirmed=False
                                ))

    def _extract_educational_and_buying_guide_topics(self, pages: List[CrawledPage], facts: List[BrandFact], brand_name: str = "") -> None:
        """
        Extracts educational content, buying guides, and comparison topics from blog,
        article, guide, and product narrative pages. These represent real customer buying
        intents and questions grounded in the website's published content.
        """
        seen_topics = {
            f.fact_value.lower() if isinstance(f.fact_value, str) else str(f.fact_value.get("title", "")).lower()
            for f in facts if f.fact_type == "use_case"
        }
        effective_brand = (brand_name or self.user_business_name or "").lower()

        guide_patterns = [
            re.compile(r"^(?:how\s+to\s+(?:choose|pick|select|find|buy))\s+(.+)$", re.I),
            re.compile(r"^(?:choosing|picking|finding)\s+the\s+(?:right|best)\s+(.+)$", re.I),
            re.compile(r"^(.+?)\s+(?:vs\.?|versus)\s+(.+)$", re.I),
            re.compile(r"^(?:best|top)\s+(.+?)\s+(?:for|in|this|to)\s+(.+)$", re.I),
            re.compile(r"^(?:what\s+to\s+look\s+for\s+in|buyer'?s\s+guide\s+to|guide\s+to)\s+(.+)$", re.I),
            re.compile(r"^(?:differences?\s+between)\s+(.+)$", re.I),
        ]

        for p in pages:
            url_lower = (p.final_url or "").lower()
            is_content_page = (
                p.page_type in ("blog", "article", "docs", "faq", "homepage", "product_service")
                or any(term in url_lower for term in ("/blog", "/article", "/guide", "/stories", "/journal", "/news", "/buying-guide", "/learn"))
            )
            if not is_content_page:
                continue
            if any(term in url_lower for term in ("/terms", "/legal", "/privacy", "/license", "/agreement", "/cookie")):
                continue

            candidates = []
            if p.title:
                clean_title = p.title.split("—")[0].split("|")[0].split(" - ")[0].strip()
                candidates.append((clean_title, "article_title"))

            headings = p.headings or {}
            for h in headings.get("h1", []) + headings.get("h2", []):
                candidates.append((h.strip(), "heading"))

            for raw_cand, src_type in candidates:
                cand = re.sub(r"[\u200b\u200c\u200d\ufeff\xa0]", " ", raw_cand).strip()
                cand = re.sub(r"\s+", " ", cand).strip()
                cand_lower = cand.lower()

                if not (12 <= len(cand) <= 90):
                    continue
                if any(bad in cand_lower for bad in ("privacy policy", "terms of", "cookie", "all rights reserved", "subscribe", "newsletter", "sign in", "cart", "checkout")):
                    continue

                if effective_brand and cand_lower.startswith(effective_brand):
                    cand = cand[len(effective_brand):].lstrip(" :-–—|").strip()
                    cand_lower = cand.lower()

                is_guide = any(pat.search(cand) for pat in guide_patterns)
                is_blog_page_title = (src_type == "article_title" and any(term in url_lower for term in ("/blog", "/guide", "/article", "/stories")))

                if (is_guide or is_blog_page_title) and cand_lower not in seen_topics:
                    seen_topics.add(cand_lower)
                    facts.append(BrandFact(
                        brand_id=self.brand_id,
                        profile_version=self.profile_version,
                        fact_type="use_case",
                        fact_value=cand,
                        source_page_id=p.id,
                        source_url=p.final_url,
                        evidence_snippet=cand,
                        supporting_evidence=[{
                            "source_url": p.final_url,
                            "snippet": cand,
                            "source_type": "article_topic",
                            "provenance_type": "verbatim_text",
                            "heuristic_confidence": 0.85
                        }],
                        extraction_method="article_topic_heuristic",
                        confidence=0.85,
                        user_confirmed=False
                    ))

    def _extract_pricing_facts(self, pages: List[CrawledPage], facts: List[BrandFact]) -> None:
        pricing_pages = [p for p in pages if p.page_type == "pricing"]

        # 1. JSON-LD Offers (extract from pricing pages, or pages with explicit Product/Offer schemas)
        for p in (pricing_pages if pricing_pages else [p for p in pages if p.page_type in ("homepage", "product_service")]):
            for sdata in (p.structured_data or []):
                offers = sdata.get("offers")
                if offers:
                    offers_list = offers if isinstance(offers, list) else [offers]
                    for off in offers_list:
                        price = off.get("price")
                        currency = off.get("priceCurrency", "USD")
                        if price is not None:
                            try:
                                num_p = float(str(price).replace(",", "").replace("$", ""))
                            except ValueError:
                                continue
                            plan_title = off.get("name") or sdata.get("name") or "Standard Plan"
                            display_text = f"{plan_title}: {currency} {price}"
                            facts.append(BrandFact(
                                brand_id=self.brand_id,
                                profile_version=self.profile_version,
                                fact_type="pricing",
                                fact_value={
                                    "pricing_type": "subscription_plan" if any(k in plan_title.lower() for k in ("plan", "tier", "subscription", "pro", "enterprise", "starter", "team", "free")) else "offer",
                                    "plan_name": plan_title,
                                    "amount": num_p,
                                    "currency": currency,
                                    "currency_symbol": "$" if currency == "USD" else ("€" if currency == "EUR" else ("£" if currency == "GBP" else currency)),
                                    "unit": "month" if "month" in str(off).lower() else "unit",
                                    "billing_basis": "monthly" if "month" in str(off).lower() else "per_unit",
                                    "associated_product": sdata.get("name") or plan_title,
                                    "formatted_display": display_text,
                                    "price": str(num_p),
                                    "price_text": display_text,
                                    "model": display_text,
                                    "name": plan_title
                                },
                                source_page_id=p.id,
                                source_url=p.final_url,
                                evidence_snippet=f"JSON-LD Offer: {currency} {price}",
                                extraction_method="json_ld_offer",
                                confidence=0.95,
                                user_confirmed=False
                            ))
                elif "hasVariant" in sdata and isinstance(sdata["hasVariant"], list):
                    for var in sdata["hasVariant"]:
                        if isinstance(var, dict) and "offers" in var:
                            var_offers = var["offers"] if isinstance(var["offers"], list) else [var["offers"]]
                            for off in var_offers:
                                if isinstance(off, dict) and off.get("price") is not None:
                                    try:
                                        num_p = float(str(off["price"]).replace(",", "").replace("$", ""))
                                    except ValueError:
                                        continue
                                    curr = off.get("priceCurrency", "USD")
                                    plan_title = var.get("name") or sdata.get("name") or "Variant Offer"
                                    display_text = f"{plan_title}: {curr} {num_p}"
                                    facts.append(BrandFact(
                                        brand_id=self.brand_id,
                                        profile_version=self.profile_version,
                                        fact_type="pricing",
                                        fact_value={
                                            "pricing_type": "offer",
                                            "plan_name": plan_title,
                                            "amount": num_p,
                                            "currency": curr,
                                            "currency_symbol": "$" if curr == "USD" else ("€" if curr == "EUR" else ("£" if curr == "GBP" else curr)),
                                            "unit": "unit",
                                            "billing_basis": "one_time",
                                            "associated_product": sdata.get("name") or plan_title,
                                            "formatted_display": display_text,
                                            "price": str(off.get("price", num_p)),
                                            "price_text": display_text,
                                            "model": display_text,
                                            "name": plan_title
                                        },
                                        source_page_id=p.id,
                                        source_url=p.final_url,
                                        evidence_snippet=f"JSON-LD Variant Offer: {curr} {num_p}",
                                        extraction_method="json_ld_offer",
                                        confidence=0.95,
                                        user_confirmed=False
                                    ))
                                    break

        # 2. Text-based plan and pricing extraction
        # Only dedicated pricing pages or pages with explicit plan/pricing tables
        candidate_text_pages = pricing_pages if pricing_pages else pages

        seen_plans = set()
        for p in candidate_text_pages:
            text = p.extracted_text or ""
            if p.page_type in ("legal", "terms", "docs"):
                continue

            # Dedicated Tier detection on pricing pages
            if p.page_type == "pricing":
                free_match = re.search(r"\bFree\b[\s\S]{1,80}?(?:Get started for free|No fees|\$0(?:\s*/\s*(?:mo|month))?|free forever|always free|25\+\s*free models|no credit card)", text, re.I)
                if free_match:
                    free_key = ("free", 0.0, "free", "free", "free_tier")
                    if free_key not in seen_plans:
                        seen_plans.add(free_key)
                        facts.append(BrandFact(
                            brand_id=self.brand_id,
                            profile_version=self.profile_version,
                            fact_type="pricing",
                            fact_value={
                                "pricing_type": "free_tier",
                                "plan_name": "Free",
                                "amount": 0.0,
                                "currency": "USD",
                                "currency_symbol": "$",
                                "unit": "free",
                                "billing_basis": "free",
                                "associated_product": "Free Tier",
                                "formatted_display": "Free: $0 (free tier)",
                                "price": "0.0",
                                "price_text": "$0",
                                "model": "Free: $0 (free tier)",
                                "name": "Free",
                                "context": free_match.group(0).replace("\n", " ").strip()
                            },
                            source_page_id=p.id,
                            source_url=p.final_url,
                            evidence_snippet=free_match.group(0).replace("\n", " ").strip(),
                            extraction_method="pricing_regex",
                            confidence=0.90,
                            user_confirmed=False
                        ))

                # Platform fees / pay-as-you-go on dedicated pricing pages
                fee_matches = re.finditer(r"\b(Standard|Business|Team|Pro|Growth)\b[\s\n:\-–—]{1,25}?(\d+(?:\.\d+)?%)", text, re.I)
                for fm in fee_matches:
                    tier = fm.group(1).capitalize()
                    pct_str = fm.group(2)
                    pct_val = float(pct_str.replace("%", ""))
                    payg_key = (tier.lower(), pct_val, "pay_as_you_go", "% fee", "pay_as_you_go")
                    if payg_key not in seen_plans:
                        seen_plans.add(payg_key)
                        formatted_display = f"{tier}: Pay-as-you-go ({pct_str} fee)"
                        facts.append(BrandFact(
                            brand_id=self.brand_id,
                            profile_version=self.profile_version,
                            fact_type="pricing",
                            fact_value={
                                "pricing_type": "pay_as_you_go",
                                "plan_name": tier,
                                "amount": pct_val,
                                "currency": "USD",
                                "currency_symbol": "%",
                                "unit": "% fee",
                                "billing_basis": "pay_as_you_go",
                                "associated_product": tier,
                                "formatted_display": formatted_display,
                                "price": pct_str,
                                "price_text": pct_str,
                                "model": formatted_display,
                                "name": tier,
                                "context": fm.group(0).replace("\n", " ").strip()
                            },
                            source_page_id=p.id,
                            source_url=p.final_url,
                            evidence_snippet=fm.group(0).replace("\n", " ").strip(),
                            extraction_method="pricing_regex",
                            confidence=0.85,
                            user_confirmed=False
                        ))

                # Non-currency Credits and Requests Allowance detection on dedicated pricing pages
                quota_matches = re.finditer(r"\b(Free|Starter|Basic|Standard|Pro|Team|Business|Developer|Personal|Scale)\b[\s\n:\-–—]{1,25}?(\d+(?:,\d{3})*|\d+)\s*(credits?|requests?|queries|tokens?|api\s*calls?)\s*(?:/\s*(?:month|mo)|per\s+month)?\b", text, re.I)
                for qm in quota_matches:
                    tier = qm.group(1).capitalize()
                    q_str = qm.group(2)
                    q_unit = qm.group(3).lower()
                    try:
                        q_val = float(q_str.replace(",", ""))
                    except ValueError:
                        continue
                    is_mo = "month" in qm.group(0).lower() or "mo" in qm.group(0).lower()
                    unit_label = f"{q_unit}/month" if is_mo else q_unit
                    quota_key = (tier.lower(), q_val, "monthly" if is_mo else "unspecified", unit_label, "usage_allowance")
                    if quota_key not in seen_plans:
                        seen_plans.add(quota_key)
                        formatted_display = f"{tier}: {q_val:,.0f} {unit_label}"
                        facts.append(BrandFact(
                            brand_id=self.brand_id,
                            profile_version=self.profile_version,
                            fact_type="pricing",
                            fact_value={
                                "pricing_type": "usage_allowance",
                                "plan_name": tier,
                                "amount": q_val,
                                "currency": None,
                                "currency_symbol": None,
                                "unit": unit_label,
                                "billing_basis": "monthly" if is_mo else "unspecified",
                                "associated_product": tier,
                                "formatted_display": formatted_display,
                                "price": str(q_val),
                                "price_text": f"{q_str} {q_unit}",
                                "model": formatted_display,
                                "name": tier,
                                "context": qm.group(0).replace("\n", " ").strip()
                            },
                            source_page_id=p.id,
                            source_url=p.final_url,
                            evidence_snippet=qm.group(0).replace("\n", " ").strip(),
                            extraction_method="pricing_regex",
                            confidence=0.85,
                            user_confirmed=False
                        ))

                # Custom / Contact Sales tier detection on dedicated pricing pages
                custom_matches = re.finditer(r"\b(Enterprise|Custom|Business|Premium|Scale|Core)\b[\s\n:\-–—]{1,30}?(Contact\s+sales|Contact\s+us|Custom\s+pricing|Custom\s+quote|Talk\s+to\s+sales|Custom)\b", text, re.I)
                for cm in custom_matches:
                    tier = cm.group(1).capitalize()
                    custom_key = (tier.lower(), 0.0, "custom", "custom", "custom")
                    if custom_key not in seen_plans:
                        seen_plans.add(custom_key)
                        formatted_display = f"{tier}: Custom / Contact Sales"
                        facts.append(BrandFact(
                            brand_id=self.brand_id,
                            profile_version=self.profile_version,
                            fact_type="pricing",
                            fact_value={
                                "pricing_type": "custom",
                                "plan_name": tier,
                                "amount": None,
                                "currency": None,
                                "currency_symbol": None,
                                "unit": "custom",
                                "billing_basis": "custom",
                                "associated_product": tier,
                                "formatted_display": formatted_display,
                                "price": "Custom",
                                "price_text": cm.group(2).strip(),
                                "model": formatted_display,
                                "name": tier,
                                "context": cm.group(0).replace("\n", " ").strip()
                            },
                            source_page_id=p.id,
                            source_url=p.final_url,
                            evidence_snippet=cm.group(0).replace("\n", " ").strip(),
                            extraction_method="pricing_regex",
                            confidence=0.85,
                            user_confirmed=False
                        ))

            price_matches = PRICE_CURRENCY_REGEX.finditer(text)
            for pm in price_matches:
                p_text = pm.group(0).strip()
                curr_sym = pm.group(1)
                num_str = pm.group(2)

                try:
                    num_val = float(num_str.replace(",", ""))
                except ValueError:
                    continue

                # Reject scale multipliers (million, billion) or funding announcements
                after_line_end = text.find("\n", pm.end())
                after_match_limit = pm.end() + 35 if after_line_end == -1 else min(pm.end() + 35, after_line_end)
                after_match = text[pm.end():after_match_limit].lower()
                if re.match(r"^\s*(?:\.\d+)?\s*(?:million|billion|trillion|m\b|b\b|k\b|arr\b|series\b|valuation\b|funding\b|revenue\b|round\b|raised\b|prize|prizes|fine|fines|penalty|auction|saved|savings|seed)", after_match):
                    continue

                # Line-bounded snippet to prevent cross-plan feature/unit leakage
                line_start = text.rfind("\n", 0, pm.start())
                snippet_start = max(0, pm.start() - 70) if line_start == -1 else max(line_start + 1, pm.start() - 70)
                line_end = text.find("\n", pm.end())
                snippet_end = min(len(text), pm.end() + 70) if line_end == -1 else min(line_end, pm.end() + 70)
                snippet = text[snippet_start:snippet_end].replace("\n", " ").strip()
                snippet_lower = snippet.lower()

                # Reject funding, fines, prize pools, incidental discounts
                if any(bad in snippet_lower for bad in (
                    "in prizes", "in prize", "prize pool", "seed round", "series a", "series b",
                    "series c", "raised $", "raised a $", "invest $", "invests $", "fines of",
                    "facing fines", "charity auction", "in fines", "costs by $", "save up to",
                    "saved $", "discount of"
                )):
                    continue

                # Detect Quotas, Allowances, or Spend Limits
                is_allowance = any(k in snippet_lower for k in ALLOWANCE_INDICATORS)

                # Identify recurring unit
                has_recurring_unit = bool(re.search(r"(?:/\s*(?:mo|month|yr|year|user|seat|member)|per\s+(?:month|year|user|seat|member)|billed\s+(?:annually|monthly))", snippet_lower))

                # Identify usage unit
                has_usage_unit = (bool(USAGE_UNIT_REGEX.search(after_match)) or bool(USAGE_UNIT_REGEX.search(snippet_lower))) and not has_recurring_unit

                has_package_term = any(
                    k in snippet_lower for k in ("package", "flat rate", "flat fee", "one-time", "starting rate", "costs $", "price:")
                )

                # Identify plan tier name
                plan_name = None
                before_snippet = text[max(0, pm.start() - 40):pm.start()]
                tier_matches_before = list(PRICING_TIER_REGEX.finditer(before_snippet))
                if tier_matches_before:
                    plan_name = tier_matches_before[-1].group(0).capitalize()
                else:
                    after_snippet = text[pm.end():min(len(text), pm.end() + 40)]
                    tier_m_after = PRICING_TIER_REGEX.search(after_snippet)
                    if tier_m_after:
                        plan_name = tier_m_after.group(0).capitalize()

                # If usage unit, look for labeled model/product row
                model_name = None
                if has_usage_unit:
                    model_match = re.search(r"\b([A-Za-z0-9\.\-]+(?:\s+[A-Za-z0-9\.\-]+){0,3})\s*[:\-–—]\s*" + re.escape(p_text), snippet)
                    if model_match:
                        cand_model = model_match.group(1).strip()
                        if 3 <= len(cand_model) <= 40 and not any(k in cand_model.lower() for k in ("price", "pricing", "cost", "from", "starting")):
                            model_name = cand_model
                    else:
                        prefix_match = re.search(r"\b([A-Z][a-zA-Z0-9\.\-]+:\s+[A-Z][a-zA-Z0-9\.\-]+(?:\s+[A-Za-z0-9\.\-]+){0,2})", snippet)
                        if prefix_match:
                            cand = prefix_match.group(1).strip()
                            if 3 <= len(cand) <= 40:
                                model_name = cand

                # STRICT VALIDATION: Reject context-free numbers
                if not plan_name and not model_name and not has_usage_unit and not has_recurring_unit and not has_package_term and p.page_type != "pricing":
                    continue

                # Determine semantics, billing basis and unit
                is_per_user = bool(re.search(r"(?:/\s*(?:user|seat|member)|per\s+(?:user|seat|member))", snippet_lower)) or bool(re.search(r"(?:/\s*(?:user|seat|member)|per\s+(?:user|seat|member))", p_text.lower()))
                is_annual = bool(re.search(r"(?:/\s*(?:yr|year)|per\s+year|annually|billed\s+annually)", snippet_lower)) or bool(re.search(r"(?:/\s*(?:yr|year)|per\s+year|annually|billed\s+annually)", p_text.lower()))
                is_monthly = bool(re.search(r"(?:/\s*(?:mo|month)|per\s+month|monthly|billed\s+monthly)", snippet_lower)) or bool(re.search(r"(?:/\s*(?:mo|month)|per\s+month|monthly|billed\s+monthly)", p_text.lower()))

                if is_allowance:
                    pricing_type = "usage_allowance"
                    billing_basis = "monthly" if "month" in snippet_lower else "unspecified"
                    unit_str = "inference allowance" if "inference" in snippet_lower else "credits allowance"
                    effective_name = plan_name or "Usage Allowance"
                    formatted_display = f"{effective_name}: {curr_sym}{num_val:,.0f} {unit_str}"
                elif has_usage_unit:
                    pricing_type = "usage_rate"
                    billing_basis = "usage"
                    if "input token" in after_match:
                        unit_str = "1M input tokens" if ("m" in after_match or "1m" in snippet_lower) else "input token"
                    elif "output token" in after_match:
                        unit_str = "1M output tokens" if ("m" in after_match or "1m" in snippet_lower) else "output token"
                    elif "character" in after_match:
                        unit_str = "1M characters" if ("m" in after_match or "1m" in snippet_lower) else "character"
                    elif "input token" in snippet_lower and "output token" not in snippet_lower:
                        unit_str = "1M input tokens" if ("m" in snippet_lower or "1m" in snippet_lower) else "input token"
                    elif "output token" in snippet_lower and "input token" not in snippet_lower:
                        unit_str = "1M output tokens" if ("m" in snippet_lower or "1m" in snippet_lower) else "output token"
                    elif "character" in snippet_lower:
                        unit_str = "1M characters" if ("m" in snippet_lower or "1m" in snippet_lower) else "character"
                    elif "1m" in after_match or "/m" in after_match or "1m" in snippet_lower or "million" in snippet_lower:
                        unit_str = "1M tokens"
                    elif "1k" in after_match or "/k" in after_match or "1k" in snippet_lower or "thousand" in snippet_lower or "1,000" in snippet_lower:
                        unit_str = "1K tokens"
                    elif "request" in after_match or "request" in snippet_lower:
                        unit_str = "request"
                    elif "query" in after_match or "query" in snippet_lower:
                        unit_str = "query"
                    elif "credit" in after_match or "credit" in snippet_lower:
                        unit_str = "credit"
                    elif "image" in after_match or "image" in snippet_lower:
                        unit_str = "image"
                    elif "gb" in after_match or "gb" in snippet_lower:
                        unit_str = "GB"
                    else:
                        unit_str = "token"
                    effective_name = model_name or plan_name or "Usage Rate"
                    formatted_display = f"{effective_name}: {curr_sym}{num_val} / {unit_str}"
                elif is_per_user:
                    pricing_type = "subscription_plan"
                    billing_basis = "per_user_monthly"
                    unit_str = "user/month"
                    effective_name = plan_name or "Team Plan"
                    formatted_display = f"{effective_name}: {curr_sym}{num_val:.2f} / {unit_str}".replace(".00 /", " /")
                elif is_annual:
                    pricing_type = "subscription_plan"
                    billing_basis = "annually"
                    unit_str = "year"
                    effective_name = plan_name or "Subscription"
                    formatted_display = f"{effective_name}: {curr_sym}{num_val:.2f} / {unit_str}".replace(".00 /", " /")
                elif is_monthly or has_recurring_unit:
                    pricing_type = "subscription_plan"
                    billing_basis = "monthly"
                    unit_str = "month"
                    effective_name = plan_name or "Monthly Plan"
                    formatted_display = f"{effective_name}: {curr_sym}{num_val:.2f} / {unit_str}".replace(".00 /", " /")
                elif "setup fee" in snippet_lower or "setup charge" in snippet_lower:
                    pricing_type = "setup_fee"
                    billing_basis = "one_time"
                    unit_str = "setup_fee"
                    effective_name = plan_name or "Setup Fee"
                    formatted_display = f"{effective_name}: {curr_sym}{num_val:.2f} (one-time setup fee)".replace(".00 (", " (")
                elif has_package_term or "one-time" in snippet_lower or "flat rate" in snippet_lower:
                    pricing_type = "one_time"
                    billing_basis = "one_time"
                    unit_str = "package"
                    effective_name = plan_name or "Package"
                    formatted_display = f"{effective_name}: {curr_sym}{num_val:.2f}".replace(".00", "")
                else:
                    pricing_type = "subscription_plan" if p.page_type == "pricing" and plan_name else "unverified"
                    billing_basis = "unspecified"
                    unit_str = "unspecified"
                    effective_name = plan_name or "Pricing"
                    formatted_display = f"{effective_name}: {curr_sym}{num_val}"

                plan_key = (effective_name.lower(), round(num_val, 4), billing_basis, unit_str, pricing_type)
                if plan_key in seen_plans:
                    continue
                seen_plans.add(plan_key)

                curr_code = "USD" if curr_sym == "$" else ("EUR" if curr_sym == "€" else ("GBP" if curr_sym == "£" else ("INR" if curr_sym == "₹" else "USD")))

                facts.append(BrandFact(
                    brand_id=self.brand_id,
                    profile_version=self.profile_version,
                    fact_type="pricing",
                    fact_value={
                        "pricing_type": pricing_type,
                        "plan_name": effective_name,
                        "amount": num_val,
                        "currency": curr_code,
                        "currency_symbol": curr_sym,
                        "unit": unit_str,
                        "billing_basis": billing_basis,
                        "associated_product": model_name or effective_name,
                        "formatted_display": formatted_display,
                        "price": str(num_val),
                        "price_text": p_text,
                        "model": formatted_display,
                        "name": effective_name,
                        "context": snippet
                    },
                    source_page_id=p.id,
                    source_url=p.final_url,
                    evidence_snippet=snippet,
                    extraction_method="pricing_regex",
                    confidence=0.90 if (p.page_type == "pricing" and plan_name and not is_allowance) else (0.80 if has_usage_unit else 0.70),
                    user_confirmed=False
                ))

    def _extract_faq_facts(self, pages: List[CrawledPage], facts: List[BrandFact]) -> None:
        seen_questions = {
            f.fact_value.get("question").lower()
            for f in facts
            if f.fact_type == "faq" and isinstance(f.fact_value, dict) and "question" in f.fact_value
        }

        for p in pages:
            if p.page_type == "faq":
                # Check if title or H1 has a question
                candidates = []
                if p.title:
                    clean_title = p.title.split("|")[0].split(" - ")[0].split(". Nike.com")[0].strip()
                    if "?" in clean_title or any(clean_title.lower().startswith(w) for w in ("how ", "what ", "why ", "when ", "can ", "does ", "is ", "where ")):
                        candidates.append(clean_title)
                for h1 in (p.headings or {}).get("h1", []):
                    clean_h1 = h1.strip()
                    if "?" in clean_h1 or any(clean_h1.lower().startswith(w) for w in ("how ", "what ", "why ", "when ", "can ", "does ", "is ", "where ")):
                        candidates.append(clean_h1)

                for q in candidates:
                    q_lower = q.lower()
                    if q_lower not in seen_questions and 10 <= len(q) <= 120:
                        # Determine answer: prefer meta_description if non-trivial, or first paragraph of extracted text
                        ans = None
                        if p.meta_description and len(p.meta_description.strip()) > 25 and not any(g in p.meta_description.lower() for g in ("customer service. nike.com", "get help")):
                            ans = p.meta_description.strip()
                        elif p.extracted_text:
                            paras = [para.strip() for para in p.extracted_text.split("\n\n") if len(para.strip()) > 30 and not para.strip().lower().startswith("get help")]
                            if paras:
                                ans = paras[0]

                        if ans:
                            seen_questions.add(q_lower)
                            facts.append(BrandFact(
                                brand_id=self.brand_id,
                                profile_version=self.profile_version,
                                fact_type="faq",
                                fact_value={"question": q, "answer": ans},
                                source_page_id=p.id,
                                source_url=p.final_url,
                                evidence_snippet=f"Q: {q}\nA: {ans[:200]}",
                                supporting_evidence=[{
                                    "source_url": p.final_url,
                                    "snippet": f"Q: {q}\nA: {ans[:200]}",
                                    "source_type": "faq_content_heuristic",
                                    "provenance_type": "verbatim_text",
                                    "heuristic_confidence": 0.85
                                }],
                                extraction_method="faq_content_heuristic",
                                confidence=0.85,
                                user_confirmed=False
                            ))
                            break

    def _extract_contact_info(self, pages: List[CrawledPage], facts: List[BrandFact]) -> None:
        seen_emails = set()
        seen_socials = set()
        for p in pages:
            text = p.extracted_text or ""
            emails = EMAIL_REGEX.findall(text)
            for email in emails:
                e_clean = email.lower().strip().rstrip(".,;:")
                if not any(e_clean.endswith(ext) for ext in (".png", ".jpg", ".svg", ".js")) and e_clean not in seen_emails:
                    seen_emails.add(e_clean)
                    facts.append(BrandFact(
                        brand_id=self.brand_id,
                        profile_version=self.profile_version,
                        fact_type="contact_info",
                        fact_value={"type": "email", "value": e_clean},
                        source_page_id=p.id,
                        source_url=p.final_url,
                        evidence_snippet=f"Email found on page: {e_clean}",
                        extraction_method="email_regex",
                        confidence=0.90,
                        user_confirmed=False
                    ))

            # External links for social media profiles
            for ext in (p.external_links or []):
                ext_l = ext.lower().strip()
                parsed_ext = urlparse(ext_l)
                ext_path = parsed_ext.path.strip("/")
                for platform in ("twitter.com", "x.com", "linkedin.com", "github.com", "youtube.com"):
                    if platform in ext_l:
                        # Share dialogs, intent, search queries, hashtags
                        if any(bad in ext_l for bad in ("/share", "/intent", "search?", "/search", "/hashtag")):
                            continue
                        # YouTube: channel/user/c only, reject watch/shorts/embed
                        if platform == "youtube.com" and any(bad in ext_l for bad in ("/watch", "/shorts", "/embed")):
                            continue
                        # LinkedIn: must be company or school profile, reject personal /in/ or post /posts/
                        if platform == "linkedin.com" and not any(ext_l.startswith(f"https://www.linkedin.com/{k}") or ext_l.startswith(f"https://linkedin.com/{k}") for k in ("company/", "school/")):
                            continue
                        # Twitter/X: must have a path segment that is an account handle, reject empty path
                        if platform in ("twitter.com", "x.com") and (not ext_path or "/" in ext_path):
                            continue
                        # GitHub: must be root organization/user, reject deep repo tree or blob links
                        if platform == "github.com" and (not ext_path or "/" in ext_path):
                            continue
                        # On blog pages, reject social links that belong to individual authors/contributors rather than the company
                        if p.page_type == "blog":
                            brand_slug = self.user_business_name.lower().replace(" ", "")
                            first_tok = self.user_business_name.lower().split()[0]
                            if brand_slug not in ext_l and first_tok not in ext_l:
                                continue

                        if ext not in seen_socials:
                            seen_socials.add(ext)
                            facts.append(BrandFact(
                                brand_id=self.brand_id,
                                profile_version=self.profile_version,
                                fact_type="contact_info",
                                fact_value={"type": "social_profile", "platform": platform, "url": ext},
                                source_page_id=p.id,
                                source_url=p.final_url,
                                evidence_snippet=f"Social link found: {ext}",
                                extraction_method="social_link_heuristic",
                                confidence=0.90,
                                user_confirmed=False
                            ))

    def _extract_languages(self, pages: List[CrawledPage], facts: List[BrandFact]) -> None:
        langs = {p.language for p in pages if p.language}
        for l in langs:
            facts.append(BrandFact(
                brand_id=self.brand_id,
                profile_version=self.profile_version,
                fact_type="supported_language",
                fact_value=l,
                source_url=pages[0].final_url,
                evidence_snippet=f"Detected html lang: {l}",
                extraction_method="html_lang",
                confidence=0.95,
                user_confirmed=False
            ))
