"""Link extraction and filtering module.
Resolves relative URLs, distinguishes internal from external links,
and eliminates fragments and non-HTTP schemes.
"""
from typing import Tuple, List, Set
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from app.crawler.security import normalize_url, is_same_domain_or_subdomain

IGNORED_EXTENSIONS = (
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".ico",
    ".pdf", ".zip", ".tar", ".gz", ".rar", ".7z",
    ".mp3", ".mp4", ".wav", ".avi", ".mov",
    ".css", ".js", ".json", ".xml", ".txt"
)


def extract_page_links(html: str, current_url: str, base_domain: str) -> Tuple[List[str], List[str]]:
    """
    Extracts (internal_links, external_links) from HTML.
    All internal links are normalized and checked to ensure they match base_domain.
    """
    soup = BeautifulSoup(html, "lxml")
    internal_set: Set[str] = set()
    external_set: Set[str] = set()

    for a_tag in soup.find_all("a", href=True):
        href = a_tag["href"].strip()
        if not href or href.startswith(("#", "javascript:", "mailto:", "tel:", "data:")):
            continue

        try:
            full_url = urljoin(current_url, href)
            parsed = urlparse(full_url)
            if parsed.scheme.lower() not in ("http", "https"):
                continue

            # Skip asset extensions
            path_lower = parsed.path.lower()
            if any(path_lower.endswith(ext) for ext in IGNORED_EXTENSIONS):
                continue

            normalized = normalize_url(full_url)

            if is_same_domain_or_subdomain(normalized, base_domain):
                internal_set.add(normalized)
            else:
                external_set.add(normalized)
        except Exception:
            continue

    return sorted(list(internal_set)), sorted(list(external_set))
