"""Heuristic page type classifier.
Infers page type (homepage, about, pricing, product_service, contact, faq, blog, docs, legal, other)
from URL path, title, and headings with strict disambiguation hierarchy.
"""
from urllib.parse import urlparse
from typing import List, Optional


LEGAL_KEYWORDS = (
    "terms", "privacy", "legal", "tos", "license", "agreement", "agreements",
    "compliance", "cookie", "cookies", "disclaimer", "terms-of-service",
    "enterprise-agreement", "enterprise-access", "terms-of-use", "sub-processors",
    "security-practices", "dpa", "sla", "acceptable-use", "master-services"
)

DOCS_PREFIXES = (
    "docs", "documentation", "guide", "guides", "api", "developer", "developers",
    "reference", "sdk", "manual", "kb"
)


def classify_page_type(
    url: str,
    title: Optional[str] = None,
    h1_list: Optional[List[str]] = None,
    structured_data: Optional[List[dict]] = None
) -> str:
    path = (urlparse(url).path or "").lower().strip("/")
    title_l = (title or "").lower()
    h1_combined = " ".join(h1_list or []).lower()

    if not path or path == "":
        return "homepage"

    segments = path.split("/")
    first_seg = segments[0]

    # 1. Legal / Terms / Privacy / Compliance (Must run BEFORE product/service check to avoid "terms-of-service")
    if any(k in path for k in LEGAL_KEYWORDS):
        return "legal"
    if any(k in title_l or k in h1_combined for k in (
        "terms of service", "privacy policy", "terms of use", "legal agreement",
        "access agreement", "enterprise access agreement", "master services agreement",
        "data processing", "acceptable use policy", "license agreement", "end user license"
    )):
        return "legal"

    # 2. Pricing & Plans (Must run BEFORE FAQ structured data check so pricing pages with FAQ sections remain pricing)
    if any(k in path for k in ("pricing", "plans", "tier", "subscription", "price")):
        return "pricing"
    if "pricing" in title_l or "plans" in title_l or "pricing" in h1_combined:
        return "pricing"

    # 3. Documentation & Developer Guides (Must check path prefix before checking "/features/" keyword)
    if first_seg in DOCS_PREFIXES or any(f"/{dp}/" in f"/{path}/" for dp in DOCS_PREFIXES):
        return "docs"
    if any(k in title_l for k in ("documentation", "api reference", "developer guide", "docs |", "quickstart")):
        return "docs"

    # 4. Structured Data hints (for genuine Product/Service and FAQ pages)
    if structured_data:
        for sdata in structured_data:
            stype = sdata.get("@type")
            if stype in ("Product", "ProductGroup", "IndividualProduct", "ProductModel", "SomeProducts", "Service", "SoftwareApplication"):
                return "product_service"
            if stype == "FAQPage" and "pricing" not in path:
                return "faq"

    # 5. FAQ / Help / Customer Support
    if any(k in path for k in ("faq", "faqs", "help", "support", "customer-service", "q-and-a")):
        return "faq"
    if first_seg in ("help", "support", "faq", "faqs"):
        return "faq"
    if any(k in title_l for k in ("frequently asked questions", "faq", "customer service", "help center", "nike help")):
        return "faq"

    # 6. About
    if any(k in path for k in ("about", "company", "team", "our-story", "who-we-are", "mission")):
        return "about"
    if "about us" in title_l or "about us" in h1_combined:
        return "about"

    # 7. Contact
    if any(k in path for k in ("contact", "get-in-touch", "reach-us", "sales")):
        return "contact"
    if "contact us" in title_l or "contact" in h1_combined:
        return "contact"

    # 8. Blog / News / Stories / Case Studies / Insights
    if any(k in path for k in ("blog", "news", "articles", "post", "posts", "press", "stories", "journal", "case-study", "case-studies", "insights")):
        return "blog"

    # 9. Product / Service / Feature / PDP
    if any(k in path for k in ("product", "products", "features", "feature", "service", "services", "platform", "solution", "solutions", "shop")):
        return "product_service"
    # Specific e-commerce PDP path patterns like /t/<slug> (Nike), /p/<id>, /item/<id>
    if first_seg in ("t", "p", "item", "items") and len(segments) >= 2:
        return "product_service"
    if any(k in title_l for k in ("features", "product overview", "services", "solutions")):
        return "product_service"

    return "other"
