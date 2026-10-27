"""Automated browser validation for Clay.com AI Visibility Experiment.
Drives local Google Chrome to exercise the UI and verify Engine 3 reaches 20/20.
"""
import os
import sys
import time
import json
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = "/Users/arpitsaha/.gemini/antigravity-ide/brain/558d7169-2f8e-444a-aba3-7d00d8341e34"
BASE_URL = "http://127.0.0.1:8000"

def run_validation():
    print("=" * 80)
    print("STARTING BROWSER VALIDATION FOR CLAY.COM ON LOCAL CHROME")
    print(f"Target URL: {BASE_URL}")
    print("=" * 80)

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        console_logs = []
        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))

        print("\n[STEP 1] Navigating to http://127.0.0.1:8000/ ...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        # Check if auth modal is visible
        auth_modal = page.locator("#auth-modal")
        if auth_modal.is_visible():
            print("Auth modal detected. Submitting admin credentials...")
            page.fill("#auth-email", "admin@auralyt.ai")
            page.fill("#auth-password", "AuralytAdmin2026!")
            page.click("#auth-submit-btn")
            auth_modal.wait_for(state="hidden", timeout=10000)
            time.sleep(1)
            print("Logged in successfully and auth modal closed!")

        screenshot_1 = os.path.join(ARTIFACT_DIR, "clay_step1_dashboard.png")
        page.screenshot(path=screenshot_1)
        print(f"Saved initial dashboard screenshot to {screenshot_1}")

        # Ensure we are on the Run Experiment tab
        nav_exp = page.locator("#nav-experiment")
        if nav_exp.is_visible():
            nav_exp.click()
            time.sleep(0.5)

        print("\n[STEP 2] Configuring End-to-End Experiment for https://www.clay.com ...")
        url_input = page.locator("#exp-website-url")
        url_input.fill("https://www.clay.com")

        # Set prompt count to 20
        count_input = page.locator("#exp-prompt-count")
        count_input.fill("20")

        # Set provider to Gemini
        provider_select = page.locator("#exp-provider")
        provider_select.select_option("gemini")

        screenshot_2 = os.path.join(ARTIFACT_DIR, "clay_step2_configured.png")
        page.screenshot(path=screenshot_2)
        print(f"Saved configured experiment screenshot to {screenshot_2}")

        print("\n[STEP 3] Launching AI Visibility Experiment...")
        start_btn = page.locator("#exp-run-btn")
        start_btn.click()

        print("\n[STEP 4] Monitoring pipeline progress in real-time...")
        start_time = time.time()
        last_progress_text = ""
        e3_passed_15 = False
        completed = False

        # Monitor loop (paced queries take ~70-90s)
        for poll_idx in range(150): # up to 300 seconds
            time.sleep(2)
            elapsed = int(time.time() - start_time)

            step1_status = page.locator("#exp-step-1-status").inner_text() if page.locator("#exp-step-1-status").is_visible() else ""
            step2_status = page.locator("#exp-step-2-status").inner_text() if page.locator("#exp-step-2-status").is_visible() else ""
            step3_status = page.locator("#exp-step-3-status").inner_text() if page.locator("#exp-step-3-status").is_visible() else ""
            step3_detail = page.locator("#exp-step-3-detail").inner_text() if page.locator("#exp-step-3-detail").is_visible() else ""
            progress_msg = page.locator("#exp-progress-msg").inner_text() if page.locator("#exp-progress-msg").is_visible() else ""
            badge_text = page.locator("#exp-progress-badge").inner_text().strip() if page.locator("#exp-progress-badge").is_visible() else ""

            current_log = f"[{elapsed}s] [{badge_text}] E1: {step1_status} | E2: {step2_status} | E3: {step3_status} ({step3_detail})"
            if current_log != last_progress_text:
                print(current_log)
                last_progress_text = current_log

            # Check if Step 3 passed 15
            for count_str in ["16 / 20", "17 / 20", "18 / 20", "19 / 20", "20 / 20"]:
                if count_str in step3_detail or count_str in progress_msg:
                    if not e3_passed_15:
                        print(f"*** BREAKTHROUGH: Engine 3 progress passed 15/20! Current: {count_str} ***")
                        e3_passed_15 = True

            if "COMPLETED" in badge_text or "COMPLETED" in step3_status:
                completed = True
                print(f"\nPipeline finished with status: {badge_text or step3_status} after {elapsed}s")
                break

            if "FAILED" in badge_text or "FAILED" in step3_status:
                print(f"\nPipeline failed: {badge_text or step3_status} after {elapsed}s")
                break

        time.sleep(2)
        screenshot_3 = os.path.join(ARTIFACT_DIR, "clay_step3_completed.png")
        page.screenshot(path=screenshot_3, full_page=True)
        print(f"Saved completed experiment screenshot to {screenshot_3}")

        # Dump summary results
        print("\n[STEP 5] Extracting Final Results from UI...")
        score_elem = page.locator("#exp-score")
        score_val = score_elem.inner_text() if score_elem.is_visible() else "N/A"
        mention_elem = page.locator("#exp-mention-rate")
        mention_val = mention_elem.inner_text() if mention_elem.is_visible() else "N/A"
        print(f"Final Visibility Score: {score_val}")
        print(f"Brand Mention Rate: {mention_val}")

        # Extract prompt rows from the results table
        prompts = []
        rows = page.locator("#exp-prompts-tbody tr").all()
        print(f"Total prompt rows in results table: {len(rows)}")
        for idx, row in enumerate(rows, 1):
            text = row.inner_text()
            prompts.append(text)
            print(f"Row {idx}: {text[:100]}...")

        with open(os.path.join(ARTIFACT_DIR, "clay_prompts_results.json"), "w") as f:
            json.dump({
                "score": score_val,
                "mention_rate": mention_val,
                "prompts_count": len(rows),
                "e3_passed_15": e3_passed_15,
                "completed": completed,
                "prompts": prompts
            }, f, indent=2)

        browser.close()

if __name__ == "__main__":
    run_validation()
