"""Regression and validation tests for Pricing Intelligence, semantic classification,
and allowance/quota guardrails.
"""
import pytest
from app.db.models import CrawledPage
from app.extractor.fact_synthesizer import FactSynthesizer


def test_pricing_rejects_byok_limits_from_subscription_plan():
    """Verify that BYOK inference limits ($25,000 / month with no fees) are NEVER
    classified as plan subscription prices."""
    pricing_page = CrawledPage(
        brand_id="test-openrouter-pricing",
        requested_url="https://openrouter.ai/pricing",
        final_url="https://openrouter.ai/pricing",
        http_status=200,
        page_type="pricing",
        extracted_text="""
        BYOK Limits Learn more →
        Free: No
        Standard: $25,000 of list price inference / month with no fees, 5% fee after
        Business: $25,000 of list price inference / month with no fees, 5% fee after
        Enterprise: Custom
        """,
        content_hash="hash-or-limits"
    )
    synth = FactSynthesizer("test-openrouter-pricing", user_business_name="OpenRouter")
    facts = synth.synthesize_facts([pricing_page])

    pricing_facts = [f for f in facts if f.fact_type == "pricing"]
    assert len(pricing_facts) >= 2

    for pf in pricing_facts:
        val = pf.fact_value
        # MUST NEVER be subscription_plan with $25,000
        if val.get("amount") == 25000.0:
            assert val.get("pricing_type") == "usage_allowance"
            assert "allowance" in val.get("unit")
            # Must not be attributed to Free plan
            assert val.get("plan_name") != "Free"


def test_pricing_identifies_free_tier_and_platform_fees():
    """Verify that dedicated pricing pages detect Free tier ($0) and Pay-as-you-go platform fees."""
    pricing_page = CrawledPage(
        brand_id="test-or-tiers",
        requested_url="https://openrouter.ai/pricing",
        final_url="https://openrouter.ai/pricing",
        http_status=200,
        page_type="pricing",
        extracted_text="""
        Platform fees
        Free: N/A (25+ free models, Get started for free)
        Standard: 5.5%
        Business: 8%
        Enterprise: Fee discounts available
        """,
        content_hash="hash-or-tiers"
    )
    synth = FactSynthesizer("test-or-tiers", user_business_name="OpenRouter")
    facts = synth.synthesize_facts([pricing_page])

    pricing_facts = [f for f in facts if f.fact_type == "pricing"]
    by_type = {f.fact_value.get("pricing_type"): f.fact_value for f in pricing_facts}

    assert "free_tier" in by_type
    assert by_type["free_tier"]["amount"] == 0.0
    assert by_type["free_tier"]["billing_basis"] == "free"

    assert "pay_as_you_go" in by_type
    payg = [f.fact_value for f in pricing_facts if f.fact_value.get("pricing_type") == "pay_as_you_go"]
    tiers = {p["plan_name"]: p["amount"] for p in payg}
    assert "Standard" in tiers
    assert tiers["Standard"] == 5.5


def test_model_inference_rates_classified_as_usage_never_monthly():
    """Verify that token inference rates ($0.042 /M input tokens, $40/M characters)
    are classified as usage rates with exact units, NEVER monthly plans."""
    models_page = CrawledPage(
        brand_id="test-or-models",
        requested_url="https://openrouter.ai/models?order=pricing-low-to-high",
        final_url="https://openrouter.ai/models?order=pricing-low-to-high",
        http_status=200,
        page_type="pricing",
        extracted_text="""
        Model catalog:
        Microsoft: Decision-1: $0.042 /M input tokens $0 /M output tokens
        StepFun: Step 5 Preview: $0.15 /M input tokens $0 /M output tokens
        ElevenLabs: Eleven v4 Turbo: $40 /M characters
        Anthropic: Claude 3.5 Sonnet: $3.00 / 1M input tokens $15.00 / 1M output tokens
        """,
        content_hash="hash-or-models"
    )
    synth = FactSynthesizer("test-or-models", user_business_name="OpenRouter")
    facts = synth.synthesize_facts([models_page])

    pricing_facts = [f for f in facts if f.fact_type == "pricing"]
    assert len(pricing_facts) >= 3

    for pf in pricing_facts:
        val = pf.fact_value
        assert val.get("pricing_type") == "usage_rate"
        assert val.get("billing_basis") == "usage"
        # Unit MUST NOT be 'month'
        assert val.get("unit") != "month"
        assert any(u in val.get("unit") for u in ("token", "character", "tokens", "characters"))


def test_standard_subscription_plans_preserve_recurring_billing():
    """Verify standard SaaS plans ($20 / month, $200 / user/month) preserve recurring semantics."""
    page = CrawledPage(
        brand_id="test-saas",
        requested_url="https://example.com/pricing",
        final_url="https://example.com/pricing",
        http_status=200,
        page_type="pricing",
        extracted_text="""
        Starter: $20 / month.
        Team Tier: $15 / user / month.
        Enterprise: $1,200 / year.
        """,
        content_hash="hash-saas-plans"
    )
    synth = FactSynthesizer("test-saas", user_business_name="Example")
    facts = synth.synthesize_facts([page])

    pricing_facts = [f for f in facts if f.fact_type == "pricing"]
    plans = {f.fact_value.get("plan_name"): f.fact_value for f in pricing_facts}

    assert "Starter" in plans
    print("\nSTARTER PLAN DETAILS:", plans["Starter"])
    assert plans["Starter"]["billing_basis"] == "monthly"
    assert plans["Starter"]["amount"] == 20.0

    assert "Team" in plans
    assert plans["Team"]["billing_basis"] == "per_user_monthly"
    assert plans["Team"]["unit"] == "user/month"

    assert "Enterprise" in plans
    assert plans["Enterprise"]["billing_basis"] == "annually"
    assert plans["Enterprise"]["unit"] == "year"
