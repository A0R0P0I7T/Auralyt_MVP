# Engine 2 and Engine 3 Validity Audit

## Baseline

- Starting commit: `d5d5f94`
- Starting worktree: pre-existing unstaged Engine 1/crawler/extractor/frontend audit changes and untracked cross-site audit tests were preserved and not staged.
- Baseline: `145 passed`.
- Final audited suite: `151 passed`.

## Confirmed Findings

- Engine 2 could persist LLM candidates with empty or foreign provenance IDs. Deterministic validation now rejects unknown fact IDs, requires relevant fact provenance for evidence-backed dimensions, validates target products/audiences, and gives ungrounded candidates a grounding score of `0.0`.
- Prompt listing and coverage used mutable `Brand.profile_version`, while generation used the completed profile snapshot. They now resolve the same completed snapshot version.
- Force regeneration could persist duplicate prompt text across runs. Existing normalized prompt text is now excluded from later persistence for the same brand/version.
- Planner provenance matching used broad substring matching, causing a brand name to match unrelated facts. Matching now uses category-specific fact types and structured values.
- Engine 3 accepted prompt IDs at scan creation but did not revalidate brand/version at execution. Execution now rejects missing, cross-brand, or cross-version inputs.
- Provider-grounding citations and URLs merely present in response text were conflated. They are now persisted and exposed separately while retaining the combined compatibility field.
- Scans with zero successful observations reported `0` rates and score. They now report `null` metrics; `prompts_completed` and `prompts_failed` remain the observation counts.
- URL-form brand domains were parsed incorrectly by the evaluator. Host parsing now handles both host-only and URL-form inputs.

## Measurements

Deterministic populated-profile evaluation set:

- 20 planned, 20 valid, 20 unique prompts.
- Duplicate rate: `0.0` after in-run deduplication.
- Unknown provenance IDs: `0`.
- Product-specific prompts lacking relevant fact provenance: `0`.
- Sparse profiles continue to suppress pricing and audience categories when those dimensions are absent from the contract.

An existing persisted Linear profile contained 30 historical prompts, including duplicate text from earlier force-regeneration runs. The corrected path prevents additional duplicates; existing rows are not silently deleted.

## Engine 3 Runtime Evidence

- Provider: `mock`
- Model: `mock-evaluator-v1`
- Profile version: `1`
- Scan: 3 selected, 3 completed, 0 failed.
- Mention rate: `1.0`
- Recommendation rate: `0.333`
- Visibility score: `70.0`
- Response citations and provider citations were returned as separate API fields. The mock provider's URLs were response-text URLs, not provider grounding citations.
- Zero-success deterministic regression: status `failed`, completed `0`, and score/rates `null`.
- Live Gemini validation was not performed; no paid provider call was made.

## Version Integrity

Generation, prompt listing, coverage, scan creation, and scan execution now use the completed profile/prompt version. Existing prompt and scan rows retain their stored version and IDs. Rejected, stale, and superseded facts are excluded by the Engine 1 profile snapshot before normalization.

## Verification

- Google Chrome loaded the running dashboard at `http://127.0.0.1:8000/` and `/health` returned HTTP 200.
- Chrome selected the existing populated Linear brand, opened Prompt Intelligence, and opened AI Visibility. API results matched persisted scan/provider/version values.
- Alembic upgrade through `a4c8e1f6b2d0` succeeded on clean SQLite.
- `compileall` passed. Ruff and mypy are not installed; no configured lint/type command is available.

## Remaining Limitations

- No live Gemini credentials were available or used.
- Existing historical prompt duplicates require a separate maintenance/backfill decision; this change prevents new duplicates.
- The worktree still contains unrelated pre-existing unstaged changes and tests; they were not committed.
- Existing frontend encoding displays replacement characters in the title and some persisted historical text.
