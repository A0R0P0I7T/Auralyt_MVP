import pytest
from app.crawler.security import (
    validate_and_resolve_url,
    normalize_url,
    is_same_domain_or_subdomain,
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


def test_domain_scope_matching():
    assert is_same_domain_or_subdomain("https://example.com/pricing", "example.com")
    assert is_same_domain_or_subdomain("https://www.example.com/pricing", "example.com")
    assert is_same_domain_or_subdomain("https://example.com/about", "www.example.com")
    assert not is_same_domain_or_subdomain("https://otherdomain.com/page", "example.com")
    assert not is_same_domain_or_subdomain("https://sub.otherdomain.com", "example.com")
