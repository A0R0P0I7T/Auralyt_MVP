"""Deterministic Brand Fact Synthesizer and Provenance Tracker.
Extracts structured brand profile evidence from crawled pages and structured data
without requiring paid LLM calls. Maintains complete provenance and confidence scores.
"""
import re
from typing import List, Dict, Any, Optional, Tuple
from urllib.parse import urlparse
from app.db.models import CrawledPage, BrandFact


EMAIL_REGEX = re.compile(r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+")
PHONE_REGEX = re.compile(r"(\+?[0-9]{1,3}[-.\s]?)?(\(?\d{3}\)?[-.\s]?)[\d.-]{7,10}")
PRICING_TIER_REGEX = re.compile(r"\b(Free|Starter|Basic|Pro|Professional|Growth|Business|Enterprise|Team)\b", re.I)
PRICE_CURRENCY_REGEX = re.compile(r"(\$|€|£|₹)\s?(\d+(?:,\d{3})*(?:\.\d+)?)\s?(?:/\s?(?:mo|month|yr|year|user|seat))?", re.I)

DISALLOWED_PRODUCT_NAMES = {
    # Continents & Regions
    "africa", "americas", "asia pacific", "europe", "middle east",
    "north america", "south america", "latin america", "oceania", "antarctica",
    "united states", "global", "worldwide", "international",
    # Generic Navigation & Support / Auth Actions
    "get help", "help", "contact us", "customer service", "sign in", "sign up",
    "log in", "cart", "bag", "checkout", "view cart", "order status",
    "shipping & delivery", "returns", "terms of sale", "privacy policy",
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

NON_PRODUCT_PREFIXES = (
    "get ", "talk to ", "contact ", "sign ", "explore ", "learn ", "see ",
    "try ", "join ", "read ", "watch ", "execute ", "turn ", "understand ",
    "know ", "start ", "build for ", "loved by ", "trusted by ", "from ",
    "all platform ", "teams ship ", "connect your ", "how teams ", "find ", "choose "
)

AUDIENCE_ROLE_WORDS = {
    "team", "teams", "developer", "developers", "engineer", "engineers",
    "designer", "designers", "creator", "creators", "marketer", "marketers",
    "founder", "founders", "builder", "builders", "enterprise", "enterprises",
    "business", "businesses", "company", "companies", "startup", "startups",
    "organization", "organizations", "agency", "agencies", "customer", "customers",
    "user", "users", "client", "clients", "professional", "professionals",
    "individual", "individuals", "runner", "runners", "athlete", "athletes",
    "enthusiast", "enthusiasts", "beginner", "beginners", "expert", "experts",
    "student", "students", "people", "everyone", "smb", "smbs", "b2b", "b2c",
    "leader", "leaders", "manager", "managers", "operator", "operators"
}

AUDIENCE_DISALLOWED_WORDS = {
    "speed", "scale", "performance", "privacy", "security", "the future",
    "modern web", "the cloud", "simplicity", "reliability", "efficiency",
    "collaboration", "growth", "today's reality", "the ai era", "tomorrow",
    "production", "the pavement", "any screen", "all devices"
}


def is_valid_product_candidate(name: str, brand_name: str = "") -> bool:
    clean = name.strip()
    lower = clean.lower()
    if brand_name and lower == brand_name.strip().lower():
        return False
    if lower in DISALLOWED_PRODUCT_NAMES:
        return False
    if clean.startswith("#"):
        return False
    if any(lower.startswith(pfx) for pfx in NON_PRODUCT_PREFIXES):
        return False
    if clean.endswith((".", "!", "?")):
        return False
    if "—" in clean or "--" in clean:
        return False
    words = clean.split()
    if len(words) > 6 or len(words) < 1:
        return False
    if len(words) == 1 and lower in {"measure", "recommend", "act", "build", "ship", "deploy", "scale"}:
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
                extraction_method="user_input",
                confidence=1.0,
                user_confirmed=True
            ))

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

        # 7. Pricing Information
        self._extract_pricing_facts(pages, facts)

        # 8. FAQs from FAQ/Help pages
        self._extract_faq_facts(pages, facts)

        # 9. Contact & Company Details (Email, phone, social)
        self._extract_contact_info(pages, facts)

        # 10. Supported Languages
        self._extract_languages(pages, facts)

        return facts

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

        # 5. From general brand storefront/landing pages (non-support, non-contact)
        for p in pages:
            if p.page_type not in ("faq", "contact") and p.meta_description and len(p.meta_description.strip()) > 25:
                p_desc_lower = p.meta_description.lower()
                if not any(g in p_desc_lower for g in ("customer service", "help center", "get help")):
                    return p.meta_description.strip(), p, f"Landing page description: {p.meta_description[:200]}...", "meta_description", 0.75

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
            # Check dedicated product/service pages and homepage H1s (excluding slogans)
            if p.page_type in ("product_service", "homepage"):
                headings = p.headings or {}
                h1_list = headings.get("h1", [])
                h2_list = headings.get("h2", []) if p.page_type == "product_service" else []

                page_has_product = False
                for heading in h1_list + h2_list:
                    h_clean = heading.strip()
                    h_lower = h_clean.lower()
                    if not is_valid_product_candidate(h_clean, effective_brand):
                        continue
                    if any(bad in h_lower for bad in ("privacy policy", "terms of", "cookie", "get help", "customer service")):
                        continue
                    if 3 <= len(h_clean) <= 60 and h_lower not in seen_products:
                        seen_products.add(h_lower)
                        page_has_product = True
                        facts.append(BrandFact(
                            brand_id=self.brand_id,
                            profile_version=self.profile_version,
                            fact_type="product_service",
                            fact_value={"name": h_clean, "page_title": p.title, "url": p.final_url},
                            source_page_id=p.id,
                            source_url=p.final_url,
                            evidence_snippet=f"Heading '{h_clean}' on {p.page_type} page ({p.final_url})",
                            extraction_method="heading_heuristic",
                            confidence=0.85 if p.page_type == "product_service" else 0.75,
                            user_confirmed=False
                        ))

                # If no heading yielded a product on a product_service page, use the page title
                if p.page_type == "product_service" and not page_has_product and p.title:
                    cand = p.title.split("—")[0].split("|")[0].split(" - ")[0].strip()
                    cand_lower = cand.lower()
                    if is_valid_product_candidate(cand, effective_brand) and cand_lower not in seen_products:
                        seen_products.add(cand_lower)
                        facts.append(BrandFact(
                            brand_id=self.brand_id,
                            profile_version=self.profile_version,
                            fact_type="product_service",
                            fact_value={"name": cand, "page_title": p.title, "url": p.final_url},
                            source_page_id=p.id,
                            source_url=p.final_url,
                            evidence_snippet=f"Page title '{cand}' on product_service page ({p.final_url})",
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
                                evidence_snippet=f"Feature list item: '{feat}'",
                                extraction_method="bullet_heuristic",
                                confidence=0.75,
                                user_confirmed=False
                            ))
                    elif len(l_str) > 0 and not l_str.startswith(("-", "•", "*")):
                        # End of list
                        in_features_block = False

    def _extract_audience_and_use_cases(self, pages: List[CrawledPage], facts: List[BrandFact]) -> None:
        target_patterns = [
            (r"(?:built|designed|made)\s+for\s+([^.\n]+)", "target_audience"),
            (r"(?:who\s+it'?s\s+for|who\s+uses\s+us)\s*[:?]?\s*([^.\n]+)", "target_audience"),
            (r"(?:use\s+case|solutions?\s+for)\s*[:\-]?\s*([^.\n]+)", "use_case"),
            (r"(?:why\s+choose\s+us|our\s+advantage|differentiator)\s*[:\-]?\s*([^.\n]+)", "differentiator"),
        ]

        seen_audience = set()
        seen_use_cases = set()
        seen_diffs = set()

        for f in facts:
            if f.fact_type == "target_audience" and isinstance(f.fact_value, str):
                seen_audience.add(f.fact_value.strip().lower())

        for p in pages:
            text = p.extracted_text or ""
            for pattern, ftype in target_patterns:
                matches = re.finditer(pattern, text, re.I)
                for m in matches:
                    raw_val = m.group(1).strip()
                    val = raw_val.strip(" \t\r\n,;:-–—\"'“”()[]")
                    if not (5 <= len(val) <= 120):
                        continue
                    val_lower = val.lower()

                    if ftype == "target_audience":
                        if any(q in val_lower for q in ("said ", "says ", "according to ")):
                            continue
                        if val_lower in AUDIENCE_DISALLOWED_WORDS:
                            continue
                        words = set(re.findall(r"\b[a-zA-Z]+\b", val_lower))
                        if not words.intersection(AUDIENCE_ROLE_WORDS) and not any(k in val_lower for k in ("who want", "looking to", "those who")):
                            continue
                        if val_lower in seen_audience:
                            continue
                        seen_audience.add(val_lower)

                    elif ftype == "use_case":
                        if val_lower in seen_use_cases or len(val) < 5:
                            continue
                        seen_use_cases.add(val_lower)

                    elif ftype == "differentiator":
                        if val_lower in seen_diffs or len(val) < 5:
                            continue
                        seen_diffs.add(val_lower)

                    facts.append(BrandFact(
                        brand_id=self.brand_id,
                        profile_version=self.profile_version,
                        fact_type=ftype,
                        fact_value=val,
                        source_page_id=p.id,
                        source_url=p.final_url,
                        evidence_snippet=m.group(0)[:180],
                        extraction_method="regex_pattern",
                        confidence=0.75,
                        user_confirmed=False
                    ))

    def _extract_pricing_facts(self, pages: List[CrawledPage], facts: List[BrandFact]) -> None:
        pricing_pages = [p for p in pages if p.page_type == "pricing"]
        target_pages = pricing_pages if pricing_pages else pages

        for p in target_pages:
            # Look for JSON-LD Offers (direct offers or within hasVariant)
            for sdata in (p.structured_data or []):
                offers = sdata.get("offers")
                if offers:
                    offers_list = offers if isinstance(offers, list) else [offers]
                    for off in offers_list:
                        price = off.get("price")
                        currency = off.get("priceCurrency", "USD")
                        if price:
                            facts.append(BrandFact(
                                brand_id=self.brand_id,
                                profile_version=self.profile_version,
                                fact_type="pricing",
                                fact_value={"price": str(price), "currency": currency, "name": off.get("name")},
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
                                if isinstance(off, dict) and off.get("price"):
                                    price_val = str(off["price"])
                                    curr = off.get("priceCurrency", "USD")
                                    facts.append(BrandFact(
                                        brand_id=self.brand_id,
                                        profile_version=self.profile_version,
                                        fact_type="pricing",
                                        fact_value={"price": price_val, "currency": curr, "name": var.get("name") or sdata.get("name")},
                                        source_page_id=p.id,
                                        source_url=p.final_url,
                                        evidence_snippet=f"JSON-LD Variant Offer: {curr} {price_val}",
                                        extraction_method="json_ld_offer",
                                        confidence=0.95,
                                        user_confirmed=False
                                    ))
                                    break

            # Search text for tier plans and prices
            text = p.extracted_text or ""
            seen_price_texts = set()
            price_matches = PRICE_CURRENCY_REGEX.finditer(text)
            for pm in price_matches:
                p_text = pm.group(0).strip()
                # Check for scale/magnitude multipliers or revenue/funding terms immediately following the price
                after_match = text[pm.end():pm.end() + 25].lower()
                if re.match(r"^\s*(?:\.\d+)?\s*(?:million|billion|trillion|m\b|b\b|k\b|arr\b|series\b|valuation\b|funding\b|revenue\b)", after_match):
                    continue

                snippet_start = max(0, pm.start() - 40)
                snippet_end = min(len(text), pm.end() + 40)
                snippet = text[snippet_start:snippet_end].replace("\n", " ").strip()

                # On non-pricing pages, require explicit subscription unit or pricing tier keywords in context
                if p.page_type != "pricing":
                    has_sub_unit = any(unit in p_text.lower() for unit in ("/mo", "/month", "/yr", "/year", "/user", "/seat"))
                    has_pricing_context = any(
                        kw in snippet.lower()
                        for kw in ("pricing", "plan", "plans", "tier", "subscription", "per month", "per year", "billed monthly", "billed annually", "starting at", "free tier", "$0")
                    )
                    if not (has_sub_unit or has_pricing_context):
                        continue

                if p_text in seen_price_texts:
                    continue
                seen_price_texts.add(p_text)

                facts.append(BrandFact(
                    brand_id=self.brand_id,
                    profile_version=self.profile_version,
                    fact_type="pricing",
                    fact_value={"price_text": p_text, "context": snippet},
                    source_page_id=p.id,
                    source_url=p.final_url,
                    evidence_snippet=snippet,
                    extraction_method="pricing_regex",
                    confidence=0.85 if p.page_type == "pricing" else 0.70,
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
                                evidence_snippet=f"FAQ from {p.final_url}: Q: {q} | A: {ans[:150]}",
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
                for platform in ("twitter.com", "x.com", "linkedin.com", "github.com", "youtube.com"):
                    if platform in ext.lower() and "/share" not in ext.lower() and "/intent" not in ext.lower() and ext not in seen_socials:
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
