"""Focused regression tests for Scrapling HTML extraction and SPA/auth diagnostics."""
import pytest
from unittest.mock import MagicMock
from app.crawler.engine import extract_html_from_response, ScraplingCrawler
from app.extractor.page_extractor import extract_page_content
from app.extractor.fact_synthesizer import FactSynthesizer
from app.db.models import CrawledPage


class MockScraplingTextHandler:
    """Simulates Scrapling TextHandler which is empty string for root html element."""
    def __init__(self, text: str = ""):
        self._text = text

    def __str__(self):
        return self._text

    def __bool__(self):
        return bool(self._text)


def test_scrapling_response_body_extraction_preserves_html():
    """Verify that Scrapling Response with body bytes and empty text property is properly decoded."""
    raw_html = (
        b"<!doctype html>"
        b"<html lang=\"en\">"
        b"<head><title>Aurora Analytics - AI Platform</title>"
        b"<meta name=\"description\" content=\"Enterprise AI visibility and intelligence platform for modern brands.\">"
        b"</head>"
        b"<body>"
        b"<h1>Aurora Analytics Engine</h1>"
        b"<h2>Real-time Search Extraction</h2>"
        b"<p>We help businesses understand how generative AI systems represent their brand.</p>"
        b"</body>"
        b"</html>"
    )

    mock_resp = MagicMock()
    mock_resp.body = raw_html
    mock_resp.encoding = "utf-8"
    mock_resp.html_content = None
    mock_resp.text = MockScraplingTextHandler("")

    extracted_html = extract_html_from_response(mock_resp)
    assert len(extracted_html) > 0
    assert "Aurora Analytics Engine" in extracted_html

    page_data = extract_page_content(
        html=extracted_html,
        requested_url="https://aurora-analytics.com",
        final_url="https://aurora-analytics.com/",
        http_status=200,
        base_domain="aurora-analytics.com"
    )

    assert page_data["extraction_status"] == "success"
    assert page_data["title"] == "Aurora Analytics - AI Platform"
    assert "Enterprise AI visibility" in page_data["meta_description"]
    assert "Aurora Analytics Engine" in page_data["headings"]["h1"]
    assert "Real-time Search Extraction" in page_data["headings"]["h2"]
    assert len(page_data["extracted_text"]) > 0

    # Verify fact synthesis
    page = CrawledPage(
        brand_id="test-brand",
        profile_run_id="test-run",
        requested_url=page_data["requested_url"],
        final_url=page_data["final_url"],
        http_status=page_data["http_status"],
        title=page_data["title"],
        meta_description=page_data["meta_description"],
        headings=page_data["headings"],
        extracted_text=page_data["extracted_text"],
        structured_data=page_data["structured_data"],
        page_type=page_data["page_type"],
        content_hash=page_data["content_hash"]
    )

    synth = FactSynthesizer("test-brand", profile_version=1)
    facts = synth.synthesize_facts([page])

    # Must extract business name, company description, and products/services
    fact_types = {f.fact_type for f in facts}
    assert "business_name" in fact_types
    assert "company_description" in fact_types
    assert "product_service" in fact_types

    desc_fact = next(f for f in facts if f.fact_type == "company_description")
    assert "Enterprise AI visibility" in desc_fact.fact_value
    assert desc_fact.user_confirmed is False
    assert desc_fact.source_url == "https://aurora-analytics.com/"


def test_spa_auth_portal_diagnostic_status():
    """Verify that pages with SPA div markers or login titles get descriptive error_details."""
    spa_html = (
        "<!doctype html>"
        "<html><head><title>App Login Portal</title></head>"
        "<body><div id=\"__next\"></div><script src=\"/bundle.js\"></script></body>"
        "</html>"
    )

    page_data = extract_page_content(
        html=spa_html,
        requested_url="https://app.example.com/login",
        final_url="https://app.example.com/login",
        http_status=200,
        base_domain="app.example.com"
    )

    assert page_data["extraction_status"] == "partial"
    assert "client-rendered single-page app or authentication portal" in page_data["error_details"]
