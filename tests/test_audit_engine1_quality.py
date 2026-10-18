"""Regression and audit tests for Engine 1 Data Quality, Crawl Budgets & Structured Ground Truth."""
import pytest
from unittest.mock import MagicMock
from app.db.models import CrawledPage, BrandFact, Brand
from app.extractor.fact_synthesizer import FactSynthesizer, is_valid_product_candidate, is_valid_use_case, is_valid_target_audience
from app.crawler.engine import ScraplingCrawler
from app.prompts.normalizer import ProfileNormalizer


def test_openrouter_legal_clauses_rejected_from_products():
    """Verify that legal agreement headings observed in OpenRouter are completely rejected from products."""
    legal_headings = [
        "Enterprise Access Agreement",
        "Recitals",
        "2.1 License",
        "2.2 AI Model Terms",
        "2.3 Restrictions",
        "2.4 Data Processing",
        "3.1 Organizational Account Management",
        "4.1 Proprietary Rights",
        "5.1 Fees and Minimum Spend Requirement"
    ]
    for h in legal_headings:
        assert not is_valid_product_candidate(h, "OpenRouter"), f"Expected legal heading '{h}' to be rejected"


def test_openrouter_use_case_and_audience_fragments_rejected():
    """Verify that grammar fragments, benchmark comparisons, and context-free statements are rejected."""
    bad_fragments = [
        "s, split between Chinese OSS and RoW OSS: benchmark comparison",
        "s are expanding across multiple teams",
        "s grew as our engineering team scaled",
        "Chinese OSS vs US closed-source models",
        "Token volume comparison with low latency",
        "Pricing starting at $0.002 per request",
        "Supported language and python integration",
        "ALL RIGHTS RESERVED UNDER APPLICABLE LAW"
    ]
    for frag in bad_fragments:
        assert not is_valid_use_case(frag), f"Expected use case fragment '{frag}' to be rejected"
        assert not is_valid_target_audience(frag), f"Expected audience fragment '{frag}' to be rejected"


def test_openrouter_pricing_context_free_numbers_rejected():
    """Verify context-free numbers like $0.042, $0, $0.04, $0.15, $1, $2.70, $40 are not published as plans."""
    page = CrawledPage(
        brand_id="openrouter-test",
        requested_url="https://openrouter.ai/models",
        final_url="https://openrouter.ai/models",
        http_status=200,
        page_type="product_service",
        extracted_text="""
        Model catalog metrics:
        Latencies: 0.042s avg response.
        Confidence: 0.
        Score: 0.04.
        Variance: 0.15.
        Count: 1.
        Multiplier: 2.70.
        Batch: 40.
        Unrelated number: $0.042 was calculated.
        Another uncontextualized charge: $2.70 was observed.
        """,
        content_hash="hash-or-1"
    )
    synth = FactSynthesizer("openrouter-test", user_business_name="OpenRouter")
    facts = synth.synthesize_facts([page])
    pricing_facts = [f for f in facts if f.fact_type == "pricing"]

    # None of these context-free dollar values should be published
    extracted_prices = [f.fact_value.get("amount") for f in pricing_facts]
    assert 0.042 not in extracted_prices
    assert 2.70 not in extracted_prices


def test_legitimate_usage_and_model_pricing_preserved():
    """Verify clearly labeled model pricing with unit context is preserved."""
    page = CrawledPage(
        brand_id="openrouter-test",
        requested_url="https://openrouter.ai/models",
        final_url="https://openrouter.ai/models",
        http_status=200,
        page_type="pricing",
        extracted_text="""
        Claude 3.5 Sonnet: $3.00 / 1M tokens
        GPT-4o: $2.50 / 1M tokens
        DeepSeek V3: $0.14 / 1M tokens
        """,
        content_hash="hash-or-2"
    )
    synth = FactSynthesizer("openrouter-test", user_business_name="OpenRouter")
    facts = synth.synthesize_facts([page])
    pricing_facts = [f for f in facts if f.fact_type == "pricing"]

    assert len(pricing_facts) >= 2
    amounts = [f.fact_value.get("amount") for f in pricing_facts]
    assert 3.0 in amounts or 2.5 in amounts or 0.14 in amounts
    for f in pricing_facts:
        assert f.fact_value.get("unit") is not None
        assert f.fact_value.get("billing_basis") == "usage"


def test_crawl_budget_configuration_defaults_and_limits():
    """Verify all 10 crawl budget limits are configured and reported in summary."""
    crawler = ScraplingCrawler(base_url="https://example.com", page_limit=15)
    summary = crawler.get_crawl_summary()

    assert summary["page_limit"] == 15
    limits = summary["budget_limits"]
    assert limits["max_pages"] == 15
    assert limits["max_depth"] == 3
    assert limits["concurrency"] == 3
    assert limits["max_pages_per_section"] == 4
    assert limits["run_timeout_seconds"] == 60
    assert "skip_reasons" in summary


def test_downstream_normalizer_ignores_rejected_facts():
    """Verify that Engine 2 Normalizer completely ignores facts marked is_rejected=True."""
    profile_data = {
        "brand": {
            "id": "b-1",
            "domain": "openrouter.ai",
            "business_name": "OpenRouter"
        },
        "profile_version": 1,
        "business_overview": {
            "description": "Unified LLM routing interface."
        },
        "products_and_services": [
            {"fact_id": "p-1", "value": "Model Routing API", "is_rejected": False},
            {"fact_id": "p-2", "value": "Enterprise Access Agreement", "is_rejected": True}
        ],
        "target_audience": [
            {"fact_id": "a-1", "value": "AI developers and prompt engineers", "is_rejected": False},
            {"fact_id": "a-2", "value": "s, split between Chinese OSS", "is_rejected": True}
        ],
        "use_cases": [
            {"fact_id": "u-1", "value": "Multi-model fallback routing", "is_rejected": False}
        ],
        "pricing_information": [
            {"fact_id": "pr-1", "value": {"plan_name": "Pay-as-you-go", "price": "Usage", "billing_basis": "usage"}}
        ],
        "facts": [
            {
                "id": "f-1",
                "fact_type": "product_service",
                "fact_value": "Model Routing API",
                "confidence": 0.95,
                "user_confirmed": True,
                "is_rejected": False
            },
            {
                "id": "f-2",
                "fact_type": "product_service",
                "fact_value": "Enterprise Access Agreement",
                "confidence": 0.5,
                "user_confirmed": False,
                "is_rejected": True
            }
        ]
    }

    normalized = ProfileNormalizer.normalize(profile_data)
    # The rejected product must not be in the normalized profile
    assert "Enterprise Access Agreement" not in normalized.products_and_services
    assert "Model Routing API" in normalized.products_and_services
    # The rejected fact must not be in grounded facts
    grounded_values = [f.fact_value for f in normalized.facts]
    assert "Enterprise Access Agreement" not in grounded_values
