"""Centralized Outbound Network Transport & Egress Security Module.
Provides connection-time DNS validation, SSRF prevention against DNS rebinding,
centralized HTTP client construction, and isolated browser networking.
"""
import asyncio
import ipaddress
import logging
import socket
from typing import Optional, Dict, Tuple, Set, Any, Callable
from urllib.parse import urlparse, unquote

import httpx
from scrapling import AsyncFetcher, DynamicFetcher

from app.core.config import settings
from app.crawler.security import (
    is_ip_prohibited,
    ALLOWED_PORTS,
    BLOCKED_HOSTNAMES,
    SecurityValidationError,
)

logger = logging.getLogger(__name__)

# Active local proxy instance for development and test suites
_local_safe_proxy: Optional["SafeEgressProxy"] = None
_proxy_lock = asyncio.Lock()


class SafeEgressProxy:
    """
    In-process asynchronous HTTP & CONNECT egress proxy server.
    Validates destination hostnames and destination IP addresses at the exact moment
    of TCP connection establishment, preventing DNS rebinding (TOCTOU) and SSRF.
    """

    def __init__(self, host: str = "127.0.0.1", port: int = 0):
        self.host = host
        self.requested_port = port
        self.server: Optional[asyncio.Server] = None
        self.assigned_port: int = 0
        self.active_connections: Set[asyncio.Task] = set()

    async def start(self) -> str:
        """Start the proxy server and return the proxy URL."""
        if self.server is not None:
            return self.get_proxy_url()

        self.server = await asyncio.start_server(
            self._handle_client,
            self.host,
            self.requested_port
        )
        self.assigned_port = self.server.sockets[0].getsockname()[1]
        logger.info(f"SafeEgressProxy listening at {self.get_proxy_url()}")
        return self.get_proxy_url()

    async def stop(self) -> None:
        """Stop the proxy server and close all active connections."""
        if self.server:
            self.server.close()
            await self.server.wait_closed()
            self.server = None

        # Cancel any active forwarding tasks
        for task in list(self.active_connections):
            if not task.done():
                task.cancel()
        if self.active_connections:
            await asyncio.gather(*self.active_connections, return_exceptions=True)
            self.active_connections.clear()

        logger.info("SafeEgressProxy stopped.")

    def get_proxy_url(self) -> str:
        if not self.assigned_port:
            raise RuntimeError("SafeEgressProxy is not running.")
        return f"http://{self.host}:{self.assigned_port}"

    async def _handle_client(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter
    ) -> None:
        current_task = asyncio.current_task()
        if current_task:
            self.active_connections.add(current_task)
            current_task.add_done_callback(self.active_connections.discard)

        try:
            req_line = await client_reader.readline()
            if not req_line:
                client_writer.close()
                return

            line_str = req_line.decode("utf-8", errors="ignore").strip()
            parts = line_str.split()
            if len(parts) < 2:
                client_writer.close()
                return

            method, target = parts[0].upper(), parts[1]

            if method == "CONNECT":
                await self._handle_connect(client_reader, client_writer, target)
            else:
                await self._handle_http_forward(client_reader, client_writer, method, target, parts)
        except Exception as e:
            logger.debug(f"Proxy client handling error: {e}")
        finally:
            try:
                client_writer.close()
                await client_writer.wait_closed()
            except Exception:
                pass

    async def _handle_connect(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        target: str
    ) -> None:
        """Handle HTTPS CONNECT tunnel with connection-time DNS & IP verification."""
        try:
            if ":" in target:
                host_str, port_str = target.split(":", 1)
                port = int(port_str)
            else:
                host_str = target
                port = 443
        except ValueError:
            client_writer.write(b"HTTP/1.1 400 Bad Request\r\nContent-Length: 15\r\n\r\nInvalid Target")
            await client_writer.drain()
            return

        # Read remainder of client CONNECT headers
        while True:
            header_line = await client_reader.readline()
            if header_line in (b"\r\n", b"\n", b""):
                break

        # Connection-time validation
        is_safe, err_msg, target_ip = self._validate_destination(host_str, port)
        if not is_safe or not target_ip:
            logger.warning(f"SafeEgressProxy BLOCKED CONNECT to {host_str}:{port} -> {err_msg}")
            status_code = b"502 Bad Gateway" if "DNS" in err_msg else b"403 Forbidden"
            body = f"SSRF Prohibited: {err_msg}".encode("utf-8")
            resp = (
                b"HTTP/1.1 " + status_code + b"\r\n"
                b"Content-Type: text/plain\r\n"
                b"Content-Length: " + str(len(body)).encode("utf-8") + b"\r\n"
                b"Connection: close\r\n\r\n" + body
            )
            client_writer.write(resp)
            await client_writer.drain()
            return

        # Connect directly to the validated IP to prevent DNS rebinding
        try:
            target_reader, target_writer = await asyncio.wait_for(
                asyncio.open_connection(target_ip, port),
                timeout=settings.REQUEST_TIMEOUT_SECONDS
            )
        except Exception as conn_err:
            logger.warning(f"Failed to connect to {target_ip}:{port}: {conn_err}")
            client_writer.write(b"HTTP/1.1 504 Gateway Timeout\r\nConnection: close\r\n\r\n")
            await client_writer.drain()
            return

        # Acknowledge tunnel establishment
        client_writer.write(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        await client_writer.drain()

        # Bi-directional stream forwarding
        await self._pipe_bidirectional(client_reader, client_writer, target_reader, target_writer)

    async def _handle_http_forward(
        self,
        client_reader: asyncio.StreamReader,
        client_writer: asyncio.StreamWriter,
        method: str,
        target: str,
        parts: list
    ) -> None:
        """Handle plain HTTP proxy forward with connection-time DNS & IP verification."""
        parsed = urlparse(target)
        host_str = parsed.hostname or ""
        port = parsed.port or (443 if parsed.scheme == "https" else 80)

        # Read remaining headers
        headers = []
        while True:
            line = await client_reader.readline()
            if line in (b"\r\n", b"\n", b""):
                break
            headers.append(line)

        is_safe, err_msg, target_ip = self._validate_destination(host_str, port)
        if not is_safe or not target_ip:
            logger.warning(f"SafeEgressProxy BLOCKED HTTP {method} to {host_str}:{port} -> {err_msg}")
            status_code = b"502 Bad Gateway" if "DNS" in err_msg else b"403 Forbidden"
            body = f"SSRF Prohibited: {err_msg}".encode("utf-8")
            resp = (
                b"HTTP/1.1 " + status_code + b"\r\n"
                b"Content-Type: text/plain\r\n"
                b"Content-Length: " + str(len(body)).encode("utf-8") + b"\r\n"
                b"Connection: close\r\n\r\n" + body
            )
            client_writer.write(resp)
            await client_writer.drain()
            return

        try:
            target_reader, target_writer = await asyncio.wait_for(
                asyncio.open_connection(target_ip, port),
                timeout=settings.REQUEST_TIMEOUT_SECONDS
            )
        except Exception as conn_err:
            logger.warning(f"Failed to connect to {target_ip}:{port}: {conn_err}")
            client_writer.write(b"HTTP/1.1 504 Gateway Timeout\r\nConnection: close\r\n\r\n")
            await client_writer.drain()
            return

        # Rewrite request line with relative path
        rel_path = parsed.path or "/"
        if parsed.query:
            rel_path += f"?{parsed.query}"
        http_version = parts[2] if len(parts) > 2 else "HTTP/1.1"
        target_writer.write(f"{method} {rel_path} {http_version}\r\n".encode("utf-8"))
        for h in headers:
            target_writer.write(h)
        target_writer.write(b"\r\n")
        await target_writer.drain()

        await self._pipe_bidirectional(client_reader, client_writer, target_reader, target_writer)

    def _validate_destination(self, host: str, port: int) -> Tuple[bool, str, Optional[str]]:
        """
        Validate destination port, hostnames, and resolve DNS at connection time.
        Returns: (is_safe, error_message, validated_ip)
        """
        if port not in ALLOWED_PORTS:
            return False, f"Port {port} is not permitted. Only {sorted(list(ALLOWED_PORTS))} allowed.", None

        clean_host = unquote(host).lower().strip().rstrip(".")
        if not clean_host:
            return False, "Missing destination hostname.", None

        if clean_host in BLOCKED_HOSTNAMES:
            return False, f"Destination hostname '{clean_host}' is prohibited.", None

        # Resolve DNS at connection time
        try:
            addrinfo = socket.getaddrinfo(clean_host, port, socket.AF_UNSPEC, socket.SOCK_STREAM)
            if not addrinfo:
                return False, f"DNS resolution failed for '{clean_host}'.", None

            # Verify every returned IP address
            approved_ip = None
            for item in addrinfo:
                ip_str = item[4][0]
                ip_obj = ipaddress.ip_address(ip_str)
                if is_ip_prohibited(ip_obj):
                    return False, f"Host '{clean_host}' resolved to prohibited IP '{ip_str}'.", None
                if approved_ip is None:
                    approved_ip = ip_str

            return True, "", approved_ip
        except socket.gaierror as e:
            return False, f"DNS resolution error: {e}", None
        except Exception as e:
            return False, f"Destination validation error: {e}", None

    async def _pipe_bidirectional(
        self,
        r1: asyncio.StreamReader,
        w1: asyncio.StreamWriter,
        r2: asyncio.StreamReader,
        w2: asyncio.StreamWriter
    ) -> None:
        """Pipe data bi-directionally between two stream pairs."""
        async def forward(source: asyncio.StreamReader, destination: asyncio.StreamWriter):
            try:
                while not source.at_eof():
                    data = await source.read(65536)
                    if not data:
                        break
                    destination.write(data)
                    await destination.drain()
            except Exception:
                pass
            finally:
                try:
                    destination.close()
                except Exception:
                    pass

        t1 = asyncio.create_task(forward(r1, w2))
        t2 = asyncio.create_task(forward(r2, w1))
        await asyncio.gather(t1, t2, return_exceptions=True)


async def get_or_start_local_proxy() -> str:
    """Get the active local SafeEgressProxy or start a new shared instance."""
    global _local_safe_proxy
    async with _proxy_lock:
        if _local_safe_proxy is None or _local_safe_proxy.server is None:
            _local_safe_proxy = SafeEgressProxy()
            await _local_safe_proxy.start()
        return _local_safe_proxy.get_proxy_url()


async def stop_local_proxy() -> None:
    """Stop the shared local SafeEgressProxy if running."""
    global _local_safe_proxy
    async with _proxy_lock:
        if _local_safe_proxy is not None:
            await _local_safe_proxy.stop()
            _local_safe_proxy = None


async def resolve_egress_proxy_url() -> Optional[str]:
    """
    Resolve the applicable egress proxy URL based on environment and settings:
    - Production: Requires explicit EGRESS_PROXY_URL; fails closed if absent.
    - Development/Testing: Uses EGRESS_PROXY_URL if configured, otherwise starts
      the local SafeEgressProxy to enforce connection-time DNS & IP validation.
    """
    if settings.EGRESS_PROXY_URL:
        return settings.EGRESS_PROXY_URL

    if settings.ENVIRONMENT.lower() == "production":
        raise SecurityValidationError(
            "Production environment requires an explicitly configured EGRESS_PROXY_URL "
            "for connection-time SSRF and DNS-rebinding enforcement."
        )

    # In development and test environments, use the built-in SafeEgressProxy
    return await get_or_start_local_proxy()


async def create_safe_httpx_client(
    timeout: Optional[float] = None,
    custom_proxy: Optional[str] = None
) -> httpx.AsyncClient:
    """
    Centralized constructor for secure httpx.AsyncClient instances.
    Enforces egress proxy routing, explicit timeouts, and follow_redirects=False.
    """
    proxy_url = custom_proxy or await resolve_egress_proxy_url()
    return httpx.AsyncClient(
        proxy=proxy_url,
        timeout=timeout or settings.REQUEST_TIMEOUT_SECONDS,
        follow_redirects=False,
        headers={"User-Agent": settings.USER_AGENT}
    )


async def safe_fetch_scrapling(
    url: str,
    custom_proxy: Optional[str] = None,
    timeout: Optional[float] = None,
    headers: Optional[Dict[str, str]] = None
) -> Any:
    """
    Execute a static GET request through Scrapling/curl_cffi with mandatory
    egress proxy routing, follow_redirects=False, and retries=1.
    """
    proxy_url = custom_proxy or await resolve_egress_proxy_url()
    req_headers = {"User-Agent": settings.USER_AGENT}
    if headers:
        req_headers.update(headers)

    return await AsyncFetcher.get(
        url,
        proxy=proxy_url,
        timeout=timeout or settings.REQUEST_TIMEOUT_SECONDS,
        headers=req_headers,
        follow_redirects=False,
        retries=1
    )


def safe_fetch_dynamic(
    url: str,
    custom_proxy: Optional[str] = None,
    timeout_ms: Optional[int] = None,
    page_setup: Optional[Callable] = None
) -> Any:
    """
    Execute dynamic browser rendering through Scrapling/Playwright.
    Enforces that browser fallback is enabled and routes traffic through
    the egress proxy with blocked resources and subresource sandboxing.
    """
    if not settings.ALLOW_BROWSER_FALLBACK:
        raise SecurityValidationError("Dynamic browser fallback is disabled by configuration.")

    if settings.ENVIRONMENT.lower() == "production" and settings.BROWSER_ISOLATION_MODE not in ("egress_proxy", "container_sandbox"):
        raise SecurityValidationError(
            "Browser fallback cannot execute in production without verified isolation mode."
        )

    proxy_url = custom_proxy or settings.BROWSER_PROXY_URL or settings.EGRESS_PROXY_URL
    if not proxy_url and settings.ENFORCE_EGRESS_PROXY:
        raise SecurityValidationError("Dynamic browser rendering requires an active egress proxy.")

    return DynamicFetcher.fetch(
        url,
        proxy=proxy_url,
        timeout=timeout_ms or (settings.REQUEST_TIMEOUT_SECONDS * 1000),
        disable_resources=True,
        blocked_domains=BLOCKED_HOSTNAMES,
        page_setup=page_setup
    )
