"""Sitemap discovery and parsing module.
Handles XML sitemaps, sitemap indexes, and prioritizes high-value brand URLs.
"""
import gzip
import io
import logging
import xml.etree.ElementTree as ET
from typing import List, Set, Tuple, Optional
from urllib.parse import urljoin
import httpx
from app.core.config import settings
from app.crawler.security import normalize_url, is_same_domain_or_subdomain, validate_and_resolve_url

logger = logging.getLogger(__name__)

COMMON_SITEMAP_PATHS = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap1.xml",
    "/sitemaps.xml",
]

# Keywords indicating high-value brand pages
HIGH_VALUE_KEYWORDS = [
    "about", "product", "products", "service", "services", "feature", "features",
    "pricing", "price", "plan", "plans", "solution", "solutions", "faq", "contact",
    "use-case", "use-cases", "case-study", "integrations", "security", "overview"
]


def score_url_priority(url: str) -> int:
    """Return priority score: lower number means higher priority."""
    url_lower = url.lower()
    for kw in HIGH_VALUE_KEYWORDS:
        if f"/{kw}" in url_lower or f"-{kw}" in url_lower:
            return 1
    return 2


class SitemapDiscoverer:
    def __init__(self, base_url: str, base_domain: str, max_urls: int = 100, max_sitemap_files: int = 5):
        self.base_url = base_url
        self.base_domain = base_domain
        self.max_urls = max_urls
        self.max_sitemap_files = max_sitemap_files
        self.discovered_urls: List[str] = []
        self.warnings: List[str] = []
        self.sitemaps_processed = 0

    async def discover(self, seed_sitemaps: Optional[List[str]] = None, client: Optional[httpx.AsyncClient] = None) -> List[str]:
        candidates: List[str] = []
        if seed_sitemaps:
            candidates.extend(seed_sitemaps)
        for path in COMMON_SITEMAP_PATHS:
            full_path = urljoin(self.base_url, path)
            if full_path not in candidates:
                candidates.append(full_path)

        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS, follow_redirects=True)
            close_client = True

        visited_sitemaps: Set[str] = set()
        extracted_set: Set[str] = set()

        try:
            for sm_url in candidates:
                if self.sitemaps_processed >= self.max_sitemap_files or len(extracted_set) >= self.max_urls:
                    break
                if sm_url in visited_sitemaps:
                    continue

                await self._process_sitemap(sm_url, visited_sitemaps, extracted_set, client)

            if not extracted_set and not self.warnings:
                self.warnings.append("No accessible or valid sitemaps found.")

        finally:
            if close_client:
                await client.aclose()

        # Sort discovered URLs by priority
        sorted_urls = sorted(list(extracted_set), key=score_url_priority)
        self.discovered_urls = sorted_urls[:self.max_urls]
        return self.discovered_urls

    async def _process_sitemap(
        self,
        sm_url: str,
        visited: Set[str],
        extracted: Set[str],
        client: httpx.AsyncClient
    ) -> None:
        if self.sitemaps_processed >= self.max_sitemap_files or sm_url in visited:
            return

        visited.add(sm_url)

        try:
            # SSRF check on sitemap URL
            try:
                validate_and_resolve_url(sm_url)
            except Exception as e:
                self.warnings.append(f"Skipping sitemap {sm_url}: {e}")
                return

            response = await client.get(sm_url, headers={"User-Agent": settings.USER_AGENT})
            if response.status_code != 200:
                return

            self.sitemaps_processed += 1
            content = response.content

            # Decompress if gzipped
            if sm_url.endswith(".gz") or content[:2] == b"\x1f\x8b":
                try:
                    with gzip.GzipFile(fileobj=io.BytesIO(content)) as gz:
                        content = gz.read()
                except Exception as e:
                    self.warnings.append(f"Failed to decompress gzipped sitemap {sm_url}: {e}")
                    return

            text_content = content.decode("utf-8", errors="ignore")
            # Parse XML
            try:
                root = ET.fromstring(text_content)
            except ET.ParseError:
                self.warnings.append(f"Malformed XML in sitemap: {sm_url}")
                return

            tag = root.tag.lower()
            # If Sitemap Index (<sitemapindex>)
            if "sitemapindex" in tag:
                sub_sitemaps = []
                for child in root:
                    if child.tag.endswith("sitemap"):
                        for elem in child:
                            if elem.tag.endswith("loc") and elem.text:
                                sub_sitemaps.append(elem.text.strip())

                for sub_sm in sub_sitemaps:
                    if len(extracted) >= self.max_urls or self.sitemaps_processed >= self.max_sitemap_files:
                        break
                    await self._process_sitemap(sub_sm, visited, extracted, client)

            # If standard urlset (<urlset>)
            elif "urlset" in tag:
                for child in root:
                    if child.tag.endswith("url"):
                        for elem in child:
                            if elem.tag.endswith("loc") and elem.text:
                                raw_loc = elem.text.strip()
                                norm = normalize_url(raw_loc)
                                if is_same_domain_or_subdomain(norm, self.base_domain):
                                    extracted.add(norm)
                                    if len(extracted) >= self.max_urls:
                                        return
        except Exception as e:
            logger.warning(f"Error processing sitemap {sm_url}: {e}")
            self.warnings.append(f"Error processing sitemap {sm_url}: {str(e)}")
