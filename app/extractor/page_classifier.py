"""Heuristic page type classifier.
Infers page type (homepage, about, pricing, product_service, contact, faq, blog, docs, other)
from URL path, title, and headings.
"""
from urllib.parse import urlparse
from typing import List, Optional


def classify_page_type(url: str, title: Optional[str] = None, h1_list: Optional[List[str]] = None) -> str:
    path = (urlparse(url).path or "").lower().strip("/")
    title_l = (title or "").lower()
    h1_combined = " ".join(h1_list or []).lower()

    if not path or path == "":
        return "homepage"

    segments = path.split("/")
    first_seg = segments[0]

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

    # Product / Service / Feature
    if any(k in path for k in ("product", "products", "features", "feature", "service", "services", "platform", "solution", "solutions")):
        return "product_service"
    if any(k in title_l for k in ("features", "product overview", "services", "solutions")):
        return "product_service"

    # Contact
    if any(k in path for k in ("contact", "get-in-touch", "reach-us", "sales")):
        return "contact"
    if "contact us" in title_l or "contact" in h1_combined:
        return "contact"

    # FAQ / Help
    if any(k in path for k in ("faq", "faqs", "help", "q-and-a")):
        return "faq"
    if "frequently asked questions" in title_l or "faq" in title_l:
        return "faq"

    # Blog / News
    if any(k in path for k in ("blog", "news", "articles", "post", "posts", "press")):
        return "blog"

    # Docs / API
    if any(k in path for k in ("docs", "documentation", "guide", "guides", "api", "developer")):
        return "docs"

    return "other"
