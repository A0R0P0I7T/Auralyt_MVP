"""Unified Page Extraction Pipeline.
Extracts metadata, headings, main text, structured data, links, and classifies page type.
"""
from typing import Dict, Any, Optional
from app.extractor.html_cleaner import clean_html_and_extract_text
from app.extractor.metadata import extract_metadata_and_structured_data
from app.extractor.page_classifier import classify_page_type
from app.extractor.links import extract_page_links


def extract_page_content(
    html: str,
    requested_url: str,
    final_url: str,
    http_status: int,
    base_domain: str,
    used_js: bool = False
) -> Dict[str, Any]:
    """
    Extracts structured content from a crawled HTML page.
    """
    # 1. Strip boilerplate and extract clean text + markdown + hash
    plain_text, md_text, content_hash = clean_html_and_extract_text(html)

    # 2. Extract metadata and structured data
    meta_info = extract_metadata_and_structured_data(html, final_url)

    # 3. Classify page type
    page_type = classify_page_type(
        final_url,
        title=meta_info.get("title"),
        h1_list=meta_info.get("headings", {}).get("h1", []),
        structured_data=meta_info.get("structured_data")
    )

    # 4. Extract internal & external links
    internal_links, external_links = extract_page_links(html, final_url, base_domain)

    # Determine status
    extraction_status = "success"
    error_details = None
    if not plain_text and http_status == 200:
        extraction_status = "partial"
        lower_html = html.lower() if html else ""
        title_lower = (meta_info.get("title") or "").lower()
        if (
            any(marker in lower_html for marker in ('id="__next"', 'id="root"', 'id="app"', 'role="dialog"', 'type="password"'))
            or any(term in title_lower for term in ("login", "sign in", "auth"))
        ):
            error_details = "Page appears to be a client-rendered single-page app or authentication portal with minimal static text content."
        else:
            error_details = "Extracted readable text was empty or minimal."
    elif http_status >= 400:
        extraction_status = "failed"
        error_details = f"HTTP Error {http_status}"

    return {
        "requested_url": requested_url,
        "final_url": final_url,
        "canonical_url": meta_info.get("canonical_url"),
        "http_status": http_status,
        "title": meta_info.get("title"),
        "meta_description": meta_info.get("meta_description"),
        "headings": meta_info.get("headings", {"h1": [], "h2": []}),
        "extracted_text": plain_text,
        "markdown_text": md_text,
        "structured_data": meta_info.get("structured_data", []),
        "internal_links": internal_links,
        "external_links": external_links,
        "page_type": page_type,
        "language": meta_info.get("language"),
        "content_hash": content_hash,
        "extraction_status": extraction_status,
        "error_details": error_details,
        "used_js": used_js
    }
