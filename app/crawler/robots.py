"""Robots.txt parsing, compliance checking, and sitemap directive extraction
with hop-by-hop SSRF validation and redirect protection.
"""
import logging
from typing import List, Optional
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import httpx
from app.core.config import settings
from app.crawler.security import (
    validate_and_resolve_url,
    normalize_url,
    is_same_domain_or_subdomain,
    SecurityValidationError
)

logger = logging.getLogger(__name__)


class RobotsPolicy:
    def __init__(self, base_url: str, user_agent: str = settings.USER_AGENT):
        self.base_url = normalize_url(base_url)
        self.base_domain = urlparse(self.base_url).hostname or ""
        self.user_agent = user_agent
        self.sitemaps: List[str] = []
        self.crawl_delay: Optional[float] = None
        self.is_accessible = False
        self.error: Optional[str] = None
        self._parser: Optional[RobotFileParser] = None

    async def fetch_and_parse(self, client: Optional[httpx.AsyncClient] = None) -> None:
        """Fetch robots.txt with hop-by-hop SSRF validation."""
        start_url = urljoin(self.base_url, "/robots.txt")
        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS)
            close_client = True

        try:
            current_url = start_url
            max_redirects = 3
            redirect_count = 0
            visited = {current_url}
            final_response = None

            while True:
                # SSRF validation on current URL
                try:
                    norm_url, _, _ = validate_and_resolve_url(current_url)
                except SecurityValidationError as se:
                    self.error = f"robots.txt security blocked on {current_url}: {se}"
                    return

                if not is_same_domain_or_subdomain(norm_url, self.base_domain):
                    self.error = f"robots.txt redirected out of domain scope: {norm_url}"
                    return

                response = await client.get(
                    norm_url,
                    headers={"User-Agent": self.user_agent},
                    follow_redirects=False
                )

                if response.status_code in (301, 302, 303, 307, 308):
                    redirect_count += 1
                    if redirect_count > max_redirects:
                        self.error = "robots.txt exceeded maximum redirects."
                        return

                    loc = response.headers.get("location") or response.headers.get("Location")
                    if not loc:
                        self.error = "robots.txt redirect missing Location header."
                        return

                    next_url = normalize_url(urljoin(current_url, loc))
                    if next_url in visited:
                        self.error = "robots.txt redirect loop detected."
                        return

                    visited.add(next_url)
                    current_url = next_url
                    continue

                final_response = response
                break

            if final_response.status_code == 200:
                self.is_accessible = True
                content = final_response.text
                self._parse_content(current_url, content)
            elif final_response.status_code in (404, 410):
                self.is_accessible = True
                logger.info(f"No robots.txt found at {start_url} (HTTP {final_response.status_code}). Permitting all.")
            elif final_response.status_code in (401, 403):
                self.error = f"robots.txt access restricted (HTTP {final_response.status_code})"
                logger.warning(f"Robots access restricted at {start_url}: {final_response.status_code}")
            else:
                self.error = f"robots.txt returned status {final_response.status_code}"

        except Exception as e:
            self.error = f"Failed to fetch robots.txt: {str(e)}"
            logger.warning(f"Error fetching robots.txt for {self.base_url}: {e}")
        finally:
            if close_client:
                await client.aclose()

    def _parse_content(self, robots_url: str, text: str) -> None:
        self._parser = RobotFileParser()
        self._parser.set_url(robots_url)
        self._parser.parse(text.splitlines())

        # Extract sitemaps and crawl-delay manually from raw text
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if ":" in line:
                key, val = line.split(":", 1)
                key = key.strip().lower()
                val = val.strip()
                if key == "sitemap":
                    if val and val not in self.sitemaps:
                        try:
                            # Validate sitemap candidate before adding
                            validate_and_resolve_url(val)
                            norm_val = normalize_url(val)
                            if is_same_domain_or_subdomain(norm_val, self.base_domain):
                                self.sitemaps.append(norm_val)
                        except Exception:
                            logger.warning(f"Ignored unsafe sitemap directive in robots.txt: {val}")
                elif key == "crawl-delay":
                    try:
                        self.crawl_delay = float(val)
                    except ValueError:
                        pass

    def is_allowed(self, target_url: str) -> bool:
        """Check if target_url is allowed to be crawled according to robots.txt rules."""
        if self._parser is None:
            return True
        try:
            return self._parser.can_fetch(self.user_agent, target_url)
        except Exception:
            return True
