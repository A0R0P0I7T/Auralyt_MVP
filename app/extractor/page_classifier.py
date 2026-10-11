"""Heuristic page type classifier.
Infers page type (homepage, about, pricing, product_service, contact, faq, blog, docs, other)
from URL path, title, and headings.
"""
from urllib.parse import urlparse
from typing import List, Optional


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

    # Structured Data hints
    if structured_data:
        for sdata in structured_data:
            stype = sdata.get("@type")
            if stype in ("Product", "ProductGroup", "IndividualProduct", "ProductModel", "SomeProducts", "Service", "SoftwareApplication"):
                return "product_service"
            if stype == "FAQPage":
                return "faq"

    # FAQ / Help / Customer Support (checked before product to avoid misclassifying help articles like /help/a/product-discount)
    if any(k in path for k in ("faq", "faqs", "help", "support", "customer-service", "q-and-a")):
        return "faq"
    if first_seg in ("help", "support", "faq", "faqs"):
        return "faq"
    if any(k in title_l for k in ("frequently asked questions", "faq", "customer service", "help center", "nike help")):
        return "faq"

    # Pricing
    if any(k in path for k in ("pricing", "plans", "tier", "subscription", "price")):
        return "pricing"
    if "pricing" in title_l or "plans" in title_l:
        return "pricing"

    # About
    if any(k in path for k in ("about", "company", "team", "our-story", "who-we-are", "mission")):
        return "about"
    if "about us" in title_l or "about us" in h1_combined:
        return "about"

    # Contact
    if any(k in path for k in ("contact", "get-in-touch", "reach-us", "sales")):
        return "contact"
    if "contact us" in title_l or "contact" in h1_combined:
        return "contact"

    # Product / Service / Feature / PDP
    if any(k in path for k in ("product", "products", "features", "feature", "service", "services", "platform", "solution", "solutions", "shop")):
        return "product_service"
    # Specific e-commerce PDP path patterns like /t/<slug> (Nike), /p/<id>, /item/<id>
    if first_seg in ("t", "p", "item", "items") and len(segments) >= 2:
        return "product_service"
    if any(k in title_l for k in ("features", "product overview", "services", "solutions")):
        return "product_service"

    # Blog / News / Stories / Case Studies / Insights
    if any(k in path for k in ("blog", "news", "articles", "post", "posts", "press", "stories", "journal", "case-study", "case-studies", "insights")):
        return "blog"

    # Docs / API
    if any(k in path for k in ("docs", "documentation", "guide", "guides", "api", "developer")):
        return "docs"

    return "other"
