import pytest
from app.db.models import CrawledPage
from app.extractor.fact_synthesizer import FactSynthesizer


def test_fact_synthesizer_provenance_and_schema():
    page = CrawledPage(
        id="page-123",
        brand_id="brand-abc",
        profile_run_id="run-xyz",
        requested_url="https://acme.ai",
        final_url="https://acme.ai/",
        http_status=200,
        title="Acme Analytics | Next-Gen AI Visibility",
        meta_description="Acme provides AI search monitoring for modern marketing teams.",
        headings={"h1": ["Next-Gen AI Visibility"], "h2": ["Core Capabilities"]},
        extracted_text="""
Acme provides AI search monitoring for modern marketing teams.
Built for enterprise marketing leaders and SEO directors.
Key Features:
- Real-time prompt intelligence
- Multi-engine brand monitoring
Pricing starts at $99/mo for Pro teams.
Contact our team at hello@acme.ai.
        """,
        structured_data=[{
            "@type": "Organization",
            "name": "Acme Analytics Inc.",
            "description": "Leading enterprise visibility monitoring platform."
        }],
        internal_links=[],
        external_links=["https://linkedin.com/company/acmeanalytics"],
        page_type="homepage",
        language="en",
        content_hash="hash123",
        extraction_status="success",
        used_js=False
    )

    synthesizer = FactSynthesizer(
        brand_id="brand-abc",
        profile_version=1
    )

    facts = synthesizer.synthesize_facts([page])

    # Check Business Name provenance
    bname_fact = next((f for f in facts if f.fact_type == "business_name"), None)
    assert bname_fact is not None
    assert bname_fact.fact_value == "Acme Analytics Inc."
    assert bname_fact.extraction_method == "json_ld_schema"
    assert bname_fact.confidence >= 0.95
    assert bname_fact.source_url == "https://acme.ai/"

    # Check Description
    desc_fact = next((f for f in facts if f.fact_type == "company_description"), None)
    assert desc_fact is not None
    assert "enterprise visibility" in desc_fact.fact_value

    # Check Target Audience
    aud_fact = next((f for f in facts if f.fact_type == "target_audience"), None)
    assert aud_fact is not None
    assert "enterprise marketing leaders" in aud_fact.fact_value

    # Check Pricing
    pricing_fact = next((f for f in facts if f.fact_type == "pricing"), None)
    assert pricing_fact is not None
    assert "$99/mo" in str(pricing_fact.fact_value)

    # Check Contact Info
    email_fact = next((f for f in facts if f.fact_type == "contact_info" and f.fact_value.get("type") == "email"), None)
    assert email_fact is not None
    assert email_fact.fact_value["value"] == "hello@acme.ai"
