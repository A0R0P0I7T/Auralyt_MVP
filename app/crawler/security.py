"""Security and URL validation module for Auralyt MVP crawler.
Provides strict SSRF protection, DNS validation, IP range filtering,
port restrictions, alternate IP encoding detection, and URL normalization.
"""
import ipaddress
import re
import socket
from typing import Tuple, Optional, Set, Any, Union
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode, unquote

# Permitted web ports
ALLOWED_PORTS: Set[int] = {80, 443, 8080, 8443}

# Prohibited private, loopback, link-local, multicast, and cloud metadata networks
PROHIBITED_NETWORKS = [
    # IPv4 Special & Private
    ipaddress.ip_network("0.0.0.0/8"),         # "This" network
    ipaddress.ip_network("10.0.0.0/8"),        # Private IPv4 Class A
    ipaddress.ip_network("100.64.0.0/10"),     # Shared Address Space / CGNAT
    ipaddress.ip_network("127.0.0.0/8"),       # Loopback IPv4
    ipaddress.ip_network("169.254.0.0/16"),    # Link-local / Cloud Metadata (169.254.169.254)
    ipaddress.ip_network("172.16.0.0/12"),     # Private IPv4 Class B
    ipaddress.ip_network("192.0.0.0/24"),      # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),      # Documentation (TEST-NET-1)
    ipaddress.ip_network("192.168.0.0/16"),    # Private IPv4 Class C
    ipaddress.ip_network("198.18.0.0/15"),     # Network benchmark tests
    ipaddress.ip_network("198.51.100.0/24"),   # Documentation (TEST-NET-2)
    ipaddress.ip_network("203.0.113.0/24"),    # Documentation (TEST-NET-3)
    ipaddress.ip_network("224.0.0.0/4"),       # Multicast
    ipaddress.ip_network("240.0.0.0/4"),       # Reserved / Future use
    ipaddress.ip_network("255.255.255.255/32"),# Broadcast
    # IPv6 Special & Private
    ipaddress.ip_network("::1/128"),           # Loopback IPv6
    ipaddress.ip_network("::/128"),            # Unspecified IPv6
    ipaddress.ip_network("64:ff9b::/96"),      # IPv4-IPv6 translation
    ipaddress.ip_network("100::/64"),          # Discard prefix
    ipaddress.ip_network("2001:db8::/32"),     # Documentation IPv6
    ipaddress.ip_network("fc00::/7"),          # Unique local address (IPv6 private)
    ipaddress.ip_network("fe80::/10"),         # Link-local IPv6
    ipaddress.ip_network("ff00::/8"),          # Multicast IPv6
]

BLOCKED_HOSTNAMES = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata",
    "instance-data",
    "169.254.169.254",
}

# Tracking query parameters to strip during normalization
TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "fbclid", "gclid", "gclsrc", "dclid", "zanpid", "msclkid",
    "mc_cid", "mc_eid", "_ga", "_gl", "yclid", "wickedid"
}


class SecurityValidationError(Exception):
    """Raised when a URL violates security or SSRF policies."""
    pass


def is_ip_prohibited(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """
    Check if an IP address belongs to any prohibited/private/link-local/metadata network.
    Safely inspects IPv4-mapped IPv6 addresses (e.g., ::ffff:127.0.0.1).
    """
    # If IPv6 is mapping an IPv4 address, inspect the underlying IPv4 address
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped:
        if is_ip_prohibited(ip.ipv4_mapped):
            return True

    # Check built-in properties
    if (
        ip.is_loopback
        or ip.is_private
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        return True

    # Check explicit network blocks
    for network in PROHIBITED_NETWORKS:
        if ip in network:
            return True

    return False


def parse_alternate_ip_notation(host: str) -> Optional[ipaddress.IPv4Address | ipaddress.IPv6Address]:
    """
    Detects and parses alternate integer, hex, or octal IP representations
    such as 2130706433, 0x7f000001, 0177.0.0.1.
    """
    clean_host = host.strip("[]")

    # 1. Standard IP literal
    try:
        return ipaddress.ip_address(clean_host)
    except ValueError:
        pass

    # 2. Pure integer notation (e.g., 2130706433)
    if clean_host.isdigit():
        try:
            int_val = int(clean_host)
            if 0 <= int_val <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(int_val)
        except Exception:
            pass

    # 3. Hex integer notation (e.g., 0x7f000001)
    if clean_host.lower().startswith("0x"):
        try:
            hex_val = int(clean_host, 16)
            if 0 <= hex_val <= 0xFFFFFFFF:
                return ipaddress.IPv4Address(hex_val)
        except Exception:
            pass

    # 4. Octal or mixed dotted notation (e.g., 0177.0.0.1)
    parts = clean_host.split(".")
    if len(parts) == 4 and all(p for p in parts):
        try:
            octets = []
            for p in parts:
                if p.startswith("0x") or p.startswith("0X"):
                    octets.append(int(p, 16))
                elif p.startswith("0") and len(p) > 1:
                    octets.append(int(p, 8))
                else:
                    octets.append(int(p, 10))
            if all(0 <= o <= 255 for o in octets):
                return ipaddress.IPv4Address(bytes(octets))
        except Exception:
            pass

    return None


def validate_and_resolve_url(raw_url: str) -> Tuple[str, str, str]:
    """
    Validate URL structure, enforce safe schemes (http, https),
    restrict ports to standard web ports, detect alternate IP notations,
    resolve DNS hostnames, and block private/loopback/cloud metadata IPs.

    Returns:
        Tuple of (normalized_url, resolved_ip, hostname)
    Raises:
        SecurityValidationError: if validation fails.
    """
    if not raw_url or not isinstance(raw_url, str):
        raise SecurityValidationError("URL must be a non-empty string.")

    raw_url = raw_url.strip()
    if "://" in raw_url:
        scheme_part = raw_url.split("://", 1)[0].lower()
        if scheme_part not in ("http", "https"):
            raise SecurityValidationError(f"Unsupported scheme '{scheme_part}'. Only HTTP and HTTPS are permitted.")
    else:
        raw_url = "https://" + raw_url

    try:
        parsed = urlparse(raw_url)
    except Exception as e:
        raise SecurityValidationError(f"Malformed URL: {e}")

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise SecurityValidationError(f"Unsupported scheme '{scheme}'. Only HTTP and HTTPS are permitted.")

    raw_hostname = (parsed.hostname or "").lower().strip()
    if not raw_hostname:
        raise SecurityValidationError("URL missing valid hostname.")

    # Check URL-encoded hostname (e.g. %31%32%37%2e%30%2e%30%2e%31)
    unquoted_hostname = unquote(raw_hostname).lower()

    for host_variant in (raw_hostname, unquoted_hostname):
        if host_variant in BLOCKED_HOSTNAMES:
            raise SecurityValidationError(f"Access to hostname '{host_variant}' is prohibited.")

    # Restrict allowed ports to standard web ports
    if parsed.port is not None and parsed.port not in ALLOWED_PORTS:
        raise SecurityValidationError(
            f"Port {parsed.port} is not permitted. Only web ports {sorted(list(ALLOWED_PORTS))} are allowed."
        )

    # Check for direct alternate IP literal (decimal, hex, octal, standard)
    direct_ip = parse_alternate_ip_notation(unquoted_hostname)
    if direct_ip is not None:
        if is_ip_prohibited(direct_ip):
            raise SecurityValidationError(f"Access to private/restricted IP '{direct_ip}' is blocked.")
        resolved_ip = str(direct_ip)
    else:
        # Not an IP literal: perform DNS resolution
        try:
            addr_info = socket.getaddrinfo(unquoted_hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            if not addr_info:
                raise SecurityValidationError(f"Could not resolve host '{unquoted_hostname}'.")

            resolved_ips = []
            for item in addr_info:
                sockaddr = item[4]
                ip_str = sockaddr[0]
                ip_obj = ipaddress.ip_address(ip_str)
                if is_ip_prohibited(ip_obj):
                    raise SecurityValidationError(
                        f"Host '{unquoted_hostname}' resolved to prohibited IP '{ip_str}'."
                    )
                resolved_ips.append(ip_str)
            resolved_ip = resolved_ips[0] if resolved_ips else ""
        except socket.gaierror as e:
            raise SecurityValidationError(f"DNS resolution failed for '{unquoted_hostname}': {e}")

    normalized_url = normalize_url(raw_url)
    return normalized_url, resolved_ip, raw_hostname


def normalize_url(url: str) -> str:
    """
    Normalizes a URL by:
    - Lowercasing scheme and netloc
    - Removing default ports (80 for http, 443 for https)
    - Stripping fragments (#...)
    - Removing standard tracking parameters
    - Standardizing empty path to '/'
    - Removing trailing slash if path != '/'
    """
    parsed = urlparse(url)
    scheme = parsed.scheme.lower()
    netloc = parsed.netloc.lower()

    # Strip default ports
    if scheme == "http" and netloc.endswith(":80"):
        netloc = netloc[:-3]
    elif scheme == "https" and netloc.endswith(":443"):
        netloc = netloc[:-4]

    # Normalize path
    path = parsed.path
    if not path:
        path = "/"
    elif len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")

    # Strip tracking query params and sort remaining
    clean_params = []
    if parsed.query:
        for k, v in parse_qsl(parsed.query, keep_blank_values=True):
            if k.lower() not in TRACKING_PARAMS:
                clean_params.append((k, v))
        clean_params.sort(key=lambda x: x[0])

    new_query = urlencode(clean_params)

    # Reconstruct without fragment
    normalized = urlunparse((scheme, netloc, path, parsed.params, new_query, ""))
    return normalized


def is_same_domain_or_subdomain(target_url: str, base_domain: str) -> bool:
    """
    Strictly check if target_url belongs to the exact base domain or allowed scope.
    Avoids crawling arbitrary external domains or unrelated subdomains.
    """
    try:
        target_parsed = urlparse(target_url)
        target_host = (target_parsed.hostname or "").lower()
        base_clean = base_domain.lower()

        # Strip ports if present in base_domain
        if ":" in base_clean:
            base_clean = base_clean.split(":", 1)[0]

        # Handle 'www.' variations
        base_clean_no_www = base_clean[4:] if base_clean.startswith("www.") else base_clean
        target_clean_no_www = target_host[4:] if target_host.startswith("www.") else target_host

        return target_clean_no_www == base_clean_no_www
    except Exception:
        return False


def sanitize_error_summary(error: Any) -> str:
    """
    Sanitize an exception or error string to prevent information leakage,
    such as leaking credentials, internal file system paths, or raw stack traces.
    """
    if error is None:
        return ""
    msg = str(error)
    # Mask database connection strings or URLs containing credentials (e.g. postgres://user:password@host)
    msg = re.sub(r'([a-zA-Z0-9+.-]+://[^:]+):[^@]+@', r'\1:***@', msg)
    # Mask filesystem paths (Windows C:\... or Unix /home/... /tmp/...)
    msg = re.sub(r'[A-Za-z]:\\[^:\s<>"\']+', '[PATH]', msg)
    msg = re.sub(r'/(?:Users|home|root|tmp|var|etc)/[^\s<>"\']+', '[PATH]', msg)
    # Truncate to reasonable length (max 300 characters)
    if len(msg) > 300:
        msg = msg[:297] + "..."
    return msg

