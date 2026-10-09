"""Metadata and Structured Data extractor.
Parses meta tags, Open Graph, Twitter cards, JSON-LD, headings, and language.
"""
import json
import logging
import re
from typing import Dict, List, Optional, Any
from bs4 import BeautifulSoup
from app.crawler.security import normalize_url

logger = logging.getLogger(__name__)


def extract_metadata_and_structured_data(html: str, current_url: str) -> Dict[str, Any]:
    soup = BeautifulSoup(html, "lxml")

    # Title
    title = None
    if soup.title and soup.title.string:
        title = soup.title.string.strip()

    # Canonical URL
    canonical_url = None
    canonical_tag = soup.find("link", rel=lambda r: r and "canonical" in r.lower())
    if canonical_tag and canonical_tag.get("href"):
        try:
            canonical_url = normalize_url(canonical_tag["href"].strip())
        except Exception:
            canonical_url = canonical_tag["href"].strip()

    # Meta Description
    meta_desc = None
    desc_tag = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
    if desc_tag and desc_tag.get("content"):
        meta_desc = desc_tag["content"].strip()

    # OpenGraph & Twitter
    og_data: Dict[str, str] = {}
    for meta in soup.find_all("meta"):
        prop = meta.get("property") or meta.get("name")
        content = meta.get("content")
        if prop and content:
            prop_l = prop.strip().lower()
            if prop_l.startswith("og:") or prop_l.startswith("twitter:"):
                og_data[prop_l] = content.strip()

    if not meta_desc:
        meta_desc = og_data.get("og:description") or og_data.get("twitter:description")

    if not title:
        title = og_data.get("og:title") or og_data.get("twitter:title")

    # Headings
    h1_list: List[str] = []
    for h in soup.find_all("h1"):
        txt = h.get_text(separator=" ", strip=True)
        if txt and txt not in h1_list:
            h1_list.append(txt)

    h2_list: List[str] = []
    for h in soup.find_all("h2"):
        txt = h.get_text(separator=" ", strip=True)
        if txt and txt not in h2_list:
            h2_list.append(txt)

    # Language
    language = None
    html_tag = soup.find("html")
    if html_tag and html_tag.get("lang"):
        language = html_tag["lang"].strip().split("-")[0].lower()
    else:
        lang_meta = soup.find("meta", attrs={"http-equiv": re.compile(r"^content-language$", re.I)})
        if lang_meta and lang_meta.get("content"):
            language = lang_meta["content"].strip().split("-")[0].lower()

    # JSON-LD Structured Data
    structured_data: List[Dict[str, Any]] = []
    for script in soup.find_all("script", attrs={"type": re.compile(r"application/ld\+json", re.I)}):
        if not script.string:
            continue
        try:
            raw_json = script.string.strip()
            parsed = json.loads(raw_json)
            if isinstance(parsed, list):
                structured_data.extend(parsed)
            elif isinstance(parsed, dict):
                # Check for @graph
                if "@graph" in parsed and isinstance(parsed["@graph"], list):
                    structured_data.extend(parsed["@graph"])
                else:
                    structured_data.append(parsed)
        except Exception as e:
            logger.debug(f"Failed to parse JSON-LD on {current_url}: {e}")

    return {
        "title": title,
        "canonical_url": canonical_url,
        "meta_description": meta_desc,
        "headings": {
            "h1": h1_list,
            "h2": h2_list
        },
        "og_data": og_data,
        "language": language,
        "structured_data": structured_data
    }
