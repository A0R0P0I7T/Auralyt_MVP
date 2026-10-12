"""Regression tests for the versioned ground-truth contract."""
from app.db.models import BrandFact, ProfileRun
from app.extractor.fact_synthesizer import canonical_fact_key, FactSynthesizer
from tests.test_cross_site_validation import create_saas_site_pages


def test_equivalent_facts_have_stable_identity_and_retained_evidence():
    first = BrandFact(
        brand_id="brand-1", profile_version=1, fact_type="product_service",
        fact_value={"name": "Aurora", "url": "https://example.test/a"},
        source_url="https://example.test/a", evidence_snippet="Aurora is a platform",
    )
    second = BrandFact(
        brand_id="brand-1", profile_version=1, fact_type="product_service",
        fact_value={"name": "Aurora", "url": "https://example.test/b"},
        source_url="https://example.test/b", evidence_snippet="Explore Aurora",
    )
    assert canonical_fact_key(first.fact_type, first.fact_value) == canonical_fact_key(second.fact_type, second.fact_value)

    facts = FactSynthesizer("brand-1").synthesize_facts(create_saas_site_pages())
    product = next(f for f in facts if f.fact_type == "product_service" and f.fact_value.get("name") == "Linear Asks")
    assert product.fact_key
    assert product.supporting_evidence


def test_profile_run_and_fact_lifecycle_defaults_are_explicit():
    run = ProfileRun(brand_id="brand-1")
    fact = BrandFact(brand_id="brand-1", fact_type="use_case", fact_value="Shipping software")
    assert run.profile_version == 1
    assert fact.is_superseded is False
    assert fact.is_stale is False
    assert fact.is_rejected is False


def test_pricing_identity_keeps_units_and_association_distinct():
    per_user = {"plan_name": "Pro", "amount": 8, "currency": "USD", "unit": "user", "billing_basis": "monthly", "associated_product": "App"}
    per_token = {"plan_name": "Pro", "amount": 8, "currency": "USD", "unit": "1M tokens", "billing_basis": "usage", "associated_product": "API"}
    assert canonical_fact_key("pricing", per_user) != canonical_fact_key("pricing", per_token)
