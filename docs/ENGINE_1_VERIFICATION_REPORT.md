# Engine 1: Brand & Website Profiler — Verification & Security Hardening Report

## Executive Summary
This document provides the formal audit and adversarial verification record for **Engine 1: Brand & Website Profiler** in the Auralyt MVP platform. The implementation was subjected to two sequential security hardening and adversarial testing passes:
1. **Pass 1 (Commit `bc15bd9`):** Hardened primary SSRF, manual hop-by-hop redirects, alternate IP parsing, port limits, and basic error sanitization (expanded test suite from 18 to 29 tests).
2. **Pass 2 (Targeted Adversarial Pass — October 10, 2026):** Targeted adversarial verification of outbound transport isolation, DNS multi-record handling, trailing-dot bypasses, userinfo credential stripping, zip-bomb decompression limits, oversized robots.txt rejection, and deep credential/token sanitization (expanded test suite to 36 tests).

---

## 1. Test Suite Verification History

| Phase | Test Suite Count | Execution Time | Pass Rate | Status |
| :--- | :--- | :--- | :--- | :--- |
| **Initial Implementation** | 18 tests | 0.48s | 100% (18/18) | Verified Baseline |
| **First-Pass Hardening** | 29 tests | 0.55s | 100% (29/29) | Verified Pass 1 |
| **Second-Pass Adversarial Pass** | 36 tests | 0.86s | 100% (36/36) | **Verified Pass 2** |

---

## 2. Adversarial Findings & Remediations (Second-Pass)

### Finding 1: Trailing-Dot Hostname Blacklist Bypass
- **Mechanism:** Attackers supplying hostnames with trailing root dots (e.g. `http://metadata.google.internal./` or `http://localhost./`) bypassed direct string matching against `BLOCKED_HOSTNAMES` because `"metadata.google.internal." != "metadata.google.internal"`.
- **Root Cause:** Hostname normalization did not strip trailing FQDN dots before membership testing in `BLOCKED_HOSTNAMES`.
- **Remediation:** In `app/crawler/security.py`, added `.rstrip(".")` to both `raw_hostname` and `unquoted_hostname` before checking `BLOCKED_HOSTNAMES` and evaluating ports.
- **Verification:** Verified by deterministic test `tests/test_adversarial.py::test_trailing_dot_hostname_blocked`.

### Finding 2: Credential & Userinfo Leakage in Normalized URLs
- **Mechanism:** URLs formatted as `https://user:password@example.com/page` or `https://attacker.com@example.com/` retained credentials inside `netloc` after normalization. If the crawler encountered an error or logged the URL, credentials could be persisted or leaked to downstream consumers.
- **Root Cause:** `normalize_url` in `app/crawler/security.py` lowercased `netloc` but did not strip userinfo (`user:pass@`).
- **Remediation:** In `normalize_url`, explicitly stripped credentials (`if "@" in netloc: netloc = netloc.split("@")[-1]`).
- **Verification:** Verified by deterministic test `tests/test_adversarial.py::test_userinfo_stripped_in_normalize_url`.

### Finding 3: Multi-A / Multi-AAAA Record Handling (Failing Closed)
- **Mechanism:** Hostnames that resolve to multiple IP addresses (e.g., dual-homed DNS containing both a public IP `93.184.216.34` and a private IP `10.0.0.1`).
- **Audit Verification:** Confirmed that `app/crawler/security.py` iterates over every address returned by `socket.getaddrinfo()`. If **any** returned IP address belongs to `PROHIBITED_NETWORKS`, the resolver fails closed immediately with `SecurityValidationError`.
- **Verification:** Verified by deterministic isolated mock test `tests/test_adversarial.py::test_mixed_public_and_private_dns_fails_closed`.

### Finding 4: Suffix Confusion & Domain Scope Matching
- **Mechanism:** Attackers attempting suffix confusion (e.g., `https://example.com.attacker.com` or `https://attackerexample.com` or `https://example.com-evil.org`).
- **Audit Verification:** `is_same_domain_or_subdomain()` performs exact equality matching on normalized apex/www hostnames rather than string prefix/suffix checking. Stripped trailing dots and empty string checks were added for strict domain boundary enforcement.
- **Verification:** Verified by deterministic test `tests/test_adversarial.py::test_domain_scope_suffix_confusion`.

### Finding 5: Sitemap Gzip Decompression Bombs
- **Mechanism:** Attackers serving a small (1KB) gzipped sitemap that inflates to several gigabytes (`gz.read()`), causing RAM exhaustion / Denial of Service.
- **Root Cause:** `app/crawler/sitemap.py` invoked unconstrained `content = gz.read()` inside `GzipFile`.
- **Remediation:** Replaced unconstrained reading with bounded chunk extraction (`gz.read(65536)`) accumulating up to `settings.MAX_RESPONSE_SIZE_BYTES` (5MB). If the decompressed payload exceeds 5MB, the stream terminates immediately and logs a sanitized warning.
- **Verification:** Verified by deterministic test `tests/test_adversarial.py::test_sitemap_decompression_bomb_protection`.

### Finding 6: Oversized Robots.txt Denial of Service
- **Mechanism:** Target servers serving an arbitrarily large `robots.txt` (>10MB).
- **Root Cause:** `app/crawler/robots.py` marked `self.is_accessible = True` and read `final_response.text` without evaluating `len(content)`.
- **Remediation:** Enforced `len(content_bytes) <= settings.MAX_RESPONSE_SIZE_BYTES` before parsing and setting `self.is_accessible = True`.
- **Verification:** Verified by deterministic test `tests/test_adversarial.py::test_robots_txt_oversized_response_protection`.

### Finding 7: Deep Credential and Secret Redaction in Error Summaries
- **Mechanism:** Exceptions containing token-only URLs (`https://ghp_token@github.com`), Bearer tokens (`Bearer eyJ...`), query parameters (`?api_key=...`), cookies, and Linux paths (`/app/...`, `/usr/...`) entered `ProfileRun.error_summary`.
- **Root Cause:** `sanitize_error_summary` previously only matched `scheme://user:pass@` and Windows drive paths.
- **Remediation:** Expanded regex sanitization in `app/crawler/security.py` to mask:
  - URLs with userinfo with or without colon passwords
  - Bearer / API key authorization strings
  - Query parameters named `api_key`, `access_token`, `token`, `secret`, `password`, `auth`
  - Cookie header values
  - Linux application and system directory paths (`/app`, `/usr`, `/home`, `/root`, `/tmp`, `/var`, `/etc`, `/opt`)
- **Verification:** Verified by deterministic test `tests/test_adversarial.py::test_sanitize_error_summary_comprehensive_leakage`.

### Finding 8: Fact Source URL Injection & Malformed Schemes
- **Mechanism:** User-submitted facts via `POST /api/brands/{brand_id}/facts` submitting dangerous pseudo-protocols (`javascript:`, `data:`, `file:`) or embedded credentials.
- **Root Cause:** Basic substring check allowed malformed inputs without host validation.
- **Remediation:** In `app/api/v1/endpoints/brands.py`, parsed `source_url` with `urlparse`, validated presence of `netloc`, enforced `http`/`https` schemes, and stripped credentials from `netloc`.
- **Verification:** Verified by deterministic test `tests/test_api_integration.py::test_create_brand_fact_rejects_malicious_source_url`.

---

## 3. Verification Status Matrix

| Protection Dimension | Code Inspection Status | Automated Test Status | Production Readiness Status |
| :--- | :--- | :--- | :--- |
| **SSRF: Loopback & Private IPv4/IPv6** | Fully Implemented | Verified (Tests 17-20) | Ready |
| **SSRF: Cloud Metadata (AWS/GCP/Azure)** | Fully Implemented | Verified (Tests 21-22) | Ready |
| **SSRF: Alternate IP Notations** | Fully Implemented | Verified (Test 23) | Ready |
| **SSRF: Port Filtering (80, 443, 8080, 8443)** | Fully Implemented | Verified (Tests 24-25) | Ready |
| **Redirect Hop-by-Hop SSRF Validation** | Fully Implemented | Verified (Tests 6-9) | Ready |
| **Redirect Loop & Scope Control** | Fully Implemented | Verified (Tests 7-8) | Ready |
| **Sitemap Decompression Bomb Limits** | Fully Implemented | Verified (Test 6, Adv) | Ready |
| **Robots.txt Size Enforcements** | Fully Implemented | Verified (Test 7, Adv) | Ready |
| **URL Credential Stripping** | Fully Implemented | Verified (Test 2, Adv) | Ready |
| **Error Summary Credential Redaction** | Fully Implemented | Verified (Test 5, Adv) | Ready |
| **DNS-to-Connection Pinning (Rebinding)** | Code Analysis Only | **UNVERIFIED (Transport)** | Requires Network Egress Proxy |
| **Headless Browser Network Isolation** | Route Interception | **UNVERIFIED (Kernel/TCP)**| Disabled by Default |

---

## 4. Unresolved Risks & Conditions for Public Deployment

While the application-layer code is strictly hardened and thoroughly verified, two fundamental limitations cannot be guaranteed solely within Python application process space:

### 1. DNS Rebinding / TOCTOU Race Condition at Transport Layer
- **Status:** **UNVERIFIED AT TRANSPORT LEVEL**
- **Analysis:** `AsyncFetcher.get` relies on `curl_cffi` (libcurl). While `validate_and_resolve_url()` verifies DNS immediately prior to the connection, libcurl establishes its own socket connection and resolves DNS independently unless pinned via `CURLOPT_RESOLVE`. `curl_cffi` does not expose `resolve` parameters on its request methods.
- **Condition for Public Deployment:** The crawler worker containers must be deployed behind an **isolated egress forward proxy** (e.g. Squid, Envoy, or Smokescreen) configured to resolve DNS at the proxy boundary and block any egress connection to RFC 1918, RFC 3927, or cloud metadata addresses at the TCP SYN handshake level.

### 2. Headless Browser (Dynamic Rendering) Isolation
- **Status:** **UNVERIFIED AT KERNEL/TCP LEVEL**
- **Analysis:** `safe_browser_setup()` uses Playwright `page.route` to intercept HTTP/HTTPS requests. However, Chromium sub-processes, WebSockets, or background service workers can bypass application-level JavaScript/Playwright routing, and Chromium resolves DNS internally.
- **Condition for Public Deployment:**
  - `ALLOW_BROWSER_FALLBACK` is disabled by default in production (`False`).
  - When dynamic rendering is required in production, the Chromium browser process must run inside a **sandboxed container with network namespace restrictions** (no default route to internal VPC CIDRs, egress routed strictly through the egress proxy).
