"""Scrapling-powered crawler engine for Auralyt MVP — Engine 1.
Implements polite, concurrency-bounded, prioritized crawling with robots compliance,
SSRF defense, and fallback browser rendering.
"""
import asyncio
import logging
import time
from typing import Dict, List, Set, Optional, Callable, Awaitable
from urllib.parse import urlparse
from scrapling import AsyncFetcher, DynamicFetcher
from app.core.config import settings
from app.crawler.security import (
    validate_and_resolve_url,
    normalize_url,
    is_same_domain_or_subdomain,
    SecurityValidationError
)
from app.crawler.robots import RobotsPolicy
from app.crawler.sitemap import SitemapDiscoverer, score_url_priority
from app.extractor.page_extractor import extract_page_content

logger = logging.getLogger(__name__)


class CrawlItem:
    def __init__(self, url: str, depth: int = 0, priority: int = 2):
        self.url = url
        self.depth = depth
        self.priority = priority


class ScraplingCrawler:
    def __init__(
        self,
        base_url: str,
        page_limit: int = 30,
        max_depth: int = 3,
        on_progress: Optional[Callable[[Dict[str, int]], Awaitable[None]]] = None
    ):
        self.base_url = normalize_url(base_url)
        self.base_domain = urlparse(self.base_url).hostname or ""
        self.page_limit = min(page_limit, settings.HARD_MAX_PAGE_LIMIT)
        self.max_depth = min(max_depth, settings.MAX_CRAWL_DEPTH)
        self.on_progress = on_progress

        # State
        self.visited_urls: Set[str] = set()
        self.canonical_map: Dict[str, str] = {}
        self.crawled_pages: List[Dict] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []

        # Metrics
        self.pages_discovered = 0
        self.pages_attempted = 0
        self.pages_succeeded = 0
        self.pages_skipped = 0
        self.pages_failed = 0

        self.robots_policy = RobotsPolicy(self.base_url)
        self.semaphore = asyncio.Semaphore(settings.PER_HOST_CONCURRENCY)

    async def run(self) -> List[Dict]:
        """Execute the complete crawl run."""
        logger.info(f"Starting Scrapling crawl on {self.base_url} (limit: {self.page_limit})")

        # 1. Fetch robots.txt
        await self.robots_policy.fetch_and_parse()
        if self.robots_policy.error:
            self.warnings.append(f"Robots.txt notice: {self.robots_policy.error}")

        # 2. Discover sitemap URLs
        sitemap_discoverer = SitemapDiscoverer(self.base_url, self.base_domain)
        sitemap_urls = await sitemap_discoverer.discover(seed_sitemaps=self.robots_policy.sitemaps)
        self.warnings.extend(sitemap_discoverer.warnings)

        # 3. Initialize Queue: Homepage first, then sitemap URLs
        queue: List[CrawlItem] = []
        queue.append(CrawlItem(url=self.base_url, depth=0, priority=0))

        for sm_url in sitemap_urls:
            if sm_url != self.base_url:
                queue.append(CrawlItem(url=sm_url, depth=1, priority=score_url_priority(sm_url)))

        self.pages_discovered = len(queue)
        await self._notify_progress()

        # 4. Crawl Loop
        while queue and len(self.crawled_pages) < self.page_limit:
            # Sort queue by priority (lowest number = highest priority), then depth
            queue.sort(key=lambda item: (item.priority, item.depth))
            current_item = queue.pop(0)

            url = current_item.url
            if url in self.visited_urls:
                continue

            # Check robots permission
            if not self.robots_policy.is_allowed(url):
                self.pages_skipped += 1
                self.warnings.append(f"Skipped {url}: Disallowed by robots.txt")
                self.visited_urls.add(url)
                continue

            self.visited_urls.add(url)
            self.pages_attempted += 1

            # Fetch and process page
            page_data = await self._fetch_and_extract(url)

            if page_data:
                canonical = page_data.get("canonical_url")
                if canonical and canonical in self.canonical_map:
                    # Duplicate canonical page already crawled
                    self.pages_skipped += 1
                    continue

                if canonical:
                    self.canonical_map[canonical] = url

                self.crawled_pages.append(page_data)
                self.pages_succeeded += 1

                # Discover new internal links if depth allows
                if current_item.depth < self.max_depth:
                    for link in page_data.get("internal_links", []):
                        if (
                            link not in self.visited_urls
                            and not any(q.url == link for q in queue)
                            and len(self.crawled_pages) + len(queue) < self.page_limit * 2
                        ):
                            queue.append(CrawlItem(
                                url=link,
                                depth=current_item.depth + 1,
                                priority=score_url_priority(link) + 1
                            ))
                            self.pages_discovered += 1
            else:
                self.pages_failed += 1

            await self._notify_progress()
            # Politeness delay
            delay = self.robots_policy.crawl_delay or settings.PER_HOST_DELAY_SECONDS
            await asyncio.sleep(delay)

        logger.info(f"Crawl completed. Succeeded: {self.pages_succeeded}, Failed: {self.pages_failed}")
        return self.crawled_pages

    async def _fetch_and_extract(self, url: str) -> Optional[Dict]:
        """Fetch a single URL using Scrapling with security checks and retries."""
        async with self.semaphore:
            # SSRF check
            try:
                norm_url, resolved_ip, hostname = validate_and_resolve_url(url)
            except SecurityValidationError as e:
                self.warnings.append(f"Security block for {url}: {e}")
                return None

            max_retries = 2
            backoff = 1.0

            for attempt in range(max_retries + 1):
                try:
                    response = await AsyncFetcher.get(
                        norm_url,
                        timeout=settings.REQUEST_TIMEOUT_SECONDS,
                        headers={"User-Agent": settings.USER_AGENT},
                        follow_redirects=True,
                        max_redirects=5
                    )

                    status_code = response.status
                    final_url = response.url or norm_url

                    # Check response size
                    body_bytes = response.body or b""
                    if len(body_bytes) > settings.MAX_RESPONSE_SIZE_BYTES:
                        self.warnings.append(f"Page exceeded maximum size {settings.MAX_RESPONSE_SIZE_BYTES} bytes: {final_url}")
                        return None

                    # SSRF check on final URL after redirects
                    try:
                        validate_and_resolve_url(final_url)
                    except SecurityValidationError as e:
                        self.warnings.append(f"Redirected to prohibited target {final_url}: {e}")
                        return None

                    if status_code >= 400:
                        logger.warning(f"HTTP {status_code} for {norm_url}")
                        if status_code in (429, 502, 503, 504) and attempt < max_retries:
                            await asyncio.sleep(backoff)
                            backoff *= 2
                            continue
                        # Return failed page record for transparency
                        html = response.text or ""
                        return extract_page_content(
                            html=html,
                            requested_url=norm_url,
                            final_url=final_url,
                            http_status=status_code,
                            base_domain=self.base_domain,
                            used_js=False
                        )

                    html = response.text or ""
                    used_js = False

                    # Check if static HTML yielded too little content and fallback to browser is allowed
                    if (
                        settings.ALLOW_BROWSER_FALLBACK
                        and len(html.strip()) < 300
                    ):
                        try:
                            logger.info(f"Static HTML minimal for {norm_url}, attempting DynamicFetcher fallback.")
                            dynamic_res = DynamicFetcher.fetch(norm_url, timeout=settings.REQUEST_TIMEOUT_SECONDS * 1000)
                            if dynamic_res and dynamic_res.text:
                                html = dynamic_res.text
                                used_js = True
                        except Exception as de:
                            logger.debug(f"DynamicFetcher fallback skipped/failed: {de}")

                    page_data = extract_page_content(
                        html=html,
                        requested_url=norm_url,
                        final_url=final_url,
                        http_status=status_code,
                        base_domain=self.base_domain,
                        used_js=used_js
                    )
                    return page_data

                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1} failed for {norm_url}: {e}")
                    if attempt < max_retries:
                        await asyncio.sleep(backoff)
                        backoff *= 2
                    else:
                        self.warnings.append(f"Failed to crawl {norm_url}: {str(e)}")
                        return None

        return None

    async def _notify_progress(self) -> None:
        if self.on_progress:
            try:
                await self.on_progress({
                    "pages_discovered": self.pages_discovered,
                    "pages_attempted": self.pages_attempted,
                    "pages_succeeded": self.pages_succeeded,
                    "pages_skipped": self.pages_skipped,
                    "pages_failed": self.pages_failed,
                })
            except Exception:
                pass
