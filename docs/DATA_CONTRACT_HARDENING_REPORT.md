# Auralyt Data Contract Hardening Report

## Scope and Baseline

- Starting commit: `faa623f`
- The requested `cross_site_ground_truth_audit_report.md` was not present in the repository. Existing audit tests and Engine 1/2/3 documents were used instead.
- Baseline test suite: `142 passed`.
- Final implementation commit is recorded in the completion message and `git log`.

## Confirmed Risks and Fixes

- A refresh incremented `Brand.profile_version` before completion, allowing downstream engines to read a version with no completed snapshot. `ProfileRun.profile_version` now pins the run, and Engine 2/3 select completed prompt/profile versions.
- Reprofiling used a coarse string key and deleted pending facts. Facts now have stable category-aware `fact_key` values, supporting evidence, stale/superseded lifecycle flags, and last-seen timestamps. Warning or failed-page runs do not retire the last clean snapshot.
- Equivalent product and pricing claims could lose alternate provenance. Extraction now merges equivalent claims while retaining supporting source URL/snippet pairs.
- Materially different values receive a new key and do not inherit human review. Same-key reaffirmations retain confirmation or rejection state.
- Manually supplied evidence could point outside the profiled brand domain. The API now rejects off-domain source URLs.

## Contract and Migration

Added `profile_runs.profile_version` and `brand_facts.fact_key`, `supporting_evidence`, `is_superseded`, `is_stale`, `last_seen_at`, and `superseded_at`. Existing rows remain readable: nullable identity/provenance fields fall back to deterministic calculation, and lifecycle defaults are applied on restart. Migration: `f2a1b7c9d4e6_harden_ground_truth_lifecycle.py`. Clean SQLite migration execution succeeded through Alembic head.

Before: a repeated extraction was compared using `(fact_type, str(fact_value))` and could delete unreviewed facts.

After: `pricing:...amount,currency,unit,billing_basis,associated_product...` identifies units and association; duplicate sources are retained in `supporting_evidence`, while `user_confirmed` and `is_rejected` remain unchanged.

## Crawl and Runtime Evidence

- Existing bounded crawl tests cover page, depth, section, concurrency, timeout, response-size, decompression, aggregate-byte, sitemap, redirect, retry, and failure paths.
- Live `https://example.com` run: `completed_with_warnings`, 1 discovered, 1 attempted, 1 succeeded, 0 failed, 577 aggregate bytes, 1.41 seconds. The warning was `No accessible or valid sitemaps found.`
- Google Chrome verification: dashboard loaded at `http://127.0.0.1:8000/`; `/health` returned HTTP 200. The title has an existing replacement-character encoding defect.

## Verification

- Final suite: `145 passed`.
- Added deterministic contract tests for stable identity, provenance retention, lifecycle defaults, and pricing-unit separation.
- Engine 2 prompt records retain `profile_version`, `provenance_fact_ids`, and `grounding_evidence`; Engine 3 scans retain their selected prompt version and historical prompt association.

## Limitations and Next Phase

- No paid LLM calls or unstable external sites were used in tests.
- No authenticated or JavaScript-heavy live site was profiled in this environment.
- Tenant authentication/authorization is not implemented in the repository, so organization isolation beyond brand-ID checks cannot be fully proven here.
- The dashboard title encoding issue should be fixed separately.
