"""Playwright script to execute the full end-to-end user workflow in Chromium."""
import os
import sys
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\sahaa\.gemini\antigravity-ide\brain\a5e5a844-b0ec-43dd-acfa-80763e2486eb"
BASE_URL = "http://127.0.0.1:8000"

def run_workflow():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")
    print(f"Starting E2E workflow against {BASE_URL}...")
    console_logs = []
    page_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        # Listen to console and errors
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        # 1. Navigate to home
        print("Step 1: Navigating to home page...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # 2. Check brand selector
        brand_select = page.locator("#global-brand-select")
        selected_brand = brand_select.input_value()
        print(f"Selected brand ID: {selected_brand}")
        assert selected_brand, "No brand selected in #global-brand-select"

        # 3. Tab 2: Brand Profile (Engine 1)
        print("Step 2: Checking Brand Profile (Engine 1)...")
        page.click("#nav-profile")
        page.wait_for_selector("#profile-brand-name:not(:empty)")
        time.sleep(0.5)

        brand_name = page.locator("#profile-brand-name").inner_text()
        domain = page.locator("#profile-domain").inner_text()
        version = page.locator("#profile-version-badge").inner_text()
        facts_cnt = page.locator("#profile-stat-facts").inner_text()
        verified_cnt = page.locator("#profile-stat-verified").inner_text()
        pages_cnt = page.locator("#profile-stat-pages").inner_text()
        print(f"Brand: {brand_name} ({domain}), Version: {version}, Facts: {facts_cnt}, Verified: {verified_cnt}, Pages: {pages_cnt}")

        profile_shot_path = os.path.join(ARTIFACT_DIR, "profile_view_e2e.png")
        page.screenshot(path=profile_shot_path, full_page=True)
        print(f"Saved full profile screenshot: {profile_shot_path}")

        # Scroll to pricing and capture dedicated pricing screenshot
        page.locator("#pricing-list").scroll_into_view_if_needed()
        time.sleep(0.5)
        pricing_shot_path = os.path.join(ARTIFACT_DIR, "pricing_intelligence_view_e2e.png")
        page.screenshot(path=pricing_shot_path)
        print(f"Saved pricing section screenshot: {pricing_shot_path}")

        # Inspect evidence modal on first pricing item
        first_pricing_ev_btn = page.locator("#pricing-list button:has-text('Inspect Evidence')").first
        if first_pricing_ev_btn.is_visible():
            first_pricing_ev_btn.click()
            page.wait_for_selector("#evidence-modal", state="visible")
            time.sleep(0.5)
            ev_snippet = page.locator("#evidence-snippet").inner_text()
            print(f"Pricing Evidence Modal opened: snippet='{ev_snippet[:60]}...'")
            pricing_modal_shot = os.path.join(ARTIFACT_DIR, "pricing_evidence_modal_e2e.png")
            page.screenshot(path=pricing_modal_shot)
            print(f"Saved pricing evidence modal screenshot: {pricing_modal_shot}")
            page.click("#evidence-modal .close-btn")
            page.wait_for_selector("#evidence-modal", state="hidden")

        # 4. Tab 4: Crawled Pages
        print("Step 3: Checking Crawled Pages...")
        page.click("#nav-pages")
        page.wait_for_selector("#pages-table-body tr")
        time.sleep(0.5)

        first_view_btn = page.locator("#pages-table-body tr:first-child button").first
        if first_view_btn.is_visible():
            first_view_btn.click()
            page.wait_for_selector("#page-detail-modal", state="visible")
            time.sleep(0.5)
            modal_url = page.locator("#page-detail-url").inner_text()
            facts_on_page = page.locator("#page-detail-facts-count").inner_text()
            print(f"Page Detail Modal: URL={modal_url}, Facts on page={facts_on_page}")
            # Close modal
            page.click("#page-detail-modal .close-btn")
            page.wait_for_selector("#page-detail-modal", state="hidden")

        # 5. Tab 3: Brand Facts
        print("Step 4: Checking Brand Facts...")
        page.click("#nav-facts")
        page.wait_for_selector("#facts-container")
        time.sleep(0.5)

        # Filter by rejected
        page.select_option("#fact-filter-status", "rejected")
        time.sleep(0.5)
        rejected_text = page.locator("#facts-container").inner_text()
        has_rejected = "✕ Rejected" in rejected_text
        print(f"Rejected facts filter active. Found rejected facts: {has_rejected}")
        # Reset filter
        page.select_option("#fact-filter-status", "")
        time.sleep(0.5)

        # 6. Tab 5: Prompt Intelligence (Engine 2)
        print("Step 5: Checking Prompt Intelligence (Engine 2)...")
        page.click("#nav-prompts")
        page.wait_for_selector("#cov-total-prompts")
        time.sleep(0.5)

        cov_total = page.locator("#cov-total-prompts").inner_text()
        cov_appr = page.locator("#cov-approved-prompts").inner_text()
        cov_score = page.locator("#cov-avg-score").inner_text()
        print(f"Prompt Coverage: Total={cov_total}, Approved={cov_appr}, Avg Score={cov_score}")

        # Check Grounding modal on first prompt
        grounding_btn = page.locator("#prompts-table-body tr:first-child button").first
        if grounding_btn.is_visible():
            grounding_btn.click()
            page.wait_for_selector("#prompt-evidence-modal", state="visible")
            time.sleep(0.5)
            ev_text = page.locator("#pe-prompt-text").inner_text()
            print(f"Prompt Evidence Modal open for: {ev_text[:50]}...")
            page.click("#prompt-evidence-modal .close-btn")
            page.wait_for_selector("#prompt-evidence-modal", state="hidden")

        # Click Generate Prompts
        print("Generating fresh prompts...")
        page.select_option("#prompt_count_select", "20")
        page.click("#generate-prompts-btn")
        # Wait for button to restore
        page.wait_for_function("document.getElementById('generate-prompts-btn').disabled === false", timeout=30000)
        time.sleep(1)

        run_badge = page.locator("#prompt-run-status-badge").inner_text()
        run_id_val = page.locator("#info-run-id").inner_text()
        run_ver = page.locator("#info-profile-ver").inner_text()
        run_cnt = page.locator("#info-count").inner_text()
        print(f"Prompt Generation completed: Status={run_badge}, RunID={run_id_val}, ProfileVer={run_ver}, Generated={run_cnt}")

        prompt_shot_path = os.path.join(ARTIFACT_DIR, "prompt_intelligence_e2e.png")
        page.screenshot(path=prompt_shot_path)
        print(f"Saved screenshot: {prompt_shot_path}")

        # 7. Tab 6: AI Visibility Evaluator (Engine 3)
        print("Step 6: Checking AI Visibility Evaluator (Engine 3)...")
        page.click("#nav-evaluator")
        page.wait_for_selector("#stat-visibility-score")
        time.sleep(0.5)

        # Select Mock Provider, 5 prompts
        page.select_option("#eval_provider_select", "mock")
        page.select_option("#eval_max_prompts", "5")

        # Trigger Scan
        print("Triggering AI Visibility Scan...")
        page.click("#start-eval-btn")

        # Verify button disables
        btn_text = page.locator("#start-eval-btn").inner_text()
        print(f"Button state during scan start: '{btn_text}'")

        # Wait for scan to complete (badge completed)
        page.wait_for_function("document.getElementById('start-eval-btn').disabled === false", timeout=30000)
        time.sleep(1)

        eval_status = page.locator("#eval-status-badge").inner_text()
        eval_score = page.locator("#stat-visibility-score").inner_text()
        eval_mention = page.locator("#stat-mention-rate").inner_text()
        eval_rec = page.locator("#stat-recommendation-rate").inner_text()
        eval_pos = page.locator("#stat-avg-position").inner_text()
        eval_done = page.locator("#stat-eval-completed").inner_text()
        eval_scan_id = page.locator("#eval-info-id").inner_text()
        eval_prof_ver = page.locator("#eval-info-profile-version").inner_text()

        print(f"Scan Completed: Status={eval_status}, ScanID={eval_scan_id}, ProfileVer={eval_prof_ver}")
        print(f"Scorecard: Visibility Score={eval_score}/100, Mention Rate={eval_mention}, Rec Rate={eval_rec}, Avg Pos={eval_pos}, Completed={eval_done}")

        # Verify mock banner visible
        mock_banner = page.locator("#eval-mock-banner")
        assert mock_banner.is_visible(), "Mock provider notice banner should be visible for mock provider"
        print("Verified mock provider warning banner is displayed correctly.")

        # Inspect Raw Response Modal on first evaluation item
        raw_resp_btn = page.locator("#eval-results-container button:has-text('Inspect Raw AI Response')").first
        if raw_resp_btn.is_visible():
            raw_resp_btn.click()
            page.wait_for_selector("#raw-response-modal", state="visible")
            time.sleep(0.5)
            raw_meta = page.locator("#raw-response-meta").inner_text()
            raw_body = page.locator("#raw-response-body").inner_text()
            print(f"Raw Response Modal: {raw_meta}, Body length={len(raw_body)} chars")
            page.click("#raw-response-modal .close-btn")
            page.wait_for_selector("#raw-response-modal", state="hidden")

        eval_shot_path = os.path.join(ARTIFACT_DIR, "visibility_evaluator_e2e.png")
        page.screenshot(path=eval_shot_path)
        print(f"Saved screenshot: {eval_shot_path}")

        # 8. Check Historical Scans Selector
        hist_select = page.locator("#eval_history_scan_select")
        if hist_select.is_visible():
            options = hist_select.locator("option").all()
            print(f"Historical scans count in selector: {len(options)}")
            for opt in options[:3]:
                print(f"  Scan option: {opt.inner_text()}")

        # 9. Page Reload & Persistence Verification
        print("Step 7: Testing Reload & Persistence...")
        page.reload()
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        page.click("#nav-evaluator")
        page.wait_for_selector("#stat-visibility-score")
        time.sleep(0.5)

        reloaded_score = page.locator("#stat-visibility-score").inner_text()
        reloaded_mention = page.locator("#stat-mention-rate").inner_text()
        print(f"After Reload: Score={reloaded_score}, Mention Rate={reloaded_mention}")
        assert reloaded_score == eval_score, f"Score did not persist after reload! Got {reloaded_score}, expected {eval_score}"

        # 10. Check Console Errors
        print("\n--- Console and Error Audit ---")
        print(f"Total console logs: {len(console_logs)}")
        error_logs = [log for log in console_logs if "[error]" in log.lower()]
        print(f"Console errors: {len(error_logs)}")
        for err in error_logs:
            print(f"  {err}")

        print(f"Uncaught page errors: {len(page_errors)}")
        for perr in page_errors:
            print(f"  {perr}")

        assert len(page_errors) == 0, f"Uncaught page errors detected: {page_errors}"

        browser.close()
        print("\nSUCCESS: Complete E2E Chrome workflow validated successfully with ZERO unhandled errors!")

if __name__ == "__main__":
    run_workflow()
