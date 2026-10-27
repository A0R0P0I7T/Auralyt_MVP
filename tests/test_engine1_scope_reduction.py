"""Tests for Engine 1 Scope Reduction:
Verifies that Scrapling is limited strictly to:
1. Checking whether a submitted website is reachable and returning a meaningful website status.
2. Gathering minimal homepage information to classify the business into a useful category.
3. No deep crawling, sitemap parsing, or catalog harvesting.
4. Distinguishing reachability, bot protection, DNS failures, timeouts, and HTTP errors.
5. Preserving strict SSRF and redirect defenses.
"""
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from app.crawler.engine import ScraplingCrawler, WebsiteVerificationResult
from app.crawler.security import SecurityValidationError


class MockResponse:
    def __init__(self, status: int, body: bytes = b"", headers: dict = None, text: str = ""):
        self.status = status
        self.status_code = status
        self.body = body
        self.headers = headers or {}
        self.text = text
        self.encoding = "utf-8"


@pytest.mark.asyncio
async def test_scrapling_verifies_reachable_homepage_with_minimal_signals():
    """Verify that Scrapling extracts minimal homepage classification signals and does not crawl subpages."""
    html_content = """<!DOCTYPE html>
    <html lang="en">
    <head>
        <title>SalesPipeline | Modern CRM and Lead Management</title>
        <meta name="description" content="AI-powered CRM and outbound sales platform to help sales teams track deals and grow pipeline.">
        <script type="application/ld+json">
        {
            "@context": "https://schema.org",
            "@type": "SoftwareApplication",
            "name": "SalesPipeline",
            "applicationCategory": "BusinessApplication",
            "description": "Sales CRM and pipeline automation tool."
        }
        </script>
    </head>
    <body>
        <h1>Close More Deals with Intelligent CRM</h1>
        <p>Manage customer relationships, track outbound outreach, and automate your sales pipeline in one intuitive workspace.</p>
        <a href="/pricing">Pricing</a>
        <a href="/blog/case-study">Blog</a>
        <a href="/docs/api">Documentation</a>
    </body>
    </html>"""

    crawler = ScraplingCrawler("https://salespipeline.io", homepage_only=True)

    with patch("scrapling.AsyncFetcher.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = MockResponse(
            status=200,
            body=html_content.encode("utf-8"),
            text=html_content,
            headers={"content-type": "text/html; charset=utf-8"}
        )

        result: WebsiteVerificationResult = await crawler.verify_and_classify_homepage()

        assert result.status == "reachable"
        assert result.http_status == 200
        assert "SalesPipeline" in (result.title or "")
        assert "AI-powered CRM" in (result.meta_description or "")
        assert len(result.structured_data) > 0
        assert result.structured_data[0].get("name") == "SalesPipeline"
        assert result.structured_data[0].get("applicationCategory") == "BusinessApplication"
        assert len(result.headings.get("h1", [])) > 0
        assert "Close More Deals" in result.headings["h1"][0]
        # Bounded text extraction
        assert len(result.extracted_text) <= 5000
        # No subpages crawled
        assert crawler.pages_attempted == 1
        assert crawler.pages_discovered == 1
        assert len(crawler.crawled_pages) == 1
        # Verification classification result exists
        assert result.is_usable is True
        assert result.classification is not None
        assert result.classification.get("primary_category") is not None


@pytest.mark.asyncio
async def test_scrapling_handles_dns_failure_distinctly():
    """Verify that DNS resolution failure returns status 'dns_failure' rather than generic error."""
    crawler = ScraplingCrawler("https://nonexistent-domain-xyz-12345.com", homepage_only=True)

    with patch("app.crawler.engine.validate_and_resolve_url", side_effect=SecurityValidationError("DNS resolution failed")):
        result = await crawler.verify_and_classify_homepage()
        assert result.status == "dns_failure"
        assert result.http_status is None
        assert result.is_usable is False
        assert "DNS resolution failed" in (result.error_details or "")


@pytest.mark.asyncio
async def test_scrapling_handles_timeout_distinctly():
    """Verify that connection/read timeout returns status 'timeout'."""
    crawler = ScraplingCrawler("https://timeout-site.com", homepage_only=True)

    with patch("app.crawler.engine.validate_and_resolve_url", return_value=("https://timeout-site.com", "93.184.216.34", "timeout-site.com")):
        with patch("scrapling.AsyncFetcher.get", side_effect=TimeoutError("Request timed out after 10s")):
            result = await crawler.verify_and_classify_homepage()
            assert result.status == "timeout"
            assert result.is_usable is False
            assert "timed out" in (result.error_details or "").lower()


@pytest.mark.asyncio
async def test_scrapling_handles_blocked_bot_protection_distinctly():
    """Verify that 403/401/429 Cloudflare/bot protection returns status 'blocked'."""
    crawler = ScraplingCrawler("https://protected-site.com", homepage_only=True)

    with patch("app.crawler.engine.validate_and_resolve_url", return_value=("https://protected-site.com", "93.184.216.34", "protected-site.com")):
        with patch("scrapling.AsyncFetcher.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = MockResponse(
                status=403,
                body=b"Attention Required! | Cloudflare",
                text="Attention Required! | Cloudflare"
            )
            result = await crawler.verify_and_classify_homepage()
            assert result.status == "blocked"
            assert result.http_status == 403
            assert result.is_usable is False


@pytest.mark.asyncio
async def test_scrapling_handles_http_404_not_found():
    """Verify that HTTP 404 returns status 'not_found'."""
    crawler = ScraplingCrawler("https://broken-site.com", homepage_only=True)

    with patch("app.crawler.engine.validate_and_resolve_url", return_value=("https://broken-site.com", "93.184.216.34", "broken-site.com")):
        with patch("scrapling.AsyncFetcher.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = MockResponse(
                status=404,
                body=b"404 Not Found",
                text="404 Not Found"
            )
            result = await crawler.verify_and_classify_homepage()
            assert result.status == "not_found"
            assert result.http_status == 404
            assert result.is_usable is False


@pytest.mark.asyncio
async def test_scrapling_handles_http_500_server_error():
    """Verify that HTTP 500 returns status 'server_error'."""
    crawler = ScraplingCrawler("https://error-site.com", homepage_only=True)

    with patch("app.crawler.engine.validate_and_resolve_url", return_value=("https://error-site.com", "93.184.216.34", "error-site.com")):
        with patch("scrapling.AsyncFetcher.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = MockResponse(
                status=500,
                body=b"500 Internal Server Error",
                text="500 Internal Server Error"
            )
            result = await crawler.verify_and_classify_homepage()
            assert result.status == "server_error"
            assert result.http_status == 500
            assert result.is_usable is False


@pytest.mark.asyncio
async def test_scrapling_homepage_only_ignores_sitemaps():
    """Verify that in homepage_only mode, sitemaps are completely bypassed."""
    crawler = ScraplingCrawler("https://example.com", homepage_only=True)

    with patch("app.crawler.sitemap.SitemapDiscoverer.discover", new_callable=AsyncMock) as mock_sitemap:
        with patch("scrapling.AsyncFetcher.get", new_callable=AsyncMock) as mock_get:
            mock_get.return_value = MockResponse(
                status=200,
                body=b"<html><head><title>Minimal</title></head><body>Hello</body></html>",
                text="<html><head><title>Minimal</title></head><body>Hello</body></html>"
            )
            await crawler.verify_and_classify_homepage()
            # Sitemap discover must NOT have been called
            mock_sitemap.assert_not_called()
            assert crawler.pages_attempted == 1
