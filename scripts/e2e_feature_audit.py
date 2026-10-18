"""Comprehensive End-to-End Feature-by-Feature Browser Audit using Google Chrome.
Exercises Engine 1, Engine 2, Engine 3, Fact Lifecycle, Pricing Intelligence,
Prompt Editing, Visibility Scanning, SSRF Security Rejection, and State Persistence.
"""
import os
import sys
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\sahaa\.gemini\antigravity-ide\brain\a5e5a844-b0ec-43dd-acfa-80763e2486eb"
BASE_URL = "http://127.0.0.1:8000"

def run_comprehensive_audit():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    print("=" * 80)
    print("STARTING COMPLETE FEATURE-BY-FEATURE GOOGLE CHROME AUDIT")
    print(f"Target URL: {BASE_URL}")
    print("=" * 80)

    console_logs = []
    page_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        # ----------------------------------------------------------------------
        # 1. NAVIGATION & BRAND SELECTION
        # ----------------------------------------------------------------------
        print("\n[STEP 1] Navigating to Home & Verifying Active Brand Selector...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        brand_select = page.locator("#global-brand-select")
        selected_brand = brand_select.input_value()
        assert selected_brand, "No active brand selected"
        print(f"Active Brand ID: {selected_brand}")

        # ----------------------------------------------------------------------
        # 2. WORKFLOW A: BRAND PROFILE (ENGINE 1)
        # ----------------------------------------------------------------------
        print("\n[STEP 2] Auditing Brand Profile Dashboard...")
        page.click("#nav-profile")
        page.wait_for_selector("#profile-brand-name:not(:empty)")
        time.sleep(0.5)

        bname = page.locator("#profile-brand-name").inner_text()
        domain = page.locator("#profile-domain").inner_text()
        ver = page.locator("#profile-version-badge").inner_text()
        facts_count = page.locator("#profile-stat-facts").inner_text()
        verified_count = page.locator("#profile-stat-verified").inner_text()
        pages_count = page.locator("#profile-stat-pages").inner_text()
        print(f"Profile Loaded: {bname} ({domain}) | Version: {ver} | Facts: {facts_count} | Verified: {verified_count} | Pages: {pages_count}")

        profile_shot = os.path.join(ARTIFACT_DIR, "audit_workflow_a_profile.png")
        page.screenshot(path=profile_shot, full_page=True)
        print(f"Captured: {profile_shot}")

        # ----------------------------------------------------------------------
        # 3. WORKFLOW B: PRICING INTELLIGENCE & SEMANTIC CLASSIFICATION
        # ----------------------------------------------------------------------
        print("\n[STEP 3] Auditing Pricing Intelligence Display...")
        page.locator("#pricing-list").scroll_into_view_if_needed()
        time.sleep(0.5)

        pricing_text = page.locator("#pricing-list").inner_text()
        # Verify absence of defect symptoms
        assert "25000.0 (monthly)" not in pricing_text, "Defect symptom '25000.0 (monthly)' found in pricing display!"
        assert "USD 25000" not in pricing_text, "Defect symptom 'USD 25000' found in pricing display!"
        assert "0.042 (monthly)" not in pricing_text, "Defect symptom '0.042 (monthly)' found in pricing display!"
        print("Verified: No $25,000 monthly subscription or $0.042 monthly plan found.")

        # Verify correct semantics present
        assert "Free ($0)" in pricing_text, "Free ($0) tier not rendered correctly"
        assert "5.5% fee" in pricing_text, "Platform fee not rendered correctly"
        assert "inference allowance" in pricing_text, "Inference allowance not rendered correctly"
        assert "/ 1M output tokens" in pricing_text, "Token usage rates not rendered correctly"
        print("Verified: Free tier, Platform fee, Inference allowance, and Token usage rates present and correctly formatted.")

        pricing_shot = os.path.join(ARTIFACT_DIR, "audit_workflow_b_pricing.png")
        page.screenshot(path=pricing_shot)
        print(f"Captured: {pricing_shot}")

        # Inspect Evidence modal for allowance
        first_ev_btn = page.locator("#pricing-list button:has-text('Inspect Evidence')").first
        if first_ev_btn.is_visible():
            first_ev_btn.click()
            page.wait_for_selector("#evidence-modal", state="visible")
            time.sleep(0.5)
            snippet = page.locator("#evidence-snippet").inner_text()
            print(f"Evidence Modal Opened: Snippet='{snippet[:65]}...'")
            ev_shot = os.path.join(ARTIFACT_DIR, "audit_workflow_b_evidence_modal.png")
            page.screenshot(path=ev_shot)
            print(f"Captured: {ev_shot}")
            page.click("#evidence-modal .close-btn")
            page.wait_for_selector("#evidence-modal", state="hidden")

        # ----------------------------------------------------------------------
        # 4. WORKFLOW C: FACT VERIFICATION & STATUS LIFECYCLE
        # ----------------------------------------------------------------------
        print("\n[STEP 4] Auditing Fact Verification & Rejection/Confirmation Lifecycle...")
        page.click("#nav-facts")
        page.wait_for_selector("#facts-container")
        time.sleep(0.5)

        # Check total facts
        fact_cards = page.locator("#facts-container .fact-item").all()
        print(f"Total Fact Cards displayed: {len(fact_cards)}")
        assert len(fact_cards) > 0, "No fact cards loaded"

        # Test Rejecting a Fact
        first_reject_btn = page.locator("#facts-container .fact-item:first-child button:has-text('✕ Reject')")
        if first_reject_btn.is_visible():
            first_reject_btn.click()
            time.sleep(1)
            print("Clicked '✕ Reject' on first fact card.")

            # Filter by rejected
            page.select_option("#fact-filter-status", "rejected")
            time.sleep(0.5)
            rejected_cards = page.locator("#facts-container .fact-item").all()
            print(f"Rejected Facts Filter: {len(rejected_cards)} rejected facts found.")
            assert len(rejected_cards) >= 1, "Rejected fact was not found in rejected filter"

            # Restore the fact
            restore_btn = page.locator("#facts-container .fact-item:first-child button:has-text('↺ Restore')")
            if restore_btn.is_visible():
                restore_btn.click()
                time.sleep(1)
                print("Clicked '↺ Restore' on rejected fact.")

        # Reset filter
        page.select_option("#fact-filter-status", "")
        time.sleep(0.5)

        facts_shot = os.path.join(ARTIFACT_DIR, "audit_workflow_c_facts.png")
        page.screenshot(path=facts_shot)
        print(f"Captured: {facts_shot}")

        # ----------------------------------------------------------------------
        # 5. WORKFLOW D: PROMPT INTELLIGENCE & EDITING (ENGINE 2)
        # ----------------------------------------------------------------------
        print("\n[STEP 5] Auditing Prompt Intelligence (Engine 2)...")
        page.click("#nav-prompts")
        page.wait_for_selector("#cov-total-prompts")
        time.sleep(0.5)

        # Check existing prompts
        cov_tot = page.locator("#cov-total-prompts").inner_text()
        cov_appr = page.locator("#cov-approved-prompts").inner_text()
        cov_score = page.locator("#cov-avg-score").inner_text()
        print(f"Current Prompts Matrix: Total={cov_tot}, Approved={cov_appr}, Avg Score={cov_score}")

        # Test Grounding Modal
        ground_btn = page.locator("#prompts-table-body tr:first-child button:has-text('Grounding')").first
        if ground_btn.is_visible():
            ground_btn.click()
            page.wait_for_selector("#prompt-evidence-modal", state="visible")
            time.sleep(0.5)
            p_text = page.locator("#pe-prompt-text").inner_text()
            p_score = page.locator("#pe-score").inner_text()
            print(f"Grounding Modal: Text='{p_text[:50]}...', Score={p_score}")
            ground_shot = os.path.join(ARTIFACT_DIR, "audit_workflow_d_prompt_grounding.png")
            page.screenshot(path=ground_shot)
            print(f"Captured: {ground_shot}")
            page.click("#prompt-evidence-modal .close-btn")
            page.wait_for_selector("#prompt-evidence-modal", state="hidden")

        # Test Editing a Prompt
        edit_btn = page.locator("#prompts-table-body tr:first-child button[title='Edit']").first
        if edit_btn.is_visible():
            edit_btn.click()
            page.wait_for_selector("#edit-prompt-modal", state="visible")
            time.sleep(0.5)
            cur_q = page.locator("#edit-prompt-text").input_value()
            new_q = cur_q + " [VERIFIED]" if "[VERIFIED]" not in cur_q else cur_q
            page.fill("#edit-prompt-text", new_q)
            page.click("#edit-prompt-modal button[type='submit']")
            page.wait_for_selector("#edit-prompt-modal", state="hidden")
            time.sleep(1)
            print(f"Edited prompt question text to include '[VERIFIED]'.")

        prompt_shot = os.path.join(ARTIFACT_DIR, "audit_workflow_d_prompts.png")
        page.screenshot(path=prompt_shot)
        print(f"Captured: {prompt_shot}")

        # ----------------------------------------------------------------------
        # 6. WORKFLOW E: AI VISIBILITY EVALUATION (ENGINE 3)
        # ----------------------------------------------------------------------
        print("\n[STEP 6] Auditing AI Visibility Evaluator (Engine 3)...")
        page.click("#nav-evaluator")
        page.wait_for_selector("#stat-visibility-score")
        time.sleep(0.5)

        page.select_option("#eval_provider_select", "mock")
        page.select_option("#eval_max_prompts", "5")
        page.click("#start-eval-btn")

        # Wait for scan completion
        page.wait_for_function("document.getElementById('start-eval-btn').disabled === false", timeout=35000)
        time.sleep(1)

        eval_score = page.locator("#stat-visibility-score").inner_text()
        eval_completed = page.locator("#stat-eval-completed").inner_text()
        eval_scan_id = page.locator("#eval-info-id").inner_text()
        print(f"Scan Completed: Scan ID={eval_scan_id} | Score={eval_score}/100 | Completed={eval_completed}")

        # Verify Mock Warning Banner
        mock_banner = page.locator("#eval-mock-banner")
        assert mock_banner.is_visible(), "Mock notice banner should be displayed"
        print("Verified: Mock provider banner visible.")

        # Inspect Raw AI Response Modal
        raw_btn = page.locator("#eval-results-container button:has-text('Inspect Raw AI Response')").first
        if raw_btn.is_visible():
            raw_btn.click()
            page.wait_for_selector("#raw-response-modal", state="visible")
            time.sleep(0.5)
            meta_info = page.locator("#raw-response-meta").inner_text()
            print(f"Raw Response Modal: {meta_info}")
            raw_shot = os.path.join(ARTIFACT_DIR, "audit_workflow_e_raw_response.png")
            page.screenshot(path=raw_shot)
            print(f"Captured: {raw_shot}")
            page.click("#raw-response-modal .close-btn")
            page.wait_for_selector("#raw-response-modal", state="hidden")

        eval_shot = os.path.join(ARTIFACT_DIR, "audit_workflow_e_evaluator.png")
        page.screenshot(path=eval_shot)
        print(f"Captured: {eval_shot}")

        # ----------------------------------------------------------------------
        # 7. WORKFLOW F: ERROR HANDLING & SSRF PROTECTION
        # ----------------------------------------------------------------------
        print("\n[STEP 7] Auditing Error Handling & SSRF Security Guardrails...")
        page.click("button:has-text('Start Profiling')")
        page.wait_for_selector("#onboard-form")
        time.sleep(0.5)

        # Attempt to onboard with private loopback SSRF URL
        page.fill("#website_url", "http://127.0.0.1:8000/evil")
        page.fill("#business_name", "Loopback Malicious Test")
        page.click("#onboard-form button[type='submit']")
        time.sleep(1.5)

        err_box = page.locator("#onboard-error")
        assert err_box.is_visible(), "SSRF error box was not displayed for 127.0.0.1!"
        err_msg = err_box.inner_text()
        print(f"SSRF Protection Verified: Rejection message='{err_msg}'")
        ssrf_shot = os.path.join(ARTIFACT_DIR, "audit_workflow_f_ssrf_rejection.png")
        page.screenshot(path=ssrf_shot)
        print(f"Captured: {ssrf_shot}")

        # ----------------------------------------------------------------------
        # 8. WORKFLOW G: PERSISTENCE ACROSS FULL PAGE RELOAD
        # ----------------------------------------------------------------------
        print("\n[STEP 8] Testing Persistence Across Full Page Reload...")
        page.reload()
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # Switch to evaluator and verify persisted score
        page.click("#nav-evaluator")
        page.wait_for_selector("#stat-visibility-score")
        time.sleep(0.5)

        reloaded_score = page.locator("#stat-visibility-score").inner_text()
        reloaded_scan_id = page.locator("#eval-info-id").inner_text()
        print(f"Reload Persistence Verified: Score={reloaded_score}/100 | ScanID={reloaded_scan_id}")
        assert reloaded_score == eval_score, f"Persisted score mismatch! Expected {eval_score}, got {reloaded_score}"

        # ----------------------------------------------------------------------
        # 9. CONSOLE & ERROR AUDIT
        # ----------------------------------------------------------------------
        print("\n" + "=" * 80)
        print("BROWSER CONSOLE & UNCAUGHT ERROR AUDIT")
        print(f"Total Console Logs Captured: {len(console_logs)}")
        console_errs = [l for l in console_logs if "[error]" in l.lower()]
        print(f"Console Errors: {len(console_errs)}")
        for ce in console_errs:
            print(f"  {ce}")

        print(f"Uncaught Page Exceptions: {len(page_errors)}")
        for pe in page_errors:
            print(f"  {pe}")

        assert len(page_errors) == 0, f"Uncaught page exceptions detected: {page_errors}"
        browser.close()
        print("\nSUCCESS: All feature workflows passed in Google Chrome with ZERO uncaught errors!")
        print("=" * 80)

if __name__ == "__main__":
    run_comprehensive_audit()
