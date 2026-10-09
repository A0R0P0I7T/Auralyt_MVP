import pytest
from app.crawler.security import (
    validate_and_resolve_url,
    normalize_url,
    is_same_domain_or_subdomain,
    sanitize_error_summary,
    SecurityValidationError
)


def test_url_normalization():
    url = "HTTPS://WWW.EXAMPLE.COM/about/?utm_source=twitter&ref=abc#section-1"
    norm = normalize_url(url)
    assert norm == "https://www.example.com/about?ref=abc"
    assert "utm_source" not in norm
    assert "#section-1" not in norm


def test_url_normalization_root_path():
    url = "https://example.com"
    norm = normalize_url(url)
    assert norm == "https://example.com/"


def test_ssrf_blocks_loopback_ipv4():
    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("http://127.0.0.1/admin")
    assert "blocked" in str(exc.value).lower() or "prohibited" in str(exc.value).lower()


def test_ssrf_blocks_localhost_hostname():
    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("http://localhost:8000/secret")
    assert "prohibited" in str(exc.value).lower()


def test_ssrf_blocks_private_ip():
    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("http://192.168.1.1/router")
    assert "blocked" in str(exc.value).lower() or "prohibited" in str(exc.value).lower()

    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("http://10.0.0.5/")
    assert "blocked" in str(exc.value).lower() or "prohibited" in str(exc.value).lower()


def test_ssrf_blocks_cloud_metadata():
    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("http://169.254.169.254/latest/meta-data/")
    assert "blocked" in str(exc.value).lower() or "prohibited" in str(exc.value).lower()

    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("http://metadata.google.internal/computeMetadata/v1/")
    assert "prohibited" in str(exc.value).lower()


def test_ssrf_blocks_unsupported_schemes():
    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("ftp://example.com/file.txt")
    assert "unsupported scheme" in str(exc.value).lower()

    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("file:///etc/passwd")
    assert "unsupported scheme" in str(exc.value).lower()


def test_ssrf_blocks_ipv4_mapped_ipv6():
    # IPv4-mapped loopback
    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("http://[::ffff:127.0.0.1]/")
    assert "blocked" in str(exc.value).lower() or "prohibited" in str(exc.value).lower()

    # IPv4-mapped cloud metadata
    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("http://[::ffff:169.254.169.254]/")
    assert "blocked" in str(exc.value).lower() or "prohibited" in str(exc.value).lower()

    # Expanded IPv4-mapped loopback
    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("http://[0:0:0:0:0:ffff:127.0.0.1]/")
    assert "blocked" in str(exc.value).lower() or "prohibited" in str(exc.value).lower()


def test_ssrf_blocks_alternate_ip_representations():
    # Decimal integer IP representation for 127.0.0.1
    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("http://2130706433/")
    assert "blocked" in str(exc.value).lower() or "prohibited" in str(exc.value).lower()

    # Hex IP representation for 127.0.0.1
    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("http://0x7f000001/")
    assert "blocked" in str(exc.value).lower() or "prohibited" in str(exc.value).lower()

    # Octal IP representation for 127.0.0.1
    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("http://0177.0.0.1/")
    assert "blocked" in str(exc.value).lower() or "prohibited" in str(exc.value).lower()


def test_ssrf_blocks_unusual_ports():
    # Dangerous service ports must be rejected
    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("http://example.com:22/")
    assert "port 22 is not permitted" in str(exc.value).lower()

    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("http://example.com:6379/")
    assert "port 6379 is not permitted" in str(exc.value).lower()

    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("http://example.com:25/")
    assert "port 25 is not permitted" in str(exc.value).lower()


def test_ssrf_allows_standard_web_ports():
    # Ports 80, 443, 8080, 8443 are allowed for legitimate web hosts
    norm, _, _ = validate_and_resolve_url("https://example.com:443/")
    assert norm == "https://example.com/"

    norm, _, _ = validate_and_resolve_url("http://example.com:80/")
    assert norm == "http://example.com/"

    norm, _, _ = validate_and_resolve_url("https://example.com:8080/api")
    assert "8080" in norm


def test_domain_scope_matching():
    assert is_same_domain_or_subdomain("https://example.com/pricing", "example.com")
    assert is_same_domain_or_subdomain("https://www.example.com/pricing", "example.com")
    assert is_same_domain_or_subdomain("https://example.com/about", "www.example.com")
    assert is_same_domain_or_subdomain("https://example.com:8080/about", "example.com")
    assert not is_same_domain_or_subdomain("https://otherdomain.com/page", "example.com")
    assert not is_same_domain_or_subdomain("https://sub.otherdomain.com", "example.com")


def test_ssrf_blocks_url_encoded_hostnames():
    with pytest.raises(SecurityValidationError) as exc:
        validate_and_resolve_url("http://%31%32%37%2e%30%2e%30%2e%31/")
    assert "blocked" in str(exc.value).lower() or "prohibited" in str(exc.value).lower()


def test_sanitize_error_summary():
    # Database URL credential redaction
    err = "Connection failed to postgresql+asyncpg://admin:SuperSecretPassword123@db.internal:5432/auralyt"
    sanitized = sanitize_error_summary(err)
    assert "SuperSecretPassword123" not in sanitized
    assert "admin" not in sanitized
    assert "***@" in sanitized

    # Local file path redaction (Windows & Unix)
    win_err = "FileNotFoundError: C:\\Users\\sahaa\\AppData\\Local\\config.json not found"
    sanitized_win = sanitize_error_summary(win_err)
    assert "C:\\Users\\sahaa" not in sanitized_win
    assert "[PATH]" in sanitized_win

    unix_err = "Permission denied: /home/ubuntu/.ssh/id_rsa"
    sanitized_unix = sanitize_error_summary(unix_err)
    assert "/home/ubuntu" not in sanitized_unix
    assert "[PATH]" in sanitized_unix

    # Truncation for oversized error messages
    long_err = "A" * 500
    sanitized_long = sanitize_error_summary(long_err)
    assert len(sanitized_long) <= 300
    assert sanitized_long.endswith("...")

