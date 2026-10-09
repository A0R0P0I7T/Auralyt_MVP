"""Security and URL validation module for Auralyt MVP crawler.
Provides strict SSRF protection, DNS validation, IP range filtering,
and URL normalization.
"""
import ipaddress
import socket
from typing import Tuple, Optional, Set
from urllib.parse import urlparse, urlunparse, parse_qsl, urlencode

# Prohibited private and loopback networks
PROHIBITED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("100.64.0.0/10"),     # CGNAT
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback IPv4
    ipaddress.ip_network("169.254.0.0/16"),   # Link-local / Cloud Metadata (169.254.169.254)
    ipaddress.ip_network("172.16.0.0/12"),    # Private IPv4 Class B
    ipaddress.ip_network("192.0.0.0/24"),      # IETF Protocol Assignments
    ipaddress.ip_network("192.0.2.0/24"),      # Documentation (TEST-NET-1)
    ipaddress.ip_network("192.168.0.0/16"),   # Private IPv4 Class C
    ipaddress.ip_network("198.18.0.0/15"),    # Network benchmark tests
    ipaddress.ip_network("198.51.100.0/24"),  # Documentation (TEST-NET-2)
    ipaddress.ip_network("203.0.113.0/24"),   # Documentation (TEST-NET-3)
    ipaddress.ip_network("224.0.0.0/4"),      # Multicast
    ipaddress.ip_network("240.0.0.0/4"),      # Reserved
    ipaddress.ip_network("255.255.255.255/32"),
    # IPv6
    ipaddress.ip_network("::1/128"),          # Loopback IPv6
    ipaddress.ip_network("::/128"),           # Unspecified
    ipaddress.ip_network("64:ff9b::/96"),     # IPv4-IPv6 translation
    ipaddress.ip_network("100::/64"),         # Discard prefix
    ipaddress.ip_network("2001:db8::/32"),    # Documentation IPv6
    ipaddress.ip_network("fc00::/7"),         # Unique local address (IPv6 private)
    ipaddress.ip_network("fe80::/10"),        # Link-local IPv6
    ipaddress.ip_network("ff00::/8"),         # Multicast IPv6
]

BLOCKED_HOSTNAMES = {
    "localhost",
    "metadata.google.internal",
    "metadata",
    "instance-data",
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
    """Check if an IP address belongs to any prohibited/private/link-local network."""
    for network in PROHIBITED_NETWORKS:
        if ip in network:
            return True
    return False


def validate_and_resolve_url(raw_url: str) -> Tuple[str, str, str]:
    """
    Validate URL structure, enforce safe schemes (http, https),
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

    hostname = (parsed.hostname or "").lower().strip()
    if not hostname:
        raise SecurityValidationError("URL missing valid hostname.")

    if hostname in BLOCKED_HOSTNAMES:
        raise SecurityValidationError(f"Access to hostname '{hostname}' is prohibited.")

    # Check if hostname itself is an IP literal
    try:
        ip_obj = ipaddress.ip_address(hostname)
        if is_ip_prohibited(ip_obj):
            raise SecurityValidationError(f"Access to private/restricted IP '{hostname}' is blocked.")
        resolved_ip = str(ip_obj)
    except ValueError:
        # Not an IP literal, perform DNS resolution
        try:
            addr_info = socket.getaddrinfo(hostname, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
            if not addr_info:
                raise SecurityValidationError(f"Could not resolve host '{hostname}'.")
            
            resolved_ips = []
            for item in addr_info:
                sockaddr = item[4]
                ip_str = sockaddr[0]
                ip_obj = ipaddress.ip_address(ip_str)
                if is_ip_prohibited(ip_obj):
                    raise SecurityValidationError(
                        f"Host '{hostname}' resolved to prohibited IP '{ip_str}'."
                    )
                resolved_ips.append(ip_str)
            resolved_ip = resolved_ips[0] if resolved_ips else ""
        except socket.gaierror as e:
            raise SecurityValidationError(f"DNS resolution failed for '{hostname}': {e}")

    normalized_url = normalize_url(raw_url)
    return normalized_url, resolved_ip, hostname


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

        # Handle 'www.' variations
        base_clean_no_www = base_clean[4:] if base_clean.startswith("www.") else base_clean
        target_clean_no_www = target_host[4:] if target_host.startswith("www.") else target_host

        return target_clean_no_www == base_clean_no_www
    except Exception:
        return False
