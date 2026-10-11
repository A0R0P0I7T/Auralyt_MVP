"""Sitemap discovery and parsing module.
Handles XML sitemaps, sitemap indexes, and prioritizes high-value brand URLs
with strict SSRF validation and domain scope boundaries.
"""
import gzip
import io
import logging
import xml.etree.ElementTree as ET
from typing import List, Set, Tuple, Optional
from urllib.parse import urljoin
import httpx
from app.core.config import settings
from app.crawler.security import (
    normalize_url,
    is_same_domain_or_subdomain,
    validate_and_resolve_url,
    SecurityValidationError
)
from app.crawler.transport import create_safe_httpx_client

logger = logging.getLogger(__name__)

COMMON_SITEMAP_PATHS = [
    "/sitemap.xml",
    "/sitemap_index.xml",
    "/sitemap1.xml",
    "/sitemaps.xml",
]

HIGH_VALUE_KEYWORDS = [
    "about", "product", "products", "service", "services", "feature", "features",
    "pricing", "price", "plan", "plans", "solution", "solutions", "faq", "contact",
    "use-case", "use-cases", "case-study", "integrations", "security", "overview",
    "ai", "enterprise", "platform", "tools", "insights",
    "t", "shop", "men", "women", "kids", "jordan", "acg", "launch"
]


def score_url_priority(url: str) -> int:
    """Return priority score: lower number means higher priority."""
    url_lower = url.lower()
    # Deprioritize help / support / locator / changelog / deep api reference URLs so they don't crowd out core products
    if any(k in url_lower for k in ("/help", "/support", "/locator", "/store", "/changelog", "/releases", "/rest-api", "/kb/guide")):
        return 3
    for kw in HIGH_VALUE_KEYWORDS:
        if f"/{kw}" in url_lower or f"-{kw}" in url_lower:
            return 1
    return 2


def score_sitemap_priority(sm_url: str) -> int:
    sm_l = sm_url.lower()
    if any(k in sm_l for k in ("landing", "product", "pdp", "article", "stories", "collection", "main", "shop")):
        return 0
    if any(k in sm_l for k in ("help", "support", "faq", "locator", "store", "legal")):
        return 2
    return 1


def score_sub_sitemap_locale(sub_url: str) -> int:
    sub_l = sub_url.lower()
    if "en-us" in sub_l or "en_us" in sub_l:
        return 0
    if "en-gb" in sub_l or "en_gb" in sub_l:
        return 1
    if "-en-" in sub_l or "/en/" in sub_l or "-en." in sub_l:
        return 2
    if "us." in sub_l or "-us-" in sub_l or "-us." in sub_l or "/us/" in sub_l:
        return 3
    return 4


class SitemapDiscoverer:
    def __init__(self, base_url: str, base_domain: str, max_urls: int = 100, max_sitemap_files: int = 15):
        self.base_url = normalize_url(base_url)
        self.base_domain = base_domain.lower()
        self.max_urls = max_urls
        self.max_sitemap_files = max_sitemap_files
        self.discovered_urls: List[str] = []
        self.warnings: List[str] = []
        self.sitemaps_processed = 0

    async def discover(self, seed_sitemaps: Optional[List[str]] = None, client: Optional[httpx.AsyncClient] = None) -> List[str]:
        candidates: List[str] = []
        if seed_sitemaps:
            for sm in seed_sitemaps:
                if is_same_domain_or_subdomain(sm, self.base_domain):
                    candidates.append(sm)

        for path in COMMON_SITEMAP_PATHS:
            full_path = urljoin(self.base_url, path)
            if full_path not in candidates and is_same_domain_or_subdomain(full_path, self.base_domain):
                candidates.append(full_path)

        # Sort candidate sitemaps by priority (products/landing first, help last)
        candidates.sort(key=score_sitemap_priority)

        close_client = False
        if client is None:
            client = await create_safe_httpx_client(timeout=settings.REQUEST_TIMEOUT_SECONDS)
            close_client = True

        visited_sitemaps: Set[str] = set()
        extracted_set: Set[str] = set()

        try:
            # Fair budget per candidate sitemap to prevent a single sitemap from starving the rest
            per_sm_quota = max(15, self.max_urls // max(1, len(candidates))) if len(candidates) > 1 else self.max_urls

            for sm_url in candidates:
                if self.sitemaps_processed >= self.max_sitemap_files or len(extracted_set) >= self.max_urls:
                    break
                if sm_url in visited_sitemaps:
                    continue

                target_limit = min(self.max_urls, len(extracted_set) + per_sm_quota)
                await self._process_sitemap(sm_url, visited_sitemaps, extracted_set, client, target_limit=target_limit)

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
        client: httpx.AsyncClient,
        target_limit: Optional[int] = None
    ) -> None:
        effective_limit = target_limit if target_limit is not None else self.max_urls
        if self.sitemaps_processed >= self.max_sitemap_files or sm_url in visited or len(extracted) >= effective_limit:
            return

        visited.add(sm_url)

        try:
            current_sm_url = sm_url
            max_redirects = 3
            redirect_count = 0
            visited_chain = {current_sm_url}
            final_response = None

            # Safe hop-by-hop redirect loop
            while True:
                try:
                    norm_url, _, _ = validate_and_resolve_url(current_sm_url)
                except SecurityValidationError as se:
                    self.warnings.append(f"Skipping sitemap {current_sm_url}: {se}")
                    return

                if not is_same_domain_or_subdomain(norm_url, self.base_domain):
                    self.warnings.append(f"Sitemap redirected out of domain scope: {norm_url}")
                    return

                response = await client.get(
                    norm_url,
                    headers={"User-Agent": settings.USER_AGENT},
                    follow_redirects=False
                )

                if response.status_code in (301, 302, 303, 307, 308):
                    redirect_count += 1
                    if redirect_count > max_redirects:
                        self.warnings.append(f"Sitemap {sm_url} exceeded max redirects.")
                        return

                    loc = response.headers.get("location") or response.headers.get("Location")
                    if not loc:
                        return

                    next_url = normalize_url(urljoin(current_sm_url, loc))
                    if next_url in visited_chain:
                        return

                    visited_chain.add(next_url)
                    current_sm_url = next_url
                    continue

                final_response = response
                break

            if final_response is None or final_response.status_code != 200:
                return

            self.sitemaps_processed += 1
            content = final_response.content

            # Enforce max response size
            if len(content) > settings.MAX_RESPONSE_SIZE_BYTES:
                self.warnings.append(f"Sitemap exceeded maximum size: {current_sm_url}")
                return

            # Decompress if gzipped
            if current_sm_url.endswith(".gz") or content[:2] == b"\x1f\x8b":
                try:
                    with gzip.GzipFile(fileobj=io.BytesIO(content)) as gz:
                        decompressed_chunks = []
                        total_decompressed = 0
                        while True:
                            chunk = gz.read(65536)
                            if not chunk:
                                break
                            total_decompressed += len(chunk)
                            if total_decompressed > settings.MAX_RESPONSE_SIZE_BYTES:
                                self.warnings.append(
                                    f"Decompressed sitemap exceeded max limit ({settings.MAX_RESPONSE_SIZE_BYTES} bytes): {current_sm_url}"
                                )
                                return
                            decompressed_chunks.append(chunk)
                        content = b"".join(decompressed_chunks)
                except Exception as e:
                    self.warnings.append(f"Failed to decompress gzipped sitemap {current_sm_url}: {e}")
                    return

            text_content = content.decode("utf-8", errors="ignore")

            try:
                root = ET.fromstring(text_content)
            except ET.ParseError:
                self.warnings.append(f"Malformed XML in sitemap: {current_sm_url}")
                return

            tag = root.tag.lower()

            # Handle Sitemap Index (<sitemapindex>)
            if "sitemapindex" in tag:
                sub_sitemaps = []
                for child in root:
                    if child.tag.endswith("sitemap"):
                        for elem in child:
                            if elem.tag.endswith("loc") and elem.text:
                                sub_loc = elem.text.strip()
                                # Validate sub-sitemap is in scope before recurring
                                if is_same_domain_or_subdomain(sub_loc, self.base_domain):
                                    sub_sitemaps.append(sub_loc)
                                else:
                                    logger.warning(f"Ignoring out-of-scope sub-sitemap: {sub_loc}")

                # Sort sub-sitemaps by locale priority (English/US first)
                sub_sitemaps.sort(key=score_sub_sitemap_locale)

                for sub_sm in sub_sitemaps:
                    if len(extracted) >= effective_limit or self.sitemaps_processed >= self.max_sitemap_files:
                        break
                    await self._process_sitemap(sub_sm, visited, extracted, client, target_limit=target_limit)

            # Handle Standard Urlset (<urlset>)
            elif "urlset" in tag:
                for child in root:
                    if child.tag.endswith("url"):
                        for elem in child:
                            if elem.tag.endswith("loc") and elem.text:
                                raw_loc = elem.text.strip()
                                try:
                                    # Validate loc URL before accepting
                                    validate_and_resolve_url(raw_loc)
                                    norm = normalize_url(raw_loc)
                                    if is_same_domain_or_subdomain(norm, self.base_domain):
                                        if norm not in extracted:
                                            extracted.add(norm)
                                        if len(extracted) >= effective_limit:
                                            return
                                except Exception:
                                    continue
        except Exception as e:
            logger.warning(f"Error processing sitemap {sm_url}: {e}")
            self.warnings.append(f"Error processing sitemap {sm_url}: {str(e)}")
