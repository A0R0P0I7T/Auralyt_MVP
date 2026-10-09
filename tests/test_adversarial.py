"""Targeted Adversarial Security Verification Tests for Auralyt MVP Engine 1.
Tests address validation, redirect hardening, DNS resolution edge cases,
decompression bombs, size limits, suffix confusion, and information leakage redaction.
"""
import io
import gzip
import pytest
import socket
from unittest.mock import patch, MagicMock
from httpx import AsyncClient, Response, Request
from app.core.config import settings
from app.crawler.security import (
    validate_and_resolve_url,
    normalize_url,
    is_same_domain_or_subdomain,
    sanitize_error_summary,
    SecurityValidationError,
    BLOCKED_HOSTNAMES
)
from app.crawler.robots import RobotsPolicy
from app.crawler.sitemap import SitemapDiscoverer
from app.crawler.engine import ScraplingCrawler


def test_trailing_dot_hostname_blocked():
    """Verify trailing dot in blocked hostnames does not bypass blacklist."""
    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("http://metadata.google.internal./")
    assert "prohibited" in str(exc.value).lower()

    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("http://localhost./")
    assert "prohibited" in str(exc.value).lower() or "blocked" in str(exc.value).lower()


def test_userinfo_stripped_in_normalize_url():
    """Verify credentials in URLs are stripped during normalization."""
    url = "https://admin:SuperSecretPass@example.com/dashboard?token_param=123"
    norm = normalize_url(url)
    assert "admin" not in norm
    assert "SuperSecretPass" not in norm
    assert "@" not in norm
    assert norm == "https://example.com/dashboard?token_param=123"


def test_mixed_public_and_private_dns_fails_closed():
    """Verify DNS returning both public and private IP fails closed."""
    # Simulate getaddrinfo returning public IP (93.184.216.34) AND private IP (10.0.0.1)
    fake_addrinfo = [
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
        (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.1", 0)),
    ]
    with patch("socket.getaddrinfo", return_value=fake_addrinfo):
        with pytest.raises(SecurityValidationError) as exc:
            validate_and_resolve_url("https://dual-homed-evil.example.com/")
        assert "prohibited ip '10.0.0.1'" in str(exc.value).lower()


def test_domain_scope_suffix_confusion():
    """Verify suffix confusion attacks are completely blocked."""
    assert not is_same_domain_or_subdomain("https://example.com.attacker.com/page", "example.com")
    assert not is_same_domain_or_subdomain("https://attackerexample.com/page", "example.com")
    assert not is_same_domain_or_subdomain("https://example.com-evil.org/page", "example.com")
    assert not is_same_domain_or_subdomain("https://evil.com/page", "")
    assert not is_same_domain_or_subdomain("", "example.com")

    # Valid trailing dots match safely
    assert is_same_domain_or_subdomain("https://example.com./page", "example.com")
    assert is_same_domain_or_subdomain("https://example.com/page", "example.com.")


def test_sanitize_error_summary_comprehensive_leakage():
    """Verify all varieties of sensitive tokens, passwords, cookies, and paths are redacted."""
    # 1. URL with username + password
    e1 = "Failed to connect to postgresql+asyncpg://app_user:DbPass12345@10.0.1.5:5432/auralyt_db"
    s1 = sanitize_error_summary(e1)
    assert "DbPass12345" not in s1
    assert "app_user" not in s1
    assert "***@" in s1

    # 2. URL with token-only userinfo
    e2 = "Failed request to https://ghp_9876543210ABCDEF@api.github.com/repo"
    s2 = sanitize_error_summary(e2)
    assert "ghp_9876543210ABCDEF" not in s2
    assert "***@" in s2

    # 3. Bearer authorization tokens
    e3 = "HTTP 401: Authorization: Bearer eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.secretpayload"
    s3 = sanitize_error_summary(e3)
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in s3
    assert "Bearer ***" in s3

    # 4. Sensitive query parameters
    e4 = "Timeout requesting https://api.service.com/data?api_key=TopSecretKey999&other=1"
    s4 = sanitize_error_summary(e4)
    assert "TopSecretKey999" not in s4
    assert "api_key=***" in s4

    # 5. Cookie header
    e5 = "Headers logged: Cookie: session_id=SuperSecretSessionToken999; theme=dark"
    s5 = sanitize_error_summary(e5)
    assert "SuperSecretSessionToken999" not in s5
    assert "Cookie: session_id=***" in s5

    # 6. Linux application & system paths
    e6 = "Crash in /app/backend/core/database.py and /usr/local/lib/python3.10/site-packages/engine.py"
    s6 = sanitize_error_summary(e6)
    assert "/app/backend" not in s6
    assert "/usr/local/lib" not in s6
    assert "[PATH]" in s6


@pytest.mark.asyncio
async def test_sitemap_decompression_bomb_protection():
    """Verify sitemap gzipped decompression bomb is bounded and does not exhaust memory."""
    discoverer = SitemapDiscoverer("https://example.com", "example.com")

    # Generate a small 1KB gzip payload that decompresses to > 6MB (exceeds default 5MB limit)
    large_xml = b"<urlset>" + (b"<url><loc>https://example.com/p</loc></url>" * 150000) + b"</urlset>"
    gz_buf = io.BytesIO()
    with gzip.GzipFile(fileobj=gz_buf, mode="wb") as gz:
        gz.write(large_xml)
    compressed_bytes = gz_buf.getvalue()

    mock_req = Request("GET", "https://example.com/sitemap.xml.gz")
    mock_resp = Response(
        status_code=200,
        content=compressed_bytes,
        headers={"Content-Type": "application/x-gzip"},
        request=mock_req
    )

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        urls = await discoverer.discover(seed_sitemaps=["https://example.com/sitemap.xml.gz"])

    # Must abort cleanly without crashing, and log warning
    assert len(urls) == 0
    assert any("decompressed sitemap exceeded max limit" in w.lower() for w in discoverer.warnings)


@pytest.mark.asyncio
async def test_robots_txt_oversized_response_protection():
    """Verify oversized robots.txt is rejected before parsing."""
    policy = RobotsPolicy("https://example.com")
    oversized_content = b"User-agent: *\nDisallow: /admin\n" + (b"# comment\n" * 600000) # > 6MB

    mock_req = Request("GET", "https://example.com/robots.txt")
    mock_resp = Response(status_code=200, content=oversized_content, request=mock_req)

    with patch("httpx.AsyncClient.get", return_value=mock_resp):
        await policy.fetch_and_parse()

    assert policy.error is not None
    assert "exceeded maximum size limit" in policy.error.lower()
    assert not policy.is_accessible
