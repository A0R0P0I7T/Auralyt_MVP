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


def test_pricing_filters_out_funding_arr_and_scale_multipliers():
    """Verify that ARR, funding rounds, valuations, and scale suffixes are excluded from pricing plans."""
    page = CrawledPage(
        brand_id="linear-brand",
        profile_run_id="run-1",
        requested_url="https://linear.app/now",
        final_url="https://linear.app/now",
        http_status=200,
        title="Updates from Linear",
        meta_description="Linear passes milestones.",
        headings={"h1": ["Updates"], "h2": []},
        extracted_text="""
        As Linear passes $100 million in ARR, we celebrate with our team.
        Earlier, Linear raised a $13M Series A led by Sequoia.
        Our demo dashboard showed total revenue $47.8K.
        Meanwhile, our Standard plan is $10/mo per user and Plus plan is $20/month.
        """,
        structured_data=[],
        page_type="blog",
        content_hash="hash-pricing-1"
    )

    synth = FactSynthesizer("linear-brand", user_business_name="Linear")
    facts = synth.synthesize_facts([page])

    pricing_facts = [f for f in facts if f.fact_type == "pricing"]
    price_texts = [f.fact_value.get("price_text") for f in pricing_facts]

    # $100 million ARR, $13M Series A, and $47.8K revenue must be rejected
    assert "$100" not in price_texts
    assert "$13" not in price_texts
    assert "$47" not in price_texts
    # Genuine subscription pricing must be retained
    assert any("$10/mo" in pt or "$10" in pt for pt in price_texts)


def test_audience_quality_and_deduplication():
    """Verify audience extraction filters out performance attributes, time periods, and quotes, and deduplicates."""
    page = CrawledPage(
        brand_id="brand-aud",
        profile_run_id="run-1",
        requested_url="https://example.com/platform",
        final_url="https://example.com/platform",
        http_status=200,
        title="Platform Overview",
        headings={"h1": ["Platform"], "h2": []},
        extracted_text="""
        Built for speed.
        Designed for the future.
        Built for the future.
        Designed for privacy.
        "This is today's reality," said Angela DeFranco, GM of Marketing Hub at HubSpot.
        Built for modern teams with AI workflows.
        Built for modern teams with AI workflows.
        Designed for enterprise marketing leaders.
        """,
        structured_data=[],
        page_type="homepage",
        content_hash="hash-aud-1"
    )

    synth = FactSynthesizer("brand-aud", user_business_name="Example")
    facts = synth.synthesize_facts([page])

    aud_facts = [f for f in facts if f.fact_type == "target_audience"]
    aud_values = [f.fact_value.lower() for f in aud_facts]

    # Non-audience concepts must be rejected
    assert not any(v == "speed" for v in aud_values)
    assert not any(v == "the future" for v in aud_values)
    assert not any(v == "privacy" for v in aud_values)
    assert not any("said angela" in v for v in aud_values)

    # Valid role/team audiences must be accepted
    assert any("modern teams" in v for v in aud_values)
    assert any("enterprise marketing leaders" in v for v in aud_values)

    # Deduplication check: "modern teams with AI workflows" must only appear once
    modern_teams_count = sum(1 for v in aud_values if "modern teams with ai workflows" in v)
    assert modern_teams_count == 1


def test_product_candidate_validation_rejects_slogans_and_ctas():
    """Verify is_valid_product_candidate filters out marketing sentences, action verbs, and CTA headings."""
    from app.extractor.fact_synthesizer import is_valid_product_candidate

    assert not is_valid_product_candidate("Measure")
    assert not is_valid_product_candidate("Recommend")
    assert not is_valid_product_candidate("Act")
    assert not is_valid_product_candidate("From insight to action, without the Frankenstack")
    assert not is_valid_product_candidate("Execute AEO at scale, natively in Webflow")
    assert not is_valid_product_candidate("All platform features")
    assert not is_valid_product_candidate("Frequently asked questions")
    assert not is_valid_product_candidate("Get More Information About Onboarding Services")
    assert not is_valid_product_candidate("#MadeinWebflow")
    assert not is_valid_product_candidate("Build for what's next.")
    assert not is_valid_product_candidate("Find a Partner")
    assert not is_valid_product_candidate("Choose from 114 partners")

    assert is_valid_product_candidate("Customer Platform Onboarding")
    assert is_valid_product_candidate("Linear Insights")
    assert is_valid_product_candidate("Webflow CMS")
    assert is_valid_product_candidate("AI Gateway")


def test_decorative_duplicate_headings_cleaned():
    """Verify metadata heading extraction cleans accessibility/decorative duplicate text layers."""
    from app.extractor.metadata import extract_metadata_and_structured_data

    html = """
    <!doctype html>
    <html>
    <head><title>Linear Features</title></head>
    <body>
    <h1>
        <span>The system for modern product development</span>
        <span aria-hidden="true"> The system for modern product development</span>
    </h1>
    <h2>
        <span>Core workflows</span>
        <span> Core workflows</span>
    </h2>
    </body>
    </html>
    """
    meta = extract_metadata_and_structured_data(html, "https://linear.app/features")
    h1_list = meta["headings"]["h1"]
    h2_list = meta["headings"]["h2"]

    assert h1_list == ["The system for modern product development"]
    assert h2_list == ["Core workflows"]


def test_homepage_heading_product_extraction_avoids_brand_name_duplication():
    """Verify homepage heading extraction captures valid product candidates while rejecting brand name duplication."""
    from app.extractor.fact_synthesizer import is_valid_product_candidate

    assert not is_valid_product_candidate("Linear", brand_name="Linear")
    assert not is_valid_product_candidate("Vercel", brand_name="Vercel")
    assert is_valid_product_candidate("Linear Insights", brand_name="Linear")

    page = CrawledPage(
        brand_id="test-linear",
        profile_run_id="run-lin-1",
        requested_url="https://linear.app",
        final_url="https://linear.app/",
        http_status=200,
        title="Linear — Purpose-built for planning and building products",
        meta_description="Linear helps plan and build products.",
        headings={
            "h1": ["Linear", "Linear Insights"],
            "h2": ["Core Workflows", "Privacy Policy"]
        },
        extracted_text="Linear is built for high-performance teams.",
        structured_data=[],
        page_type="homepage",
        content_hash="hash-lin-1"
    )

    synth = FactSynthesizer("test-linear", user_business_name="Linear")
    facts = synth.synthesize_facts([page])

    products = [f.fact_value.get("name") for f in facts if f.fact_type == "product_service"]
    assert "Linear Insights" in products
    assert "Linear" not in products


def test_company_description_rejects_single_product_stories_and_selects_brand_mission():
    """Verify company description extraction rejects individual garment/story descriptions and selects real brand landing descriptions."""
    homepage = CrawledPage(
        brand_id="test-nike",
        profile_run_id="run-nike-1",
        requested_url="https://www.nike.com",
        final_url="https://www.nike.com/",
        http_status=200,
        title="Nike. Just Do It. Nike.com",
        meta_description=None,
        headings={"h1": [], "h2": []},
        extracted_text="Nike homepage content.",
        structured_data=[],
        page_type="homepage",
        content_hash="hash-home"
    )
    story_page = CrawledPage(
        brand_id="test-nike",
        profile_run_id="run-nike-1",
        requested_url="https://www.nike.com/acg/acg-aireez",
        final_url="https://www.nike.com/acg/acg-aireez",
        http_status=200,
        title="Field Test: ACG Aireez Long-Sleeve. Nike.com",
        meta_description="The ACG Aireez Long-Sleeve goes on a journey to a salt flat in France.",
        headings={"h1": ["ACG Aireez"], "h2": []},
        extracted_text="Story content.",
        structured_data=[],
        page_type="blog",
        content_hash="hash-story"
    )
    brand_landing_page = CrawledPage(
        brand_id="test-nike",
        profile_run_id="run-nike-1",
        requested_url="https://www.nike.com/at/en",
        final_url="https://www.nike.com/at/en",
        http_status=200,
        title="Nike. Just Do It. Nike AT",
        meta_description="Inspiring the world's athletes, Nike delivers innovative products, experiences and services.",
        headings={"h1": ["Nike"], "h2": []},
        extracted_text="Nike delivers innovative products to inspire athletes worldwide.",
        structured_data=[],
        page_type="landing",
        content_hash="hash-landing"
    )

    synth = FactSynthesizer("test-nike", user_business_name="Nike")
    facts = synth.synthesize_facts([homepage, story_page, brand_landing_page])

    desc_fact = next((f for f in facts if f.fact_type == "company_description"), None)
    assert desc_fact is not None
    assert "The ACG Aireez Long-Sleeve" not in desc_fact.fact_value
    assert "Nike delivers innovative products" in desc_fact.fact_value
    assert desc_fact.source_url == "https://www.nike.com/at/en"


def test_product_candidate_validation_preserves_tech_names_and_rejects_navigation():
    """Verify is_valid_product_candidate preserves tech products and compound titles while rejecting navigation labels and multi-sentence slogans."""
    from app.extractor.fact_synthesizer import is_valid_product_candidate

    # Legitimate products preserved (acceptance cases)
    assert is_valid_product_candidate("Next.js")
    assert is_valid_product_candidate("v0.dev")
    assert is_valid_product_candidate("Dri-FIT")
    assert is_valid_product_candidate("HubSpot Marketing Hub Enterprise")
    assert is_valid_product_candidate("Customer Platform Onboarding")
    assert is_valid_product_candidate("Linear Insights")
    assert is_valid_product_candidate("Webflow CMS")

    # Navigation labels and UI headers rejected (rejection cases)
    assert not is_valid_product_candidate("Product")
    assert not is_valid_product_candidate("Resources")
    assert not is_valid_product_candidate("Company")
    assert not is_valid_product_candidate("Trust")
    assert not is_valid_product_candidate("Solutions")
    assert not is_valid_product_candidate("Pricing")
    assert not is_valid_product_candidate("Overview")

    # Marketing slogans and multi-sentence headlines rejected
    assert not is_valid_product_candidate("Trusted in production. Proven at scale.")
    assert not is_valid_product_candidate("Power your AI with real-time web search")
    assert not is_valid_product_candidate("Tavily in action")
    assert not is_valid_product_candidate("Enterprise-grade security, built in!")


def test_pricing_filters_prizes_and_fines_while_preserving_usage_and_packages():
    """Verify pricing extraction rejects funding rounds, prizes, and fines while preserving usage-based rates and packages."""
    page = CrawledPage(
        brand_id="test-pricing-audit",
        profile_run_id="run-p-1",
        requested_url="https://example.com/api",
        final_url="https://example.com/api",
        http_status=200,
        title="API Pricing & Usage",
        meta_description="Pay-as-you-go pricing.",
        headings={"h1": ["Pricing"], "h2": []},
        extracted_text="""
        Competition announcement: Winners take home $2,450 in prizes this week!
        Regulatory update: The court issued fines of $4B against antitrust violators.
        Funding milestone: The startup secured a $35M round of mezzanine financing.
        Company news: Reduced tech costs by $600K through efficiency programs.

        API Usage:
        Starting rate is $0.008 / credit for high-volume endpoints.
        Vector indexing costs $0.50 per 1M requests.
        Enterprise Onboarding Package: Price: $10,000 one-time flat rate.
        Monthly subscription: $15/mo billed annually.
        """,
        structured_data=[],
        page_type="product_service",
        content_hash="hash-p-1"
    )

    synth = FactSynthesizer("test-pricing-audit", user_business_name="Example")
    facts = synth.synthesize_facts([page])

    pricing_facts = [f for f in facts if f.fact_type == "pricing"]
    extracted_prices = [f.fact_value.get("price_text") for f in pricing_facts]

    # False positives rejected
    assert "$2,450" not in extracted_prices
    assert "$4" not in extracted_prices
    assert "$35" not in extracted_prices
    assert "$600" not in extracted_prices

    # Legitimate prices preserved
    assert any("$0.008" in p for p in extracted_prices)
    assert any("$0.50" in p for p in extracted_prices)
    assert any("$10,000" in p for p in extracted_prices)
    assert any("$15" in p for p in extracted_prices)


def test_target_audience_filters_abstract_metrics_and_preserves_diverse_roles():
    """Verify target audience rejects abstract metrics while preserving diverse professional and organizational segments."""
    page = CrawledPage(
        brand_id="test-aud-audit",
        profile_run_id="run-a-1",
        requested_url="https://example.com/overview",
        final_url="https://example.com/overview",
        http_status=200,
        title="Platform Overview",
        meta_description="Who we serve.",
        headings={"h1": ["Overview"], "h2": []},
        extracted_text="""
        Built for enterprise scale, performance, and reliability.
        Designed for enterprise scale.
        Built for speed and modern aesthetics.
        Made for a great caption: "even the best years have a crash in them".
        Designed for the communication between frontend and backend services.

        Built for freelancers and consultants managing high-velocity projects.
        Designed for nonprofit organizations and educational institutions.
        Made for product teams building agentic AI applications.
        """,
        structured_data=[],
        page_type="homepage",
        content_hash="hash-a-1"
    )

    synth = FactSynthesizer("test-aud-audit", user_business_name="Example")
    facts = synth.synthesize_facts([page])

    audiences = [f.fact_value.lower() for f in facts if f.fact_type == "target_audience"]

    # Abstract metrics and captions rejected
    assert not any("enterprise scale, performance" in a for a in audiences)
    assert not any(a == "enterprise scale" for a in audiences)
    assert not any("caption:" in a for a in audiences)
    assert not any("communication between" in a for a in audiences)
    assert not any(a == "speed" for a in audiences)

    # Legitimate diverse segments preserved
    assert any("freelancers and consultants" in a for a in audiences)
    assert any("nonprofit organizations" in a for a in audiences)
    assert any("product teams" in a for a in audiences)


def test_contact_info_filters_search_queries_video_links_and_personal_profiles():
    """Verify contact info extraction rejects search URLs, video watch links, and personal author accounts while preserving corporate channels."""
    page = CrawledPage(
        brand_id="test-contact-audit",
        profile_run_id="run-c-1",
        requested_url="https://example.com/contact",
        final_url="https://example.com/contact",
        http_status=200,
        title="Contact Us",
        meta_description="Get in touch.",
        headings={"h1": ["Contact"], "h2": []},
        extracted_text="Email: support@example.com",
        structured_data=[],
        page_type="contact",
        external_links=[
            "http://search.twitter.com/search?q=%23inbound",
            "https://twitter.com/intent/tweet?text=hello",
            "https://www.youtube.com/watch?v=pYpw5jqI0l8",
            "https://www.youtube.com/shorts/sample123",
            "https://www.linkedin.com/in/author-caroline-123",
            "https://www.linkedin.com/posts/jonfor-sample-post",
            "https://github.com/sample-project/repo/blob/main/README.md",
            "https://www.linkedin.com/company/example-corp",
            "https://x.com/ExampleCorp",
            "https://youtube.com/user/ExampleCorp",
            "https://github.com/example-corp"
        ],
        content_hash="hash-c-1"
    )
    blog_page = CrawledPage(
        brand_id="test-contact-audit",
        requested_url="https://example.com/blog/article-1",
        final_url="https://example.com/blog/article-1",
        http_status=200,
        title="Engineering at Example",
        page_type="blog",
        external_links=[
            "https://twitter.com/hbfleish",
            "https://twitter.com/jeff",
            "https://twitter.com/ExampleCorp"
        ],
        content_hash="hash-c-2"
    )

    synth = FactSynthesizer("test-contact-audit", user_business_name="Example")
    facts = synth.synthesize_facts([page, blog_page])

    contacts = [f.fact_value for f in facts if f.fact_type == "contact_info"]
    social_urls = [c.get("url") for c in contacts if isinstance(c, dict) and c.get("type") == "social_profile"]

    # Noise rejected
    assert "http://search.twitter.com/search?q=%23inbound" not in social_urls
    assert "https://www.youtube.com/watch?v=pYpw5jqI0l8" not in social_urls
    assert "https://www.youtube.com/shorts/sample123" not in social_urls
    assert "https://www.linkedin.com/in/author-caroline-123" not in social_urls
    assert "https://www.linkedin.com/posts/jonfor-sample-post" not in social_urls
    assert "https://github.com/sample-project/repo/blob/main/README.md" not in social_urls
    assert "https://twitter.com/hbfleish" not in social_urls
    assert "https://twitter.com/jeff" not in social_urls

    # Corporate channels preserved
    assert "https://www.linkedin.com/company/example-corp" in social_urls
    assert "https://x.com/ExampleCorp" in social_urls
    assert "https://youtube.com/user/ExampleCorp" in social_urls
    assert "https://github.com/example-corp" in social_urls


def test_product_candidate_rejects_legal_clauses_and_doc_headings():
    """Verify is_valid_product_candidate rejects legal contracts, clauses, and doc guides."""
    from app.extractor.fact_synthesizer import is_valid_product_candidate

    # Legal clauses and contracts
    assert not is_valid_product_candidate("Enterprise Access Agreement")
    assert not is_valid_product_candidate("Recitals")
    assert not is_valid_product_candidate("2.1 License Grant")
    assert not is_valid_product_candidate("5.1 Fees and Payment")
    assert not is_valid_product_candidate("Schedule 1: Permitted Use")
    assert not is_valid_product_candidate("Exhibit A: Terms")
    assert not is_valid_product_candidate("General Provisions")
    assert not is_valid_product_candidate("Limitation of Liability")
    assert not is_valid_product_candidate("Terms of Service")
    assert not is_valid_product_candidate("Privacy Policy")

    # Zero-width spaces and doc guides
    assert not is_valid_product_candidate("\u200b Using In-Region Routing")
    assert not is_valid_product_candidate("How to configure routing")
    assert not is_valid_product_candidate("Feature availability matrix")
    assert not is_valid_product_candidate("Troubleshooting guide")

    # Legitimate products preserved
    assert is_valid_product_candidate("Model Routing Engine")
    assert is_valid_product_candidate("Prompt Caching")
    assert is_valid_product_candidate("LLM Gateway")


def test_use_case_and_audience_rejects_fragments_and_market_comparisons():
    """Verify use-cases and audiences reject grammar fragments and market-share commentary."""
    page = CrawledPage(
        brand_id="test-brand",
        requested_url="https://example.com/about",
        final_url="https://example.com/about",
        http_status=200,
        page_type="about",
        extracted_text="""
        Use cases, split between Chinese OSS and RoW OSS: benchmark comparison.
        Our use cases are expanding rapidly across industries.
        As use cases grew exponentially, we hired more engineers.
        ALL RIGHTS RESERVED UNDER THE APPLICABLE LAW.
        
        Use Cases: Multi-agent Customer Support Workflow
        Solutions for: Enterprise Content Generation
        Built for: Machine learning engineers and AI product teams
        """,
        content_hash="hash-uc-1"
    )
    synth = FactSynthesizer("test-brand", user_business_name="Example")
    facts = synth.synthesize_facts([page])

    use_cases = [f.fact_value for f in facts if f.fact_type == "use_case"]
    audiences = [f.fact_value for f in facts if f.fact_type == "target_audience"]

    # Fragments and noise rejected
    assert not any(uc.lower().startswith("s,") for uc in use_cases)
    assert not any(uc.lower().startswith("s are") for uc in use_cases)
    assert not any(uc.lower().startswith("s grew") for uc in use_cases)
    assert not any("chinese oss" in uc.lower() for uc in use_cases)
    assert not any("all rights reserved" in uc.lower() for uc in use_cases)

    # Legitimate use cases and audiences preserved
    assert any("Multi-agent Customer Support" in uc for uc in use_cases)
    assert any("Enterprise Content Generation" in uc for uc in use_cases)
    assert any("Machine learning engineers" in a for a in audiences)


def test_pricing_on_dedicated_pricing_page_extracts_structured_plans():
    """Verify structured plan extraction on dedicated pricing pages."""
    pricing_page = CrawledPage(
        brand_id="test-pricing-plans",
        requested_url="https://example.com/pricing",
        final_url="https://example.com/pricing",
        http_status=200,
        page_type="pricing",
        extracted_text="""
        Choose the plan that fits your business:
        Free Plan: $0 / mo forever for individuals.
        Pro Tier: $20 / month billed annually.
        Enterprise: $200 / user / month for large teams.
        """,
        content_hash="hash-pricing-plans"
    )
    synth = FactSynthesizer("test-pricing-plans", user_business_name="Example")
    facts = synth.synthesize_facts([pricing_page])

    pricing_facts = [f for f in facts if f.fact_type == "pricing"]
    assert len(pricing_facts) >= 2
    plans = {f.fact_value.get("plan_name"): f.fact_value for f in pricing_facts}
    assert "Pro" in plans
    assert plans["Pro"]["amount"] == 20.0
    assert "price_text" in plans["Pro"]
    assert "model" in plans["Pro"]


def test_crawler_budget_tracking_and_summary():
    """Verify crawler budget configuration and crawl summary structure."""
    from app.crawler.engine import ScraplingCrawler

    crawler = ScraplingCrawler(base_url="https://example.com", page_limit=25)
    summary = crawler.get_crawl_summary()
    assert summary["page_limit"] == 25
    assert "category_quotas" in summary
    assert "budget_limits" in summary
    assert summary["budget_limits"]["max_pages_per_section"] == 4
    assert "skip_reasons" in summary




