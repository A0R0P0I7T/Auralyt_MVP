"""Robots.txt parsing, compliance checking, and sitemap directive extraction."""
import logging
from typing import List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser
import httpx
from app.core.config import settings

logger = logging.getLogger(__name__)


class RobotsPolicy:
    def __init__(self, base_url: str, user_agent: str = settings.USER_AGENT):
        self.base_url = base_url
        self.user_agent = user_agent
        self.sitemaps: List[str] = []
        self.crawl_delay: Optional[float] = None
        self.is_accessible = False
        self.error: Optional[str] = None
        self._parser: Optional[RobotFileParser] = None

    async def fetch_and_parse(self, client: Optional[httpx.AsyncClient] = None) -> None:
        """Fetch robots.txt and parse its rules and sitemaps."""
        robots_url = urljoin(self.base_url, "/robots.txt")
        close_client = False
        if client is None:
            client = httpx.AsyncClient(timeout=settings.REQUEST_TIMEOUT_SECONDS, follow_redirects=True)
            close_client = True

        try:
            response = await client.get(
                robots_url,
                headers={"User-Agent": self.user_agent}
            )
            if response.status_code == 200:
                self.is_accessible = True
                content = response.text
                self._parse_content(robots_url, content)
            elif response.status_code in (404, 410):
                # Standard convention: if robots.txt does not exist, everything is permitted
                self.is_accessible = True
                logger.info(f"No robots.txt found at {robots_url} (status {response.status_code}). Permitting all.")
            elif response.status_code in (401, 403):
                self.error = f"robots.txt access restricted (HTTP {response.status_code})"
                logger.warning(f"Robots access restricted at {robots_url}: {response.status_code}")
            else:
                self.error = f"robots.txt returned status {response.status_code}"
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

        # Extract sitemaps and crawl-delay manually from raw text for full reliability
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
                        self.sitemaps.append(val)
                elif key == "crawl-delay":
                    try:
                        self.crawl_delay = float(val)
                    except ValueError:
                        pass

    def is_allowed(self, target_url: str) -> bool:
        """Check if target_url is allowed to be crawled according to robots.txt rules."""
        if self._parser is None:
            # If no parser exists (e.g. 404 or missing), allow by default
            return True
        try:
            return self._parser.can_fetch(self.user_agent, target_url)
        except Exception:
            return True
