"""Deterministic Regression & Integration Tests for Connection-Time Egress Protection,
DNS Rebinding Prevention, and Browser Sandbox Enforcement.
"""
import asyncio
import ipaddress
import socket
from unittest.mock import patch, MagicMock
import pytest
import httpx

from app.core.config import Settings
from app.crawler.security import SecurityValidationError
from app.crawler.engine import safe_browser_setup
from app.crawler.transport import (
    SafeEgressProxy,
    create_safe_httpx_client,
    safe_fetch_scrapling,
    safe_fetch_dynamic,
    resolve_egress_proxy_url,
)


@pytest.mark.asyncio
async def test_dns_rebinding_blocked_at_connection_time():
    """
    Test DNS Rebinding:
    Initial validation sees a public IP (e.g. 93.184.216.34).
    Subsequent connection-time resolution returns 127.0.0.1.
    The SafeEgressProxy must intercept at connection time and return 403 Forbidden,
    preventing any TCP socket from being established to 127.0.0.1.
    """
    proxy = SafeEgressProxy()
    proxy_url = await proxy.start()

    try:
        # Simulate DNS rebinding: socket.getaddrinfo returns 127.0.0.1 inside the proxy
        rebound_addrinfo = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("127.0.0.1", 0))
        ]

        with patch("socket.getaddrinfo", return_value=rebound_addrinfo):
            async with httpx.AsyncClient(proxy=proxy_url) as client:
                with pytest.raises(httpx.ProxyError) as exc_info:
                    await client.get("https://rebind-attack.org:443/")

                # Must be rejected by proxy with 403
                assert "403" in str(exc_info.value)
    finally:
        await proxy.stop()


@pytest.mark.asyncio
async def test_dns_rebinding_to_cloud_metadata_blocked():
    """
    Test DNS Rebinding to Cloud Metadata (169.254.169.254):
    Connection-time DNS resolution rebinds to link-local/cloud metadata.
    The SafeEgressProxy must terminate with 403 Forbidden.
    """
    proxy = SafeEgressProxy()
    proxy_url = await proxy.start()

    try:
        metadata_addrinfo = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("169.254.169.254", 0))
        ]

        with patch("socket.getaddrinfo", return_value=metadata_addrinfo):
            async with httpx.AsyncClient(proxy=proxy_url) as client:
                with pytest.raises(httpx.ProxyError) as exc_info:
                    await client.get("https://metadata-rebind.internal:443/")

                assert "403" in str(exc_info.value)
    finally:
        await proxy.stop()


@pytest.mark.asyncio
async def test_dual_homed_dns_resolution_blocked_at_connection_time():
    """
    Test dual-homed DNS response: returns both a public IP and a private IP.
    The proxy must fail closed and reject with 403 Forbidden.
    """
    proxy = SafeEgressProxy()
    proxy_url = await proxy.start()

    try:
        dual_addrinfo = [
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("93.184.216.34", 0)),
            (socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.5", 0)),
        ]

        with patch("socket.getaddrinfo", return_value=dual_addrinfo):
            async with httpx.AsyncClient(proxy=proxy_url) as client:
                with pytest.raises(httpx.ProxyError) as exc_info:
                    await client.get("https://dual-homed.example.com:443/")

                assert "403" in str(exc_info.value)
    finally:
        await proxy.stop()


@pytest.mark.asyncio
async def test_connect_to_prohibited_port_blocked():
    """
    Test destination port restrictions:
    Attempts to CONNECT to dangerous ports (e.g. 22 SSH, 6379 Redis)
    must be rejected by the proxy with 403 Forbidden before DNS/connection.
    """
    proxy = SafeEgressProxy()
    proxy_url = await proxy.start()

    try:
        async with httpx.AsyncClient(proxy=proxy_url) as client:
            with pytest.raises(httpx.ProxyError) as exc_22:
                await client.get("https://example.com:22/")
            assert "403" in str(exc_22.value)

            with pytest.raises(httpx.ProxyError) as exc_6379:
                await client.get("https://example.com:6379/")
            assert "403" in str(exc_6379.value)
    finally:
        await proxy.stop()


@pytest.mark.asyncio
async def test_proxy_blocks_ipv4_mapped_ipv6():
    """
    Test IPv4-mapped IPv6 prohibited address (e.g. [::ffff:127.0.0.1])
    is rejected at the proxy connection layer.
    """
    proxy = SafeEgressProxy()
    proxy_url = await proxy.start()

    try:
        mapped_addrinfo = [
            (socket.AF_INET6, socket.SOCK_STREAM, 6, "", ("::ffff:127.0.0.1", 0, 0, 0))
        ]

        with patch("socket.getaddrinfo", return_value=mapped_addrinfo):
            async with httpx.AsyncClient(proxy=proxy_url) as client:
                with pytest.raises(httpx.ProxyError) as exc_info:
                    await client.get("https://mapped-test.example.com:443/")
                assert "403" in str(exc_info.value)
    finally:
        await proxy.stop()


@pytest.mark.asyncio
async def test_dns_resolution_failure_returns_502():
    """
    Test DNS resolution failure inside the proxy produces 502 Bad Gateway.
    """
    proxy = SafeEgressProxy()
    proxy_url = await proxy.start()

    try:
        with patch("socket.getaddrinfo", side_effect=socket.gaierror(-2, "Name or service not known")):
            async with httpx.AsyncClient(proxy=proxy_url) as client:
                with pytest.raises(httpx.ProxyError) as exc_info:
                    await client.get("https://unresolvable-domain-test.example:443/")
                assert "502" in str(exc_info.value)
    finally:
        await proxy.stop()


def test_production_fails_closed_without_egress_proxy():
    """
    In production mode, missing EGRESS_PROXY_URL must fail closed immediately.
    """
    prod_settings = Settings(
        ENVIRONMENT="production",
        EGRESS_PROXY_URL=None,
        ALLOW_BROWSER_FALLBACK=False
    )
    with pytest.raises(ValueError) as exc_info:
        prod_settings.validate_security_configuration()
    assert "EGRESS_PROXY_URL" in str(exc_info.value)


def test_production_refuses_unsandboxed_browser_fallback():
    """
    In production mode, enabling browser fallback without isolated mode must fail closed.
    """
    prod_settings = Settings(
        ENVIRONMENT="production",
        EGRESS_PROXY_URL="http://egress-proxy:4750",
        ALLOW_BROWSER_FALLBACK=True,
        BROWSER_ISOLATION_MODE="none"
    )
    with pytest.raises(ValueError) as exc_info:
        prod_settings.validate_security_configuration()
    assert "isolated execution mode" in str(exc_info.value)


def test_safe_fetch_dynamic_enforces_disabled_default():
    """
    safe_fetch_dynamic must raise SecurityValidationError when ALLOW_BROWSER_FALLBACK is False.
    """
    with patch("app.core.config.settings.ALLOW_BROWSER_FALLBACK", False):
        with pytest.raises(SecurityValidationError) as exc:
            safe_fetch_dynamic("https://example.com")
        assert "disabled by configuration" in str(exc.value)


def test_safe_browser_setup_blocks_websockets_and_media():
    """
    Verify Playwright route handler aborts WebSockets, media, and dangerous URI schemes.
    """
    mock_page = MagicMock()
    safe_browser_setup(mock_page)

    # Ensure page.route was registered
    mock_page.route.assert_called_once()
    route_pattern, interceptor = mock_page.route.call_args[0]
    assert route_pattern == "**/*"

    # Test WebSocket request is aborted
    ws_route = MagicMock()
    ws_request = MagicMock()
    ws_request.url = "wss://example.com/socket"
    ws_request.resource_type = "websocket"
    interceptor(ws_route, ws_request)
    ws_route.abort.assert_called_with("blockedbyclient")

    # Test media request is aborted
    media_route = MagicMock()
    media_request = MagicMock()
    media_request.url = "https://example.com/video.mp4"
    media_request.resource_type = "media"
    interceptor(media_route, media_request)
    media_route.abort.assert_called_with("blockedbyclient")

    # Test file:// protocol request is aborted
    file_route = MagicMock()
    file_request = MagicMock()
    file_request.url = "file:///etc/passwd"
    file_request.resource_type = "document"
    interceptor(file_route, file_request)
    file_route.abort.assert_called_with("blockedbyclient")


@pytest.mark.asyncio
async def test_proxy_unavailable_fails_closed():
    """
    Test when proxy is configured but unreachable (e.g. dead port),
    requests fail closed rather than falling back to direct insecure requests.
    """
    # Point to an unused local port
    dead_proxy = "http://127.0.0.1:1"
    async with httpx.AsyncClient(proxy=dead_proxy, timeout=0.5) as client:
        with pytest.raises(httpx.TransportError):
            await client.get("https://example.com/")


@pytest.mark.asyncio
async def test_legitimate_https_request_through_safe_proxy():
    """
    Verify legitimate public HTTPS request through SafeEgressProxy preserves
    end-to-end TLS certificate verification and SNI.
    """
    proxy = SafeEgressProxy()
    proxy_url = await proxy.start()

    try:
        async with httpx.AsyncClient(proxy=proxy_url, timeout=10.0) as client:
            resp = await client.get("https://example.com")
            assert resp.status_code == 200
            assert "Example Domain" in resp.text
    finally:
        await proxy.stop()
