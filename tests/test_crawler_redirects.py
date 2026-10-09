import pytest
from unittest.mock import patch, AsyncMock
from app.crawler.engine import ScraplingCrawler


class MockRedirectResponse:
    def __init__(self, status: int, headers: dict, body: bytes = b"", text: str = ""):
        self.status = status
        self.headers = headers
        self.body = body
        self.text = text


@pytest.mark.asyncio
async def test_crawler_blocks_redirect_to_private_ip():
    crawler = ScraplingCrawler("https://example.com", page_limit=5)

    # First request returns 302 pointing to 169.254.169.254
    redirect_resp = MockRedirectResponse(
        status=302,
        headers={"location": "http://169.254.169.254/latest/meta-data/"}
    )

    with patch("scrapling.AsyncFetcher.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = redirect_resp
        res = await crawler._fetch_and_extract("https://example.com/test")

        # Must be blocked and return None
        assert res is None
        # Blocked either by out of domain scope or by security block
        assert any("out of domain scope" in w or "Security block" in w for w in crawler.warnings)


@pytest.mark.asyncio
async def test_crawler_blocks_redirect_out_of_scope():
    crawler = ScraplingCrawler("https://example.com", page_limit=5)

    # First request returns 302 pointing to an external domain
    redirect_resp = MockRedirectResponse(
        status=302,
        headers={"location": "https://malicious-external-site.com/exploit"}
    )

    with patch("scrapling.AsyncFetcher.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value = redirect_resp
        res = await crawler._fetch_and_extract("https://example.com/test")

        assert res is None
        assert any("out of domain scope" in w for w in crawler.warnings)


@pytest.mark.asyncio
async def test_crawler_detects_redirect_loop():
    crawler = ScraplingCrawler("https://example.com", page_limit=5)

    # Redirect loop: A -> B -> A
    def redirect_side_effect(url, **kwargs):
        if "loop-a" in url:
            return MockRedirectResponse(302, {"location": "/loop-b"})
        elif "loop-b" in url:
            return MockRedirectResponse(302, {"location": "/loop-a"})
        return MockRedirectResponse(200, {}, body=b"OK", text="OK")

    with patch("scrapling.AsyncFetcher.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = redirect_side_effect
        res = await crawler._fetch_and_extract("https://example.com/loop-a")

        assert res is None
        assert any("Redirect loop detected" in w for w in crawler.warnings)


@pytest.mark.asyncio
async def test_crawler_allows_safe_in_scope_redirect():
    crawler = ScraplingCrawler("https://example.com", page_limit=5)

    # Safe redirect: /home -> /about (200 OK)
    def safe_redirect(url, **kwargs):
        if url == "https://example.com/home":
            return MockRedirectResponse(301, {"location": "/about"})
        return MockRedirectResponse(
            200,
            {},
            body=b"<html><body><h1>About Us</h1><p>Welcome</p></body></html>",
            text="<html><body><h1>About Us</h1><p>Welcome</p></body></html>"
        )

    with patch("scrapling.AsyncFetcher.get", new_callable=AsyncMock) as mock_get:
        mock_get.side_effect = safe_redirect
        res = await crawler._fetch_and_extract("https://example.com/home")

        assert res is not None
        assert res["http_status"] == 200
        assert res["final_url"] == "https://example.com/about"
        assert "About Us" in res["headings"]["h1"]
