"""Regressions for the Engine 1 -> Engine 2 -> Engine 3 pipeline failures seen in the live app.

Covers: hostname-derived brand names (country subdomains), short brand names causing
false positives in prompt validation and visibility evaluation, crawls blocked by WAFs
being treated as successful, and Gemini being silently replaced by the mock provider.
"""
import pytest

from app.core.brand_identity import (
    infer_business_name_from_host,
    is_inferred_business_name,
    registrable_domain,
    registrable_label,
)
from app.evaluator.evaluator import VisibilityResponseEvaluator
from app.evaluator.service import VisibilityEvaluatorService
from app.prompts.models import GeneratedPromptCandidate, NormalizedBrandProfile
from app.prompts.validator import PromptValidator
from app.services.profiler_service import assess_crawl_outcome


def test_registrable_domain_skips_country_and_www_subdomains():
    assert registrable_domain("in.louisvuitton.com") == "louisvuitton.com"
    assert registrable_domain("www.nike.com") == "nike.com"
    assert registrable_domain("example.co.uk") == "example.co.uk"
    assert registrable_label("in.louisvuitton.com") == "louisvuitton"


def test_business_name_inferred_from_host_is_not_a_country_code():
    assert infer_business_name_from_host("in.louisvuitton.com") == "Louisvuitton"
    assert infer_business_name_from_host("www.linear.app") == "Linear"
    assert infer_business_name_from_host("shop.example.co.uk") == "Example"


def test_inferred_business_name_detection_covers_legacy_placeholder():
    # Earlier builds stored the first hostname label ("In") as the business name.
    assert is_inferred_business_name("In", "in.louisvuitton.com")
    assert is_inferred_business_name("Louisvuitton", "in.louisvuitton.com")
    assert not is_inferred_business_name("Acme Corp", "acme.com")


def test_short_brand_name_is_not_a_forbidden_prompt_token():
    profile = NormalizedBrandProfile(
        brand_id="b-in",
        domain="in.louisvuitton.com",
        business_name="In",
        industry="Luxury Fashion",
        profile_version=1,
    )
    tokens = profile.get_forbidden_brand_tokens()
    assert "in" not in tokens
    assert "louisvuitton" in tokens

    candidate = GeneratedPromptCandidate(
        text="What are the best luxury handbag brands to buy in Paris?",
        category="discovery",
        intent="informational",
        buying_stage="awareness",
    )
    valid, reason = PromptValidator.validate(candidate, profile, reject_brand_mentions=True)
    assert valid, reason


def test_short_brand_name_does_not_match_ordinary_words_in_ai_answers():
    result = VisibilityResponseEvaluator.evaluate(
        response_text="Popular handbag options in Paris include structured totes and quilted bags.",
        brand_name="In",
        brand_domain="in.louisvuitton.com",
    )
    assert result.brand_mentioned is False


def test_brand_is_detected_by_root_domain_even_when_name_is_short():
    result = VisibilityResponseEvaluator.evaluate(
        response_text="Louis Vuitton (louisvuitton.com) is a well-known luxury house.",
        brand_name="In",
        brand_domain="in.louisvuitton.com",
    )
    assert result.brand_mentioned is True


def test_target_citations_match_root_domain_of_regional_subdomain():
    result = VisibilityResponseEvaluator.evaluate(
        response_text="See https://www.louisvuitton.com/eng-in/homepage for details.",
        brand_name="Louis Vuitton",
        brand_domain="in.louisvuitton.com",
    )
    assert result.target_brand_citations == ["https://www.louisvuitton.com/eng-in/homepage"]


def test_blocked_crawl_is_not_treated_as_successful_profile():
    blocked_page = {
        "http_status": 403,
        "extracted_text": "REF #0.4772c117 Access denied. We invite you to return at a later time to complete your purchase. " * 2,
    }
    failure = assess_crawl_outcome([blocked_page])
    assert failure is not None
    assert "403" in failure
    assert "blocked" in failure.lower()


def test_crawl_with_no_pages_is_a_failure():
    assert assess_crawl_outcome([]) is not None


def test_crawl_with_readable_homepage_is_a_success():
    page = {"http_status": 200, "extracted_text": "Linear builds issue tracking software for product teams. " * 3}
    assert assess_crawl_outcome([page]) is None


@pytest.mark.asyncio
async def test_crawler_counts_http_error_pages_as_failed_not_succeeded(monkeypatch):
    from app.core.config import settings
    from app.crawler import engine as engine_module
    from app.crawler.robots import RobotsPolicy
    from app.crawler.sitemap import SitemapDiscoverer

    async def fake_fetch_and_parse(self, client=None):
        return None

    async def fake_discover(self, seed_sitemaps=None):
        return []

    monkeypatch.setattr(RobotsPolicy, "fetch_and_parse", fake_fetch_and_parse)
    monkeypatch.setattr(RobotsPolicy, "is_allowed", lambda self, url: True)
    monkeypatch.setattr(SitemapDiscoverer, "discover", fake_discover)
    monkeypatch.setattr(settings, "PER_HOST_DELAY_SECONDS", 0.0)

    crawler = engine_module.ScraplingCrawler(base_url="https://in.louisvuitton.com/eng-in/homepage", page_limit=5)

    async def fake_fetch(url):
        return {
            "requested_url": url,
            "final_url": url,
            "canonical_url": None,
            "http_status": 403,
            "title": "LOUIS VUITTON",
            "headings": {"h1": ["Access denied."], "h2": []},
            "extracted_text": "Access denied. We invite you to return at a later time. " * 3,
            "internal_links": [],
            "external_links": [],
            "page_type": "other",
            "structured_data": [],
        }

    crawler._fetch_and_extract = fake_fetch
    pages = await crawler.run()

    assert crawler.pages_succeeded == 0
    assert crawler.pages_failed == 1
    assert crawler.get_crawl_summary()["useful_pages_produced"] == 0
    assert assess_crawl_outcome(pages) is not None


def test_gemini_provider_without_api_key_is_rejected_explicitly(monkeypatch):
    from app.core.config import settings

    monkeypatch.setattr(settings, "LLM_API_KEY", None)
    with pytest.raises(ValueError, match="LLM_API_KEY"):
        import asyncio
        asyncio.run(VisibilityEvaluatorService.create_scan(brand_id="any", provider="gemini"))
