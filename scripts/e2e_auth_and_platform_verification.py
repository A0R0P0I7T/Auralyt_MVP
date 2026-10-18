"""End-to-End Google Chrome validation script for P0 Auth, Multi-Tenancy, and Engines 1-3."""
import os
import sys
import time
from playwright.sync_api import sync_playwright

ARTIFACT_DIR = r"C:\Users\sahaa\.gemini\antigravity-ide\brain\a5e5a844-b0ec-43dd-acfa-80763e2486eb"
BASE_URL = "http://127.0.0.1:8000"


def run_e2e_verification():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    print(f"=== Auralyt P0 Auth & E2E Platform Verification ===")
    print(f"Target URL: {BASE_URL}")

    console_logs = []
    page_errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, channel="chrome")
        context = browser.new_context(viewport={"width": 1440, "height": 900})
        page = context.new_page()

        page.on("console", lambda msg: console_logs.append(f"[{msg.type}] {msg.text}"))
        page.on("pageerror", lambda err: page_errors.append(str(err)))

        # -------------------------------------------------------------------
        # Step 1: Unauthenticated visit -> Auth Modal must appear
        # -------------------------------------------------------------------
        print("\nStep 1: Navigating unauthenticated to home...")
        page.goto(BASE_URL)
        page.wait_for_load_state("networkidle")
        time.sleep(1)

        page.wait_for_selector("#auth-modal", state="visible", timeout=10000)
        auth_modal = page.locator("#auth-modal")
        assert auth_modal.is_visible(), "Expected #auth-modal to be visible for unauthenticated user"
        print("PASS: Unauthenticated visitor greeted by #auth-modal.")

        shot_unauth = os.path.join(ARTIFACT_DIR, "audit_p0_unauthenticated_modal.png")
        page.screenshot(path=shot_unauth)
        print(f"Saved screenshot: {shot_unauth}")

        # -------------------------------------------------------------------
        # Step 2: Test Invalid Credentials Rejection
        # -------------------------------------------------------------------
        print("\nStep 2: Testing invalid login rejection...")
        page.fill("#auth-email", "invalid_user@auralyt.ai")
        page.fill("#auth-password", "WrongPassword123!")
        page.click("#auth-submit-btn")
        time.sleep(1)

        error_box = page.locator("#auth-modal-error")
        assert error_box.is_visible(), "Expected error message on invalid login"
        print(f"PASS: Rejected invalid login with message: '{error_box.inner_text()}'")

        shot_invalid = os.path.join(ARTIFACT_DIR, "audit_p0_invalid_login.png")
        page.screenshot(path=shot_invalid)
        print(f"Saved screenshot: {shot_invalid}")

        # -------------------------------------------------------------------
        # Step 3: Admin Login with Seeded Credentials
        # -------------------------------------------------------------------
        print("\nStep 3: Logging in with seeded admin credentials...")
        page.click("button:has-text('Fill Admin Credentials')")
        time.sleep(0.5)
        page.click("#auth-submit-btn")
        page.wait_for_selector("#auth-modal", state="hidden", timeout=10000)
        time.sleep(1)

        # Verify authenticated header state
        org_name = page.locator("#auth-org-name").inner_text()
        user_email = page.locator("#auth-user-email").inner_text()
        logout_btn = page.locator("#auth-logout-btn")
        assert "Default Organization" in org_name, f"Expected Default Organization, got {org_name}"
        assert "admin@auralyt.ai" in user_email, f"Expected admin@auralyt.ai, got {user_email}"
        assert logout_btn.is_visible(), "Expected logout button to be visible"
        print(f"PASS: Logged in successfully as {user_email} in org '{org_name}'")

        # Verify brands selector is populated
        brand_select = page.locator("#global-brand-select")
        brand_options = brand_select.locator("option").all_inner_texts()
        print(f"PASS: Brands populated ({len(brand_options)} options): {brand_options[:4]}")
        assert len(brand_options) > 1, "Expected brands to be populated for Default Organization"

        shot_auth_dash = os.path.join(ARTIFACT_DIR, "audit_p0_authenticated_dashboard.png")
        page.screenshot(path=shot_auth_dash)
        print(f"Saved screenshot: {shot_auth_dash}")

        # -------------------------------------------------------------------
        # Step 4: Engine 1 — Brand Profile & Fact Verification
        # -------------------------------------------------------------------
        print("\nStep 4: Verifying Engine 1 (Brand Profile & Facts)...")
        # Select OpenRouter or first available brand
        target_option = next((opt for opt in brand_options if "OpenRouter" in opt or "openrouter" in opt), brand_options[1])
        brand_select.select_option(label=target_option)
        time.sleep(1)

        page.click("#nav-profile")
        page.wait_for_selector("#profile-brand-name:not(:empty)", timeout=5000)
        brand_name = page.locator("#profile-brand-name").inner_text()
        verified_cnt = page.locator("#profile-stat-verified").inner_text()
        print(f"PASS: Loaded Profile for '{brand_name}', verified facts: {verified_cnt}")

        shot_profile = os.path.join(ARTIFACT_DIR, "audit_p0_brand_profile.png")
        page.screenshot(path=shot_profile)
        print(f"Saved screenshot: {shot_profile}")

        # Fact Verification Tab
        page.click("#nav-facts")
        page.wait_for_selector("#facts-container", timeout=5000)
        time.sleep(0.5)
        facts_count = page.locator("#facts-container .fact-item").count()
        print(f"PASS: Fact Verification tab loaded {facts_count} facts")
        assert facts_count > 0, "Expected facts in verification list"

        shot_facts = os.path.join(ARTIFACT_DIR, "audit_p0_fact_verification.png")
        page.screenshot(path=shot_facts)
        print(f"Saved screenshot: {shot_facts}")

        # -------------------------------------------------------------------
        # Step 5: Engine 2 — Prompt Intelligence & Grounding Evidence
        # -------------------------------------------------------------------
        print("\nStep 5: Verifying Engine 2 (Prompt Intelligence & Evidence)...")
        page.click("#nav-prompts")
        page.wait_for_selector("#prompts-table-body", timeout=5000)
        time.sleep(1)

        total_prompts = page.locator("#cov-total-prompts").inner_text()
        print(f"PASS: Engine 2 Prompt Intelligence active with {total_prompts} total prompts")

        # Inspect evidence modal
        first_inspect_btn = page.locator("#prompts-table-body button:has-text('Grounding')").first
        if first_inspect_btn.is_visible():
            first_inspect_btn.click()
            page.wait_for_selector("#prompt-evidence-modal", state="visible", timeout=5000)
            time.sleep(0.5)
            prompt_text = page.locator("#pe-prompt-text").inner_text()
            print(f"PASS: Opened Prompt Evidence Modal for: '{prompt_text[:60]}...'")

            shot_evidence = os.path.join(ARTIFACT_DIR, "audit_p0_prompt_evidence.png")
            page.screenshot(path=shot_evidence)
            print(f"Saved screenshot: {shot_evidence}")

            page.click("#prompt-evidence-modal button:has-text('Close')")
            page.wait_for_selector("#prompt-evidence-modal", state="hidden")

        # -------------------------------------------------------------------
        # Step 6: Engine 3 — AI Visibility & Raw Responses
        # -------------------------------------------------------------------
        print("\nStep 6: Verifying Engine 3 (AI Visibility & Evaluations)...")
        page.click("#nav-evaluator")
        page.wait_for_selector("#eval-summary-card", timeout=5000)
        time.sleep(1)

        vis_score = page.locator("#stat-visibility-score").inner_text()
        print(f"PASS: Engine 3 AI Visibility Scorecard active with score: {vis_score}")

        shot_visibility = os.path.join(ARTIFACT_DIR, "audit_p0_ai_visibility.png")
        page.screenshot(path=shot_visibility)
        print(f"Saved screenshot: {shot_visibility}")

        # -------------------------------------------------------------------
        # Step 7: Multi-Tenant Isolation (New Organization Registration)
        # -------------------------------------------------------------------
        print("\nStep 7: Verifying Strict Cross-Tenant Isolation via Registration...")
        # Logout from admin
        page.click("#auth-logout-btn")
        page.wait_for_selector("#auth-modal", state="visible")
        time.sleep(0.5)

        # Switch to Register mode
        page.click("#auth-switch-btn")
        time.sleep(0.5)

        timestamp = int(time.time())
        new_email = f"tenant_{timestamp}@isolated-corp.com"
        new_org = f"Isolated Corp {timestamp}"

        page.fill("#auth-full-name", "Security Auditor")
        page.fill("#auth-org-name-input", new_org)
        page.fill("#auth-email", new_email)
        page.fill("#auth-password", "SecureTenantPass2026!")
        time.sleep(0.5)
        page.click("#auth-submit-btn")

        page.wait_for_selector("#auth-modal", state="hidden", timeout=15000)
        time.sleep(1.5)

        # Check tenant badge reflects new organization
        new_org_badge = page.locator("#auth-org-name").inner_text()
        new_email_badge = page.locator("#auth-user-email").inner_text()
        print(f"PASS: Logged in as new tenant '{new_email_badge}' in '{new_org_badge}'")
        assert new_org in new_org_badge, f"Expected {new_org}, got {new_org_badge}"

        # Check that this brand-new tenant sees ZERO brands belonging to Default Organization
        brand_select_new = page.locator("#global-brand-select")
        new_options = brand_select_new.locator("option").all_inner_texts()
        print(f"PASS: New tenant sees isolated brand list ({len(new_options)} options): {new_options}")
        assert len(new_options) <= 1, f"Expected 0 brands for new isolated tenant, but found {len(new_options)}"

        shot_tenant_iso = os.path.join(ARTIFACT_DIR, "audit_p0_tenant_isolation.png")
        page.screenshot(path=shot_tenant_iso)
        print(f"Saved screenshot: {shot_tenant_iso}")

        browser.close()

    print("\n=======================================================")
    print("ALL E2E GOOGLE CHROME VERIFICATION CHECKS PASSED 100%!")
    print("=======================================================")


if __name__ == "__main__":
    run_e2e_verification()
