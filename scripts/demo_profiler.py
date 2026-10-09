import asyncio
import os
import sys

# Ensure project root is in sys.path
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

from app.db.session import async_session_factory
from app.services.profiler_service import ProfilerService
from app.crawler.security import validate_and_resolve_url, SecurityValidationError



async def main():
    print("=" * 70)
    print(" Auralyt MVP — Engine 1: Brand & Website Profiler Demo")
    print("=" * 70)

    # 1. Test SSRF Security Defense
    print("\n[Step 1] Testing SSRF Defense...")
    malicious_urls = [
        "http://127.0.0.1:8000/internal",
        "http://169.254.169.254/latest/meta-data/",
        "http://metadata.google.internal/",
        "http://192.168.1.1/admin",
        "ftp://example.com/file"
    ]
    for m_url in malicious_urls:
        try:
            validate_and_resolve_url(m_url)
            print(f"  ❌ FAILED to block: {m_url}")
        except SecurityValidationError as e:
            print(f"  ✓ Safely BLOCKED: {m_url} -> {e}")

    # 2. Onboard and Profile a Public Test Site
    target_url = "https://example.com"
    print(f"\n[Step 2] Onboarding and Profiling Target Site: {target_url}...")

    async with async_session_factory() as db:
        brand, run = await ProfilerService.onboard_brand(
            website_url=target_url,
            business_name="Example Domain Inc.",
            industry="Internet Standards",
            target_market="Global",
            language="en",
            page_limit=5,
            db=db
        )
        print(f"  ✓ Brand Created: {brand.business_name} (ID: {brand.id}, Domain: {brand.domain})")
        print(f"  ✓ Profile Run Created: ID: {run.id}, Status: {run.status}")

        # Wait for the crawl and extraction background task to complete
        print("  ⏳ Waiting for crawl execution to complete...")
        for i in range(15):
            await asyncio.sleep(1)
            await db.refresh(run)
            if run.status in ("completed", "completed_with_warnings", "failed"):
                break

        print(f"  ✓ Run Finished with Status: {run.status.upper()}")
        print(f"    - Pages Discovered: {run.pages_discovered}")
        print(f"    - Pages Attempted:  {run.pages_attempted}")
        print(f"    - Pages Succeeded:  {run.pages_succeeded}")
        print(f"    - Duration:         {run.duration_seconds}s")
        if run.warnings:
            print(f"    - Warnings:         {run.warnings}")

        # 3. Retrieve Structured Profile and Evidence
        print("\n[Step 3] Inspecting Synthesized Brand Profile & Provenance Facts...")
        profile = await ProfilerService.get_brand_profile_summary(brand.id, db)
        print(f"  • Business Name: {profile['business_overview']['business_name']}")
        print(f"  • Domain:        {profile['business_overview']['domain']}")
        print(f"  • Industry:      {profile['business_overview']['industry']}")
        print(f"  • Total Facts:   {len(profile['facts'])}")

        print("\n  Fact Provenance Samples:")
        for idx, fact in enumerate(profile['facts'][:5], 1):
            val = str(fact.fact_value)[:60]
            print(f"    {idx}. [{fact.fact_type.upper()}] {val}")
            print(f"       Source:     {fact.source_url}")
            print(f"       Method:     {fact.extraction_method} (Confidence: {fact.confidence * 100:.0f}%)")
            print(f"       Confirmed:  {fact.user_confirmed}")
            if fact.evidence_snippet:
                print(f"       Snippet:    \"{fact.evidence_snippet[:80]}...\"")

        # 4. Human Verification Step
        print("\n[Step 4] Human Verification — Confirming First Extracted Fact...")
        if profile['facts']:
            target_fact = profile['facts'][0]
            target_fact.user_confirmed = True
            await db.commit()
            print(f"  ✓ Fact '{target_fact.fact_type}' marked as USER CONFIRMED.")

        print("\n[Step 5] Human Verification — Adding Ground-Truth Fact Manually...")
        from app.db.models import BrandFact
        manual_fact = BrandFact(
            brand_id=brand.id,
            profile_version=brand.profile_version,
            fact_type="product_service",
            fact_value="Reserved illustrative domain names for RFC documentation",
            source_url="https://example.com/",
            evidence_snippet="RFC 2606 Section 3 document specifications",
            extraction_method="user_input",
            confidence=1.0,
            user_confirmed=True
        )
        db.add(manual_fact)
        await db.commit()
        print(f"  ✓ Manual Ground-Truth Fact saved with full provenance.")

        # Re-fetch profile summary to verify progress
        updated_profile = await ProfilerService.get_brand_profile_summary(brand.id, db)
        print(f"\n  ✓ Verification Progress:")
        print(f"    - Total Facts:      {updated_profile['verification_progress']['total_facts']}")
        print(f"    - Confirmed Facts:  {updated_profile['verification_progress']['confirmed_facts']}")
        print(f"    - Verification Rate: {updated_profile['verification_progress']['verification_rate'] * 100:.0f}%")

    print("\n" + "=" * 70)
    print(" ✅ Engine 1 Demonstration Completed Successfully!")
    print("=" * 70)


if __name__ == "__main__":
    asyncio.run(main())
