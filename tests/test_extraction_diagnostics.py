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


def test_boilerplate_headings_excluded_from_metadata():
    """Verify that headings inside header, footer, nav, and boilerplate containers are stripped."""
    html = """
    <!doctype html>
    <html>
    <head><title>Nike Official Store</title></head>
    <body>
        <header>
            <div id="header-search">
                <a href="/help"><h1>GET HELP</h1></a>
            </div>
        </header>
        <main>
            <h1>Nike Air Max 90</h1>
            <h2>Iconic Cushioning</h2>
            <p>The Nike Air Max 90 stays true to its OG running roots.</p>
        </main>
        <footer>
            <div class="footer-links">
                <h2>Africa</h2>
                <h2>Americas</h2>
                <h2>Asia Pacific</h2>
                <h2>Europe</h2>
                <h2>Middle East</h2>
            </div>
        </footer>
    </body>
    </html>
    """
    from app.extractor.metadata import extract_metadata_and_structured_data
    meta = extract_metadata_and_structured_data(html, "https://www.nike.com/t/air-max-90")

    h1_list = meta["headings"]["h1"]
    h2_list = meta["headings"]["h2"]

    # Main content headings must be retained
    assert "Nike Air Max 90" in h1_list
    assert "Iconic Cushioning" in h2_list

    # Boilerplate headings must be excluded
    assert "GET HELP" not in h1_list
    assert "Africa" not in h2_list
    assert "Americas" not in h2_list
    assert "Europe" not in h2_list
    assert "Middle East" not in h2_list


def test_page_classification_hierarchy_faq_vs_product():
    """Verify that help/FAQ pages are prioritized over generic product keyword matching."""
    from app.extractor.page_classifier import classify_page_type

    # Help article containing 'product' in path
    assert classify_page_type("https://www.nike.com/help/a/product-discount", title="Product Discounts | Nike Help") == "faq"
    assert classify_page_type("https://www.nike.com/help/a/find-product", title="Find a Product | Nike Help") == "faq"
    assert classify_page_type("https://www.nike.com/help", title="Nike Customer Service") == "faq"

    # E-commerce PDP paths
    assert classify_page_type("https://www.nike.com/t/24-7-womens-shoes-j9v0Ciab", title="Nike 24.7 Women's Shoes") == "product_service"
    assert classify_page_type("https://www.nike.com/products/running-shoe", title="Running Shoe") == "product_service"

    # Structured data hinting product
    sd_product = [{"@type": "ProductGroup", "name": "Running Shoes"}]
    assert classify_page_type("https://www.nike.com/shoes/group", title="Shoes", structured_data=sd_product) == "product_service"


def test_disallowed_product_labels_filtered_out():
    """Verify that generic UI, region, and interface terms are never synthesized as products."""
    page = CrawledPage(
        brand_id="nike-brand",
        profile_run_id="run-1",
        requested_url="https://www.nike.com/t/air-zoom",
        final_url="https://www.nike.com/t/air-zoom",
        http_status=200,
        title="Nike Air Zoom",
        meta_description="Lightweight speed.",
        headings={
            "h1": ["Nike Air Zoom Pegasus", "GET HELP"],
            "h2": ["Running Shoe", "Africa", "Americas", "Asia Pacific", "Europe", "Middle East", "Privacy Policy"]
        },
        extracted_text="Designed for speed and comfort.",
        structured_data=[],
        page_type="product_service",
        content_hash="hash123"
    )

    synth = FactSynthesizer("nike-brand", user_business_name="Nike")
    facts = synth.synthesize_facts([page])

    product_names = [f.fact_value.get("name") for f in facts if f.fact_type == "product_service"]

    # Legitimate product retained
    assert "Nike Air Zoom Pegasus" in product_names
    assert "Running Shoe" in product_names

    # Irrelevant labels excluded
    assert "GET HELP" not in product_names
    assert "Africa" not in product_names
    assert "Americas" not in product_names
    assert "Asia Pacific" not in product_names
    assert "Europe" not in product_names
    assert "Middle East" not in product_names
    assert "Privacy Policy" not in product_names


def test_structured_data_product_group_and_variant_pricing():
    """Verify ProductGroup structured data extracts products, audience, and variant offers."""
    structured_data = [
        {
            "@type": "ProductGroup",
            "name": "Nike Invincible 3",
            "description": "Max cushioning running shoe designed for runners.",
            "audience": {
                "@type": "PeopleAudience",
                "suggestedGender": "https://schema.org/Unisex",
                "suggestedMinAge": 16
            },
            "hasVariant": [
                {
                    "@type": "Product",
                    "name": "Nike Invincible 3 - White",
                    "offers": {
                        "@type": "Offer",
                        "price": 180,
                        "priceCurrency": "USD"
                    }
                }
            ]
        }
    ]

    page = CrawledPage(
        brand_id="nike-brand",
        profile_run_id="run-1",
        requested_url="https://www.nike.com/t/invincible-3",
        final_url="https://www.nike.com/t/invincible-3",
        http_status=200,
        title="Nike Invincible 3",
        meta_description="Max cushioning.",
        headings={"h1": [], "h2": []},
        extracted_text="The ultimate cushioned ride.",
        structured_data=structured_data,
        page_type="product_service",
        content_hash="hash456"
    )

    synth = FactSynthesizer("nike-brand", user_business_name="Nike")
    facts = synth.synthesize_facts([page])

    fact_types = {f.fact_type for f in facts}
    assert "product_service" in fact_types
    assert "target_audience" in fact_types
    assert "pricing" in fact_types

    pricing_fact = next(f for f in facts if f.fact_type == "pricing")
    assert pricing_fact.fact_value["price"] == "180"
    assert pricing_fact.fact_value["currency"] == "USD"

    audience_fact = next(f for f in facts if f.fact_type == "target_audience")
    assert "Unisex" in audience_fact.fact_value
    assert "16+" in audience_fact.fact_value


def test_faq_facts_extracted_from_faq_pages():
    """Verify FAQ extraction from pages classified as faq."""
    page = CrawledPage(
        brand_id="nike-brand",
        profile_run_id="run-1",
        requested_url="https://www.nike.com/help/a/student-discount",
        final_url="https://www.nike.com/help/a/student-discount",
        http_status=200,
        title="Does Nike Offer a Student Discount? | Nike Help",
        meta_description="Eligible students can get 10% off most Nike items once verified.",
        headings={"h1": ["Does Nike Offer a Student Discount?"], "h2": []},
        extracted_text="Eligible students can get 10% off most Nike items once verified.",
        structured_data=[],
        page_type="faq",
        content_hash="hash789"
    )

    synth = FactSynthesizer("nike-brand", user_business_name="Nike")
    facts = synth.synthesize_facts([page])

    faq_facts = [f for f in facts if f.fact_type == "faq"]
    assert len(faq_facts) == 1
    assert faq_facts[0].fact_value["question"] == "Does Nike Offer a Student Discount?"
    assert "10% off" in faq_facts[0].fact_value["answer"]
    assert faq_facts[0].source_url == "https://www.nike.com/help/a/student-discount"

