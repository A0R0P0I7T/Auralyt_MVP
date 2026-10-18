"""Scrapling-powered crawler engine for Auralyt MVP — Engine 1.
Implements polite, concurrency-bounded, prioritized crawling with robots compliance,
strict hop-by-hop SSRF defense, redirect loop limits, and sandboxed browser rendering.
"""
import asyncio
import logging
import re
import time
from typing import Dict, List, Set, Optional, Callable, Awaitable, Any
from urllib.parse import urlparse, urljoin
from app.core.config import settings
from app.crawler.security import (
    validate_and_resolve_url,
    normalize_url,
    is_same_domain_or_subdomain,
    SecurityValidationError,
    BLOCKED_HOSTNAMES
)
from app.crawler.transport import safe_fetch_scrapling, safe_fetch_dynamic
from app.crawler.robots import RobotsPolicy
from app.crawler.sitemap import SitemapDiscoverer, score_url_priority
from app.extractor.page_extractor import extract_page_content

logger = logging.getLogger(__name__)


def safe_browser_setup(page) -> None:
    """
    Playwright page setup handler for sandboxing browser execution.
    Intercepts and blocks any subresource requests to prohibited or private networks,
    as well as WebSockets, media streams, and non-HTTP protocols.
    """
    def intercept_route(route, request):
        req_url = request.url
        resource_type = getattr(request, "resource_type", "")
        # Block unnecessary or dangerous resource types
        if resource_type in ("websocket", "media"):
            route.abort("blockedbyclient")
            return

        if req_url.startswith(("ws://", "wss://", "file://", "ftp://", "data:")):
            route.abort("blockedbyclient")
            return

        try:
            # Validate every subresource request against SSRF policies
            validate_and_resolve_url(req_url)
            route.continue_()
        except SecurityValidationError as se:
            logger.warning(f"Aborted unsafe browser subresource: {req_url} ({se})")
            route.abort("blockedbyclient")
        except Exception:
            route.continue_()

    try:
        page.route("**/*", intercept_route)
    except Exception as e:
        logger.debug(f"Could not attach route interceptor: {e}")


def extract_html_from_response(response) -> str:
    """
    Safely extract decoded HTML string from Scrapling Response or test mock response.
    Handles Scrapling toolbelt Response (body bytes and encoding), html_content,
    and fallback text strings.
    """
    body = getattr(response, "body", None)
    if isinstance(body, bytes) and body:
        encoding = getattr(response, "encoding", "utf-8") or "utf-8"
        try:
            return body.decode(encoding, errors="replace")
        except Exception:
            return body.decode("utf-8", errors="replace")

    html_content = getattr(response, "html_content", None)
    if isinstance(html_content, str) and html_content:
        return html_content

    text = getattr(response, "text", None)
    if text:
        text_str = str(text)
        if text_str.strip():
            return text_str

    return ""


class CrawlItem:
    def __init__(self, url: str, depth: int = 0, priority: int = 2):
        self.url = url
        self.depth = depth
        self.priority = priority


class ScraplingCrawler:
    def __init__(
        self,
        base_url: str,
        page_limit: int = 25,
        max_depth: int = 3,
        on_progress: Optional[Callable[[Dict[str, int]], Awaitable[None]]] = None
    ):
        self.base_url = normalize_url(base_url)
        self.base_domain = urlparse(self.base_url).hostname or ""
        self.page_limit = min(page_limit, settings.HARD_MAX_PAGE_LIMIT)
        self.max_depth = min(max_depth, settings.CRAWL_MAX_DEPTH)
        self.on_progress = on_progress

        # State
        self.visited_urls: Set[str] = set()
        self.canonical_map: Dict[str, str] = {}
        self.crawled_pages: List[Dict] = []
        self.warnings: List[str] = []
        self.errors: List[str] = []

        # Budgets & Metrics
        self.start_time = time.time()
        self.deadline = self.start_time + settings.CRAWL_RUN_TIMEOUT_SECONDS
        self.aggregate_bytes_processed = 0
        self.category_counts: Dict[str, int] = {}
        self.section_counts: Dict[str, int] = {}
        self.skip_reasons: Dict[str, int] = {}

        self.pages_discovered = 0
        self.pages_attempted = 0
        self.pages_succeeded = 0
        self.pages_skipped = 0
        self.pages_failed = 0

        self.robots_policy = RobotsPolicy(self.base_url)
        self.semaphore = asyncio.Semaphore(settings.PER_HOST_CONCURRENCY)

    def _get_section_prefix(self, url: str) -> str:
        """Extract primary section prefix (e.g. docs, blog, tools), stripping any leading locale segment."""
        path = (urlparse(url).path or "").strip("/")
        if not path:
            return ""
        segments = [s.lower() for s in path.split("/") if s]
        if not segments:
            return ""
        # Check if first segment is a locale (e.g. en, en-us, en_us, fr, fr-fr, etc.)
        if re.match(r"^[a-z]{2}(?:[-_][a-z]{2})?$", segments[0]) and len(segments) > 1:
            return segments[1]
        return segments[0]

    def get_crawl_summary(self) -> Dict[str, Any]:
        """Produce structured canonical crawl budget & performance summary."""
        elapsed = round(time.time() - self.start_time, 2)
        useful_count = sum(1 for p in self.crawled_pages if len(p.get("extracted_text", "").strip()) > 50)
        return {
            "page_limit": self.page_limit,
            "max_depth": self.max_depth,
            "pages_discovered": self.pages_discovered,
            "pages_selected": self.pages_attempted,
            "pages_fetched": self.pages_succeeded + self.pages_failed,
            "pages_succeeded": self.pages_succeeded,
            "pages_skipped": self.pages_skipped,
            "pages_failed": self.pages_failed,
            "skip_reasons": self.skip_reasons,
            "aggregate_bytes_processed": self.aggregate_bytes_processed,
            "duration_seconds": elapsed,
            "useful_pages_produced": useful_count,
            "category_breakdown": self.category_counts,
            "category_quotas": settings.CRAWL_CATEGORY_QUOTAS,
            "budget_limits": {
                "max_pages": self.page_limit,
                "max_depth": self.max_depth,
                "max_pages_per_domain": settings.CRAWL_MAX_PAGES_PER_DOMAIN,
                "max_pages_per_section": settings.CRAWL_MAX_PAGES_PER_SECTION,
                "concurrency": settings.CRAWL_MAX_CONCURRENCY,
                "request_timeout_seconds": settings.REQUEST_TIMEOUT_SECONDS,
                "run_timeout_seconds": settings.CRAWL_RUN_TIMEOUT_SECONDS,
                "max_response_size_bytes": settings.MAX_RESPONSE_SIZE_BYTES,
                "max_decompressed_bytes": settings.CRAWL_MAX_DECOMPRESSED_BYTES,
                "max_aggregate_bytes": settings.CRAWL_MAX_AGGREGATE_BYTES,
                "max_retries": settings.CRAWL_MAX_RETRIES,
                "max_sitemap_entries": settings.CRAWL_MAX_SITEMAP_ENTRIES,
            },
            "deadline_exceeded": time.time() > self.deadline,
        }

    async def run(self) -> List[Dict]:
        """Execute the complete budget-bounded crawl run."""
        logger.info(f"Starting Scrapling crawl on {self.base_url} (budget: {self.page_limit} pages, depth: {self.max_depth})")

        # 1. Fetch robots.txt
        await self.robots_policy.fetch_and_parse()
        if self.robots_policy.error:
            self.warnings.append(f"Robots.txt notice: {self.robots_policy.error}")

        # 2. Discover sitemap URLs within budget
        sitemap_discoverer = SitemapDiscoverer(
            self.base_url,
            self.base_domain,
            max_urls=settings.CRAWL_MAX_SITEMAP_ENTRIES
        )
        sitemap_urls = await sitemap_discoverer.discover(seed_sitemaps=self.robots_policy.sitemaps)
        self.warnings.extend(sitemap_discoverer.warnings)

        # 3. Initialize Queue: Homepage first, then prioritized sitemap URLs with pre-scheduling deduplication
        queue: List[CrawlItem] = []
        scheduled_urls: Set[str] = {self.base_url}
        queue.append(CrawlItem(url=self.base_url, depth=0, priority=0))

        # Sort and select sitemaps honoring section quotas
        sorted_sitemaps = sorted(sitemap_urls, key=score_url_priority)
        section_sitemap_counts: Dict[str, int] = {}
        for sm_url in sorted_sitemaps:
            norm_sm_url = normalize_url(sm_url)
            if norm_sm_url in scheduled_urls:
                continue
            sec = self._get_section_prefix(norm_sm_url)
            prio = score_url_priority(norm_sm_url)
            # Low-priority sections (e.g. blog, changelog, legal) capped strictly in initial queue
            if prio >= 3 and section_sitemap_counts.get(sec, 0) >= settings.CRAWL_MAX_PAGES_PER_SECTION:
                self.skip_reasons["section-quota"] = self.skip_reasons.get("section-quota", 0) + 1
                continue
            section_sitemap_counts[sec] = section_sitemap_counts.get(sec, 0) + 1
            scheduled_urls.add(norm_sm_url)
            queue.append(CrawlItem(url=norm_sm_url, depth=1, priority=prio))
            if len(queue) >= self.page_limit * 2:
                break

        self.pages_discovered = len(queue)
        await self._notify_progress()

        # 4. Budget-Bounded Crawl Loop
        while queue and len(self.crawled_pages) < self.page_limit:
            # Check run deadline
            if time.time() > self.deadline:
                self.warnings.append("Crawl stopped: Run deadline exceeded (timeout budget)")
                self.skip_reasons["run-deadline-exceeded"] = self.skip_reasons.get("run-deadline-exceeded", 0) + len(queue)
                break

            # Check aggregate content budget
            if self.aggregate_bytes_processed >= settings.CRAWL_MAX_AGGREGATE_BYTES:
                self.warnings.append("Crawl stopped: Aggregate content size budget reached")
                self.skip_reasons["aggregate-size-limit"] = self.skip_reasons.get("aggregate-size-limit", 0) + 1
                break

            # Sort queue by priority (lowest number = highest priority), then depth
            queue.sort(key=lambda item: (item.priority, item.depth))
            current_item = queue.pop(0)

            url = current_item.url
            if url in self.visited_urls:
                continue

            # Check section quota before fetching
            sec = self._get_section_prefix(url)
            if sec and self.section_counts.get(sec, 0) >= settings.CRAWL_MAX_PAGES_PER_SECTION and current_item.priority > 0:
                self.pages_skipped += 1
                self.skip_reasons["section-quota"] = self.skip_reasons.get("section-quota", 0) + 1
                self.visited_urls.add(url)
                continue

            # Check robots permission
            if not self.robots_policy.is_allowed(url):
                self.pages_skipped += 1
                self.skip_reasons["robots-disallowed"] = self.skip_reasons.get("robots-disallowed", 0) + 1
                self.warnings.append(f"Skipped {url}: Disallowed by robots.txt")
                self.visited_urls.add(url)
                continue

            self.visited_urls.add(url)
            self.pages_attempted += 1

            # Fetch and process page with hop-by-hop validation
            page_data = await self._fetch_and_extract(url)

            if page_data:
                canonical = page_data.get("canonical_url")
                if canonical and canonical in self.canonical_map:
                    # Duplicate canonical page already crawled
                    self.pages_skipped += 1
                    self.skip_reasons["duplicate-canonical-url"] = self.skip_reasons.get("duplicate-canonical-url", 0) + 1
                    continue

                page_type = page_data.get("page_type", "other")
                max_for_cat = settings.CRAWL_CATEGORY_QUOTAS.get(page_type, 4)

                # Check category quota (homepage and pricing are never skipped for category quota)
                if page_type not in ("homepage", "pricing") and self.category_counts.get(page_type, 0) >= max_for_cat:
                    self.pages_skipped += 1
                    self.skip_reasons["category-quota"] = self.skip_reasons.get("category-quota", 0) + 1
                    continue

                if canonical:
                    self.canonical_map[canonical] = url

                self.category_counts[page_type] = self.category_counts.get(page_type, 0) + 1
                if sec:
                    self.section_counts[sec] = self.section_counts.get(sec, 0) + 1

                self.crawled_pages.append(page_data)
                self.pages_succeeded += 1

                # Discover new internal links if depth allows
                if current_item.depth < self.max_depth:
                    candidate_links = sorted(page_data.get("internal_links", []), key=score_url_priority)
                    for link in candidate_links:
                        link_norm = normalize_url(link)
                        link_prio = score_url_priority(link_norm)
                        link_sec = self._get_section_prefix(link_norm)
                        prio = link_prio if (current_item.depth == 0 and link_prio <= 1) else link_prio + 1

                        # Skip links if section quota is already exhausted
                        if link_sec and self.section_counts.get(link_sec, 0) >= settings.CRAWL_MAX_PAGES_PER_SECTION and link_prio > 0:
                            continue

                        if (
                            is_same_domain_or_subdomain(link_norm, self.base_domain)
                            and link_norm not in self.visited_urls
                            and link_norm not in scheduled_urls
                            and (len(self.crawled_pages) + len(queue) < self.page_limit * 3 or link_prio <= 1)
                        ):
                            scheduled_urls.add(link_norm)
                            queue.append(CrawlItem(
                                url=link_norm,
                                depth=current_item.depth + 1,
                                priority=prio
                            ))
                            self.pages_discovered += 1
            else:
                self.pages_failed += 1

            await self._notify_progress()
            # Politeness delay
            delay = self.robots_policy.crawl_delay or settings.PER_HOST_DELAY_SECONDS
            await asyncio.sleep(delay)

        # Record remaining items in queue if budget exhausted
        if len(self.crawled_pages) >= self.page_limit and queue:
            self.skip_reasons["page-budget-exhausted"] = self.skip_reasons.get("page-budget-exhausted", 0) + len(queue)

        logger.info(f"Crawl completed. Succeeded: {self.pages_succeeded}, Skipped: {self.pages_skipped}, Failed: {self.pages_failed}")
        return self.crawled_pages

    async def _fetch_and_extract(self, start_url: str) -> Optional[Dict]:
        """
        Fetch a URL with hop-by-hop redirect SSRF validation, bounded retries,
        response size limits, and sandboxed browser fallback.
        """
        async with self.semaphore:
            max_retries = settings.CRAWL_MAX_RETRIES
            backoff = settings.CRAWL_RETRY_BACKOFF_SECONDS

            for attempt in range(max_retries + 1):
                try:
                    current_url = start_url
                    redirect_count = 0
                    max_redirects = 5
                    visited_redirect_chain = {current_url}
                    final_response = None

                    # Hop-by-hop redirect loop with SSRF check at each step
                    while True:
                        try:
                            norm_target, resolved_ip, hostname = validate_and_resolve_url(current_url)
                        except SecurityValidationError as se:
                            self.warnings.append(f"Security block on {current_url}: {se}")
                            return None

                        if not is_same_domain_or_subdomain(norm_target, self.base_domain):
                            self.warnings.append(f"Redirect target out of domain scope: {norm_target}")
                            return None

                        # Make request through centralized safe transport
                        response = await safe_fetch_scrapling(
                            norm_target,
                            timeout=settings.REQUEST_TIMEOUT_SECONDS,
                            headers={"User-Agent": settings.USER_AGENT}
                        )

                        # Check for 3xx redirects
                        if response.status in (301, 302, 303, 307, 308):
                            redirect_count += 1
                            if redirect_count > max_redirects:
                                self.warnings.append(f"Exceeded max redirects ({max_redirects}) starting from {start_url}")
                                return None

                            location = response.headers.get("location") or response.headers.get("Location")
                            if not location:
                                self.warnings.append(f"HTTP {response.status} redirect without Location header on {current_url}")
                                return None

                            # Resolve relative Location header
                            next_url = normalize_url(urljoin(current_url, location))
                            if not is_same_domain_or_subdomain(next_url, self.base_domain):
                                self.warnings.append(f"Redirect target out of domain scope: {next_url}")
                                return None

                            if next_url in visited_redirect_chain:
                                self.warnings.append(f"Redirect loop detected: {next_url}")
                                return None

                            visited_redirect_chain.add(next_url)
                            current_url = next_url
                            continue

                        # Not a redirect
                        final_response = response
                        break

                    if final_response is None:
                        return None

                    status_code = final_response.status
                    final_url = current_url

                    # Check response size
                    body_bytes = final_response.body or b""
                    self.aggregate_bytes_processed += len(body_bytes)
                    if len(body_bytes) > settings.MAX_RESPONSE_SIZE_BYTES:
                        self.warnings.append(f"Page exceeded maximum size {settings.MAX_RESPONSE_SIZE_BYTES} bytes: {final_url}")
                        self.skip_reasons["response-size-limit"] = self.skip_reasons.get("response-size-limit", 0) + 1
                        return None

                    if status_code >= 400:
                        logger.warning(f"HTTP {status_code} for {final_url}")
                        if status_code in (429, 502, 503, 504) and attempt < max_retries:
                            await asyncio.sleep(backoff)
                            backoff *= 2
                            continue
                        html = extract_html_from_response(final_response)
                        return extract_page_content(
                            html=html,
                            requested_url=start_url,
                            final_url=final_url,
                            http_status=status_code,
                            base_domain=self.base_domain,
                            used_js=False
                        )

                    html = extract_html_from_response(final_response)
                    # Enforce decompressed text limit
                    decompressed_len = len(html.encode("utf-8", errors="ignore"))
                    if decompressed_len > settings.MAX_RESPONSE_SIZE_BYTES:
                        self.warnings.append(
                            f"Decompressed page content exceeded maximum size ({settings.MAX_RESPONSE_SIZE_BYTES} bytes): {final_url}"
                        )
                        self.skip_reasons["response-size-limit"] = self.skip_reasons.get("response-size-limit", 0) + 1
                        return None

                    used_js = False

                    # Check if static HTML yielded too little content and fallback to browser is allowed
                    if (
                        settings.ALLOW_BROWSER_FALLBACK
                        and len(html.strip()) < 300
                    ):
                        try:
                            logger.info(f"Static HTML minimal for {final_url}, attempting sandboxed DynamicFetcher.")
                            dynamic_res = safe_fetch_dynamic(
                                final_url,
                                timeout_ms=settings.REQUEST_TIMEOUT_SECONDS * 1000,
                                page_setup=safe_browser_setup
                            )
                            if dynamic_res:
                                rendered_text = extract_html_from_response(dynamic_res)
                                if rendered_text and len(rendered_text.encode("utf-8", errors="ignore")) <= settings.MAX_RESPONSE_SIZE_BYTES:
                                    html = rendered_text
                                    used_js = True
                                elif len(rendered_text.encode("utf-8", errors="ignore")) > settings.MAX_RESPONSE_SIZE_BYTES:
                                    self.warnings.append(f"Dynamic render exceeded maximum size limit for {final_url}")
                        except Exception as de:
                            logger.debug(f"DynamicFetcher fallback skipped/failed: {de}")

                    page_data = extract_page_content(
                        html=html,
                        requested_url=start_url,
                        final_url=final_url,
                        http_status=status_code,
                        base_domain=self.base_domain,
                        used_js=used_js
                    )
                    return page_data

                except Exception as e:
                    logger.warning(f"Attempt {attempt + 1} failed for {start_url}: {e}")
                    if attempt < max_retries:
                        await asyncio.sleep(backoff)
                        backoff *= 2
                    else:
                        self.warnings.append(f"Failed to crawl {start_url}: {str(e)}")
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
