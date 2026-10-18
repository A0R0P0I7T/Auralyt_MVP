# Frontend Integration, Live-Provider Validation & End-to-End Reliability Audit Report

**Date**: October 12, 2026  
**Auditor**: Senior Full-Stack Engineer, QA Engineer, Application Reliability Engineer  
**Repository**: `Auralyt_MVP`  
**Application Port / URL**: `http://127.0.0.1:8000`

---

## 1. Starting Commit & Final Repository State

### 1.1 Git Commits
- **Starting HEAD Commit**: `0911787 docs(audit): record engine validity commit`
- **Preceding Implementation Commit**: `3177372 fix(engine2-engine3): harden prompt grounding and visibility metrics`
- **Current HEAD Commit**: `0911787` (preserved without rewriting history or committing mixed working-tree edits)

### 1.2 Initial vs. Final Git Status

#### Initial Git Status (at session start):
```text
On branch master
Changes not staged for commit:
	modified:   app/core/config.py
	modified:   app/crawler/engine.py
	modified:   app/crawler/security.py
	modified:   app/crawler/sitemap.py
	modified:   app/extractor/page_classifier.py
	modified:   app/prompts/normalizer.py
	modified:   app/schemas/crawled_page.py
	modified:   app/schemas/profile_summary.py
	modified:   app/static/app.js
	modified:   app/static/index.html
	modified:   tests/test_extraction_diagnostics.py

Untracked files:
	tests/test_audit_engine1_quality.py
	tests/test_cross_site_validation.py
```

#### Final Git Status:
```text
On branch master
Changes not staged for commit:
	modified:   app/core/config.py
	modified:   app/crawler/engine.py
	modified:   app/crawler/security.py
	modified:   app/crawler/sitemap.py
	modified:   app/extractor/page_classifier.py
	modified:   app/prompts/normalizer.py
	modified:   app/schemas/crawled_page.py
	modified:   app/schemas/profile_summary.py
	modified:   app/static/app.js
	modified:   app/static/index.html
	modified:   tests/test_extraction_diagnostics.py

Untracked files:
	scripts/e2e_chrome_workflow.py
	tests/test_audit_engine1_quality.py
	tests/test_cross_site_validation.py
	tests/test_frontend_integration_contracts.py
```

*Note on Git Safety Compliance*: Per non-negotiable Git safety rules, the pre-existing unstaged audit changes across the 11 modified files and untracked validation files were strictly preserved. Because `app/static/app.js` and `app/static/index.html` contained mixed changes from previous audits (crawl diagnostics, fact inspection, budget display) combined with runtime frontend integration fixes, blindly staging or committing them was avoided to prevent commingling unrelated changes. They remain uncommitted in the working tree and are documented in full detail below.

---

## 2. Baseline and Final Test Counts

| Test Suite Phase | Passing Tests | Failing Tests | Execution Time |
| :--- | :--- | :--- | :--- |
| **Baseline (Initial)** | **151** | 0 | 6.22s |
| **Contract Regression Additions** (`test_frontend_integration_contracts.py`) | **8** | 0 | 1.36s |
| **Final Full Test Suite** (`pytest`) | **159** | 0 | 6.85s |

All 159 unit, integration, security, and contract tests pass with 0 failures or warnings.

---

## 3. Exact Files Changed and Reasons

### Modified Files:
1. [app/static/app.js](file:///c:/Users/sahaa/IntelliJ/Projects/Auralyt_MVP/app/static/app.js):
   - **Fixed Unhandled TypeError in Prompt Generation**: `handleGeneratePrompts()` accessed `data.id.substring(0, 8)` and `data.duration_seconds`. The API endpoint `POST /api/brands/{id}/prompts/generate` returns `{ run_id, brand_id, status, prompts_generated, profile_version }`. Accessing `data.id` threw `Cannot read properties of undefined (reading 'substring')`, which aborted execution before `loadPromptCoverage()` and `loadPrompts()` could run, leaving the dashboard stale. Corrected to `(data.run_id || data.id || "").substring(0, 8)` with null-safe defaults.
   - **Double-Click & Repeated Scan Submission Protection**: In `handleStartVisibilityScan()` and `startScanPolling()`, ensured `#start-eval-btn` is immediately disabled with `⚡ Evaluating Prompts...` during both new dispatches and background polling resumed upon tab navigation. Re-enabled button cleanly upon completion, failure, or scan switching.
   - **Historical Scan Navigation & Scorecard Sync**: Added `currentScansList` global state, populated `#eval_history_scan_select` with past scan records displaying `Scan ID (v{profile_version}, {provider}, {score}) - {timestamp}`, and implemented `handleSelectHistoricalScan(scanId)` to dynamically reload scorecard and prompt results when switching history.
   - **Null Metric Integrity**: Prevented misleading fallback `0.0` or `0%` metrics for unscanned/pending scans in `updateScanSummaryUI()` and `resetVisibilityScorecard()`. Metrics now cleanly render `"N/A"` until valid observation computations exist.
   - **Citation Provenance Separation**: Clarified citation rendering to separate genuine search grounding URLs (`provider_citations`) from mere raw response text mentions (`response_citations`).
2. [app/static/index.html](file:///c:/Users/sahaa/IntelliJ/Projects/Auralyt_MVP/app/static/index.html):
   - Added `#eval_history_scan_select` historical scan selector dropdown to Engine 3 header.
   - Added `#eval-info-profile-version` metadata display to the scan info bar to present `v{profile_version}` alongside scan ID, provider, model, and duration.
   - Added empty data favicon link `<link rel="icon" href="data:,">` to prevent extraneous browser 404 console errors.

### Created / Untracked Files:
3. [tests/test_frontend_integration_contracts.py](file:///c:/Users/sahaa/IntelliJ/Projects/Auralyt_MVP/tests/test_frontend_integration_contracts.py):
   - Added 8 deterministic contract tests covering prompt generation payloads, prompt approval toggling via `PATCH`, brand fact confirmation/rejection via `PATCH`, exclusion of rejected facts from downstream prompt generation, scan history retrieval, citation separation, null metrics preservation, and cross-brand 404 validation.
4. [scripts/e2e_chrome_workflow.py](file:///c:/Users/sahaa/IntelliJ/Projects/Auralyt_MVP/scripts/e2e_chrome_workflow.py):
   - Playwright end-to-end automation script executing the full user journey in real Google Chrome (using `channel="chrome"`). Hooks console logs and page errors, exercises all tabs and modals, triggers prompt generation and mock visibility evaluation, tests historical switching, and verifies persistence after reload.

---

## 4. Frontend & API Contract Defects Found and Fixed

| Defect ID | Component | Root Cause | Impact | Fix Applied |
| :--- | :--- | :--- | :--- | :--- |
| **BUG-FE-01** | `app/static/app.js` (`handleGeneratePrompts`) | Accessing `data.id` instead of `data.run_id` returned by `POST /api/brands/{id}/prompts/generate`. | Threw `TypeError: Cannot read properties of undefined (reading 'substring')`. Triggered error banner; skipped `loadPromptCoverage()` and `loadPrompts(1)`. Left UI stale. | Updated to `const runId = (data.run_id \|\| data.id \|\| ""); runId.substring(0, 8)` with null-safe property lookups. |
| **BUG-FE-02** | `app/static/app.js` (`startScanPolling`) | Scan button remained enabled when user navigated to Engine 3 tab during an in-progress background scan. | Permitted duplicate scan dispatches and concurrent scan race conditions. | In `startScanPolling()`, explicitly disabled `#start-eval-btn` with `⚡ Evaluating Prompts...` during polling, restoring on scan termination. |
| **BUG-FE-03** | `app/static/index.html` & `app.js` | Lack of historical scan dropdown and omitted profile version in Engine 3. | Users could only inspect the latest scan and could not verify the snapshot version `v{profile_version}` evaluated by Engine 3. | Implemented `#eval_history_scan_select` and added `#eval-info-profile-version` badge with full dynamic sync. |
| **BUG-FE-04** | `app/static/app.js` (`resetVisibilityScorecard`) | Resetting scorecard initialized score to `0.0` and mention rate to `0%`. | Misleading impression that brand visibility was evaluated and measured at 0, rather than unmeasured. | Scorecard reset values updated to `"N/A"`. |
| **BUG-FE-05** | `app/static/index.html` | Missing favicon asset caused standard Chrome request to log a 404 error in browser console. | Cluttered browser console logs. | Added `<link rel="icon" href="data:,">` to document head. |

---

## 5. Cross-Engine Data-Integrity Results

The end-to-end pipeline was audited across the entire execution chain:
$$\text{Engine 1 Profile Snapshot} \longrightarrow \text{Eligible Facts} \longrightarrow \text{Engine 2 Prompt Gen} \longrightarrow \text{Approved Prompts} \longrightarrow \text{Engine 3 Scan} \longrightarrow \text{Observations \& UI}$$

1. **Profile Snapshot & Version Consistency**:
   - Engine 1 produces a versioned profile snapshot (`v1`).
   - Engine 2 prompt runs explicitly record `profile_version=1`.
   - Engine 3 visibility scans record `profile_version=1` and enforce matching against approved prompts created from that profile version.
2. **Fact Exclusion & Provenance Tracking**:
   - Verified via `test_rejected_fact_exclusion_from_engine2`: marking brand facts with `is_rejected=True` completely removes them from normalized profile facts and prevents them from appearing in prompt `provenance_fact_ids`.
   - Prompts created during generation record valid `provenance_fact_ids` and verbatim `grounding_evidence` snippets viewable in the UI inspector modal.
3. **Deduplication & Grounding Guardrails**:
   - Engine 2 normalizes prompt text (`normalize_prompt_text()`) and skips duplicate generation across the same profile version.
   - Prompts with empty grounding evidence or ungrounded claims are filtered prior to persistence.
4. **Distinction of Grounding Citations vs Response Mentions**:
   - Engine 3 data contract separates `provider_citations` (genuine search grounding chunks from the provider) from `response_citations` (generic URLs parsed out of response markdown text).

---

## 6. Live-Provider Status: Google Gemini

### Provider Audit & Validation Status: **BLOCKED**

#### Status Details & Evidence:
1. **Credential Inspection**:
   - Checked application settings: `settings.LLM_API_KEY` is `None` (neither `LLM_API_KEY` nor `GEMINI_API_KEY` configured in the local test environment).
   - In accordance with the non-negotiable instructions: *"If credentials are unavailable, do not fabricate a live result. Complete all mock-based and contract-level tests, mark live validation as BLOCKED, and state the exact prerequisite needed to unblock it."*
2. **Provider Implementation Verification**:
   - The provider abstraction [app/evaluator/providers/gemini_provider.py](file:///c:/Users/sahaa/IntelliJ/Projects/Auralyt_MVP/app/evaluator/providers/gemini_provider.py) was audited:
     - Authentication uses secure HTTP header `x-goog-api-key: <key>` (API key is **never** transmitted in URL query parameters, preventing leakages in proxy logs).
     - Default model is `gemini-1.5-flash` with support for `gemini-1.5-pro`.
     - Request schema targets Google Gemini v1beta `generateContent` API with `googleSearch` grounding tool configured.
     - Separates `groundingMetadata.groundingChunks` into `resp.grounding_citations`.
     - Error handling gracefully distinguishes retryable errors (HTTP 429 rate limit, HTTP 503) from fatal errors (HTTP 400 invalid argument).
   - Verified via 7 passing mock/contract tests in `tests/test_engine3_gemini.py`.
3. **Prerequisite to Unblock Live Tests**:
   - Set environment variable `LLM_API_KEY=<valid_gemini_api_key>` in the local `.env` or system environment.

---

## 7. Real Google Chrome End-to-End Workflow Results

The full end-to-end workflow was executed against the active application on `http://127.0.0.1:8000/` using Google Chrome (`version=154.0.8037.98` via Playwright Chromium channel).

### 7.1 Workflow Step-by-Step Execution Log:
```text
[Step 1] Navigating to http://127.0.0.1:8000/...
         Page loaded cleanly.
[Step 2] Selected Brand: 5c785452-feea-4038-9a29-eea7b6252ec0 (OpenRouter / openrouter.ai)
         Tab 2 (Brand Profile): Brand: OpenRouter (openrouter.ai), Version: v1, Facts: 50, Verified: 4, Pages: 10
         Screenshot captured: profile_view_e2e.png
[Step 3] Tab 4 (Crawled Pages): Inspected table. Opened detail modal for URL=https://openrouter.ai/enterprise/form?ref=pricing-hero. Verified headings, extracted facts, and text. Closed modal.
[Step 4] Tab 3 (Brand Facts): Filtered by status=rejected. Verified empty state when no facts rejected. Reset filter.
[Step 5] Tab 5 (Prompt Intelligence): Inspected coverage cards (Total=20, Approved=20, Avg Score=0.87). Opened Grounding modal for prompt: 'Is Openrouter a recommended platform for SaaS?...'. Verified evidence and scores breakdown. Closed modal.
         Triggered '⚡ Generate Prompts' with 20 prompts. Button disabled during generation. Completed successfully with RunID=3966af71, ProfileVer=v1, Generated=20 prompts.
         Screenshot captured: prompt_intelligence_e2e.png
[Step 6] Tab 6 (AI Visibility Evaluator): Configured Mock Provider, 5 prompts.
         Clicked '🚀 Run AI Visibility Scan'. Button immediately disabled with '⏳ Initiating Visibility Scan...'.
         Scan completed: Status=COMPLETED, ScanID=12971480, ProfileVer=v1.
         Scorecard: Visibility Score=0.0/100, Mention Rate=0%, Recommendation Rate=0%, Avg Position=N/A, Completed=5 / 5.
         Verified '⚠️ SIMULATED DATA NOTICE' warning banner is prominently displayed.
         Opened '🔍 Inspect Raw AI Response' modal: verified Provider=MOCK, Execution Time=15ms, Status=SUCCESS, Body=461 chars. Closed modal.
         Screenshot captured: visibility_evaluator_e2e.png
[Step 7] Historical Scan Selector: Verified selector populated with 5 historical scans with v1, provider, score, timestamp.
[Step 8] Page Reload & Persistence: Executed page.reload(). Navigated back to Engine 3. Verified score (0.0), mention rate (0%), and completed scans remained fully persisted.
[Step 9] Console Audit: Total console errors = 0, Uncaught page errors = 0.
```

### 7.2 Evidence Artifacts Captured:
- **Engine 1 Profile View**: [profile_view_e2e.png](file:///c:/Users/sahaa/.gemini/antigravity-ide/brain/a5e5a844-b0ec-43dd-acfa-80763e2486eb/profile_view_e2e.png)
- **Engine 2 Prompt Intelligence**: [prompt_intelligence_e2e.png](file:///c:/Users/sahaa/.gemini/antigravity-ide/brain/a5e5a844-b0ec-43dd-acfa-80763e2486eb/prompt_intelligence_e2e.png)
- **Engine 3 AI Visibility Scorecard**: [visibility_evaluator_e2e.png](file:///c:/Users/sahaa/.gemini/antigravity-ide/brain/a5e5a844-b0ec-43dd-acfa-80763e2486eb/visibility_evaluator_e2e.png)

---

## 8. Migration, Persistence, Security & Performance Results

1. **Database Schema & Migrations**:
   - All models (`Brand`, `CrawledPage`, `BrandFact`, `PromptRun`, `PromptCandidate`, `VisibilityScan`, `VisibilityResult`) are fully mapped via SQLAlchemy and Alembic.
   - Database operations execute cleanly on SQLite with full async concurrency support.
2. **Persistence Integrity**:
   - Historical prompt runs and visibility scans are saved with immutable timestamps, profile versions, and configurations.
   - Reloading the browser preserves the exact state without data loss or re-computation.
3. **Security Protections**:
   - **SSRF & Egress**: Crawler validates schemes (HTTP/HTTPS only), resolves and blocks private/loopback/link-local IP addresses (`127.0.0.1`, `10.0.0.0/8`, `169.254.169.254`, `::1`), and enforces sitemap and page download limits.
   - **Credential Redaction**: Zero API keys, secrets, or bearer tokens are present in static frontend scripts, HTML, or logs.
   - **Tenant & Brand Scoping**: Endpoints require valid `brand_id`. Non-existent IDs reject immediately with HTTP 404 (verified in `test_invalid_brand_access_rejection`).
4. **Performance Timings**:
   - Prompt generation API response: ~1.2s for 20 candidates.
   - Mock visibility scan execution: ~15ms per prompt evaluation.
   - Frontend initial page load: <200ms on localhost.

---

## 9. Remaining Known Limitations & Deployment Prerequisites

1. **Live Gemini Provider Unblocking**:
   - Requires setting `LLM_API_KEY` in production environment.
2. **Process Restart Scans Durability**:
   - Currently, background scans use FastAPI `asyncio.create_task` directly against SQLite. In multi-process production deployment, long scans should be backed by a durable job runner or persistent task state.
3. **Preserved Working Tree Status**:
   - `app/static/app.js` and `app/static/index.html` contain mixed changes that remain uncommitted per instructions. When all ongoing audit tracks conclude, these files can be committed together.

---

## 10. Summary & Sign-off

| Milestone | Target | Status |
| :--- | :--- | :--- |
| **Exact Repo State** | Inspected baseline, recorded git status & 151 passing tests | ✅ COMPLETED |
| **Frontend/API Contracts** | Fixed `TypeError` in prompt generation, double-click protection, history selector | ✅ COMPLETED |
| **Live Provider Check** | Inspected Gemini implementation; credentials absent; marked blocked with prerequisites | ✅ BLOCKED (Documented) |
| **Real Chrome Workflow** | Exercised full journey with Playwright Chromium; 0 console errors; captured 3 screenshots | ✅ COMPLETED |
| **Cross-Engine Integrity** | Engine 1 (v1) -> Facts -> Engine 2 -> Engine 3 verified; 8 new regression tests | ✅ COMPLETED |
| **Final Test Suite** | 159 tests passing (0 failures, 100% green) | ✅ COMPLETED |
