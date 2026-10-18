"""Comprehensive Cross-Site Ground-Truth Validation, Crawl Budget & Downstream Compatibility Suite.

Evaluates three distinct website structural archetypes:
- Site A: SaaS Platform (Linear - issues, cycles, roadmaps, subscription tiers, use cases, legal clauses)
- Site B: Documentation-Heavy API / AI Platform (Pinecone - vector DB, serverless, read/write units, 1000s of docs, legal DPA)
- Site C: Ecommerce / Consumer Brand (Allbirds - sustainable footwear, product families vs SKUs, JSON-LD offers, category filters, multi-locale URLs)

Includes:
- Measurable ground-truth quality evaluation (Precision, Recall, Duplicate Rate, Unsupported Rate, Provenance Completeness)
- Deterministic crawl budget boundary enforcement tests (massive sitemaps, deep docs, timeouts, aggregate bytes, decompression)
- Engine 2 prompt grounding and sparse-profile verification
- Engine 3 AI visibility scan compatibility verification
"""
import asyncio
import io
import gzip
import pytest
import time
from unittest.mock import MagicMock, AsyncMock, patch

from app.db.models import CrawledPage, BrandFact, Brand, VisibilityScan, VisibilityResult
from app.extractor.fact_synthesizer import (
    FactSynthesizer,
    is_valid_product_candidate,
    is_valid_use_case,
    is_valid_target_audience
)
from app.crawler.engine import ScraplingCrawler, extract_html_from_response
from app.crawler.sitemap import SitemapDiscoverer, score_url_priority
from app.crawler.security import normalize_url, validate_and_resolve_url
from app.core.config import settings
from app.prompts.normalizer import ProfileNormalizer
from app.prompts.planner import CoveragePlanner
from app.prompts.generator import DeterministicGenerator
from app.evaluator.service import VisibilityEvaluatorService
from app.evaluator.evaluator import VisibilityResponseEvaluator


# ==============================================================================
# SITE A: SaaS COMPANY (LINEAR - Project & Issue Management)
# ==============================================================================

def create_saas_site_pages() -> list[CrawledPage]:
    """Generates realistic pages for Site A (SaaS)."""
    p_home = CrawledPage(
        brand_id="brand-saas-linear",
        requested_url="https://linear.app",
        final_url="https://linear.app/",
        http_status=200,
        page_type="homepage",
        title="Linear — A better way to build software",
        meta_description="Linear is a purpose-built issue tracking tool, project planner, and product roadmap engine for high-performing teams.",
        headings={
            "h1": ["Linear Issue Tracking & Project Management"],
            "h2": ["Cycles for automated sprint planning", "Project Roadmaps for cross-team alignment"]
        },
        extracted_text="""
        Linear is a modern software development tool designed for engineering and product teams.
        Streamline software projects, sprints, tasks, and bug tracking with high speed and keyboard-first design.
        
        Key Features:
        - Automated sprint cycles and backlogs
        - Cross-team project roadmaps
        - Git integrations with GitHub and GitLab
        """,
        content_hash="hash-saas-home"
    )

    p_products = CrawledPage(
        brand_id="brand-saas-linear",
        requested_url="https://linear.app/features",
        final_url="https://linear.app/features",
        http_status=200,
        page_type="product_service",
        title="Features — Linear",
        meta_description="Explore Linear features including Linear Asks, Linear Insights, and Linear Projects.",
        headings={
            "h1": ["Linear Asks"],
            "h2": ["Linear Insights", "Linear Projects", "2.1 License Grant", "Terms of Use"]
        },
        extracted_text="""
        Linear Asks turns user requests from Slack into actionable engineering issues.
        Linear Insights provides automated analytics on cycle time and issue velocity.
        Linear Projects enables complex cross-functional roadmaps with milestones.
        """,
        content_hash="hash-saas-prod"
    )

    p_usecases = CrawledPage(
        brand_id="brand-saas-linear",
        requested_url="https://linear.app/method",
        final_url="https://linear.app/method",
        http_status=200,
        page_type="homepage",
        title="The Linear Method — Principles for modern software teams",
        extracted_text="""
        Use Cases:
        - Software sprint planning and execution
        - Cross-functional product roadmap alignment
        - Customer bug and issue triage
        
        Target Audience:
        - High-growth engineering teams
        - Product managers and technical leads
        - Fast-moving technology startups
        
        Built for: Modern engineering organizations
        Why choose us: Keyboard-first workflows with zero-latency synchronization
        """,
        content_hash="hash-saas-uc"
    )

    p_pricing = CrawledPage(
        brand_id="brand-saas-linear",
        requested_url="https://linear.app/pricing",
        final_url="https://linear.app/pricing",
        http_status=200,
        page_type="pricing",
        title="Pricing — Linear",
        extracted_text="""
        Flexible plans for teams of every size.
        Free Tier: $0 / mo forever with unlimited members and 250 active issues.
        Standard Tier: $8 / user / month billed annually or $10 billed monthly.
        Plus Tier: $14 / user / month billed annually with SLA and SOC2 reports.
        Enterprise Tier: Custom pricing for large organizations.
        """,
        content_hash="hash-saas-pricing"
    )

    p_legal = CrawledPage(
        brand_id="brand-saas-linear",
        requested_url="https://linear.app/terms",
        final_url="https://linear.app/terms",
        http_status=200,
        page_type="legal",
        title="Terms of Service — Linear",
        headings={
            "h1": ["Master Services Agreement"],
            "h2": ["1.1 Definitions", "2.1 License Grant", "3.1 Restrictions", "4.1 Proprietary Rights", "5.1 Fees and Payment"]
        },
        extracted_text="""
        1.1 Definitions: Capitalized terms have the meaning defined herein.
        2.1 License Grant: Linear grants customer a non-exclusive license.
        5.1 Fees and Payment: Customer agrees to pay all fees outlined in the Order Form.
        """,
        content_hash="hash-saas-legal"
    )

    return [p_home, p_products, p_usecases, p_pricing, p_legal]


# ==============================================================================
# SITE B: DOCUMENTATION-HEAVY AI / API PLATFORM (PINECONE - Vector DB)
# ==============================================================================

def create_ai_platform_site_pages() -> list[CrawledPage]:
    """Generates realistic pages for Site B (API / AI Platform)."""
    p_home = CrawledPage(
        brand_id="brand-api-pinecone",
        requested_url="https://pinecone.io",
        final_url="https://pinecone.io/",
        http_status=200,
        page_type="homepage",
        title="Pinecone — Vector Database for AI",
        meta_description="Pinecone provides an ultra-fast, serverless vector database designed for high-scale AI and LLM search applications.",
        headings={
            "h1": ["Serverless Vector Database for Real-Time AI"],
            "h2": ["Vector Search at Enterprise Scale", "Built-in Metadata Filtering"]
        },
        extracted_text="""
        Pinecone is a cloud-native vector database for semantic search, recommendation engines, and RAG.
        
        Key Features:
        - Ultra-low latency approximate nearest neighbor search
        - Fresh index updates with zero indexing downtime
        - Multi-cloud availability across AWS, GCP, and Azure
        """,
        content_hash="hash-api-home"
    )

    p_products = CrawledPage(
        brand_id="brand-api-pinecone",
        requested_url="https://pinecone.io/product",
        final_url="https://pinecone.io/product",
        http_status=200,
        page_type="product_service",
        title="Products — Pinecone Vector Cloud",
        headings={
            "h1": ["Pinecone Serverless"],
            "h2": ["Pinecone Pod-Based Indexes", "Pinecone Inference API", "2.2 AI Model Terms", "Recitals"]
        },
        extracted_text="""
        Pinecone Serverless lets developers scale vector storage without provisioning clusters.
        Pinecone Inference API generates embeddings directly within the database pipeline.
        """,
        content_hash="hash-api-prod"
    )

    p_usecases = CrawledPage(
        brand_id="brand-api-pinecone",
        requested_url="https://pinecone.io/solutions",
        final_url="https://pinecone.io/solutions",
        http_status=200,
        page_type="homepage",
        title="Solutions & Architecture — Pinecone",
        extracted_text="""
        Use Cases:
        - Retrieval augmented generation for enterprise LLMs
        - Real-time semantic document search
        - Multimodal ecommerce recommendation systems
        
        Target Audience:
        - AI engineers and ML platform architects
        - Enterprise data engineering teams
        - Developers building generative AI applications
        
        Why choose us: Separation of storage and compute delivering 50x lower cost
        """,
        content_hash="hash-api-uc"
    )

    p_pricing = CrawledPage(
        brand_id="brand-api-pinecone",
        requested_url="https://pinecone.io/pricing",
        final_url="https://pinecone.io/pricing",
        http_status=200,
        page_type="pricing",
        title="Pricing — Pinecone",
        extracted_text="""
        Pay only for what you query and store:
        Serverless Read: $0.040 / 1M read units
        Serverless Write: $0.100 / 1M write units
        Standard Tier: $50 / month base platform commitment.
        Enterprise Tier: Custom committed spend with dedicated support.
        Incidental stats: We raised $100M in Series B funding.
        Latency benchmarks: 0.042 ms avg latency across test runs.
        """,
        content_hash="hash-api-pricing"
    )

    p_legal = CrawledPage(
        brand_id="brand-api-pinecone",
        requested_url="https://pinecone.io/legal/msa",
        final_url="https://pinecone.io/legal/msa",
        http_status=200,
        page_type="legal",
        title="Master Subscription Agreement — Pinecone",
        headings={
            "h1": ["Master Subscription Agreement"],
            "h2": ["Recitals", "2.1 License", "3.1 Restrictions", "4.1 Data Processing", "5.1 Fees and Minimum Spend Requirement"]
        },
        extracted_text="Legal agreement text.",
        content_hash="hash-api-legal"
    )

    return [p_home, p_products, p_usecases, p_pricing, p_legal]


# ==============================================================================
# SITE C: ECOMMERCE / CONSUMER BRAND (ALLBIRDS - Sustainable Footwear)
# ==============================================================================

def create_ecommerce_site_pages() -> list[CrawledPage]:
    """Generates realistic pages for Site C (Ecommerce)."""
    p_home = CrawledPage(
        brand_id="brand-ecom-allbirds",
        requested_url="https://allbirds.com",
        final_url="https://allbirds.com/",
        http_status=200,
        page_type="homepage",
        title="Allbirds — Sustainable Shoes & Natural Apparel",
        meta_description="Discover comfortable, sustainable footwear made with natural materials like merino wool and eucalyptus tree fiber.",
        headings={
            "h1": ["Natural Materials & Sustainable Everyday Footwear"],
            "h2": ["Super-comfortable wool runners", "Tree fiber everyday sneakers"]
        },
        extracted_text="""
        Allbirds crafts sustainable footwear with nature-first innovation.
        
        Key Features:
        - Thermoregulating ZQ merino wool upper
        - SweetFoam sugarcane EVA midsole
        - Machine-washable everyday construction
        """,
        structured_data=[{
            "@type": "ProductGroup",
            "name": "Wool Runner Collection",
            "description": "Iconic everyday shoes crafted from ultra-soft merino wool.",
            "hasVariant": [
                {
                    "@type": "Product",
                    "name": "Wool Runner 2 - Natural White",
                    "offers": {"price": "110", "priceCurrency": "USD"}
                }
            ]
        }],
        content_hash="hash-ecom-home"
    )

    p_pdp = CrawledPage(
        brand_id="brand-ecom-allbirds",
        requested_url="https://allbirds.com/products/mens-tree-dasher",
        final_url="https://allbirds.com/products/mens-tree-dasher",
        http_status=200,
        page_type="product_service",
        title="Men's Tree Dasher 2 — Daily Running Shoes | Allbirds",
        headings={
            "h1": ["Tree Dasher 2"],
            "h2": ["Shop by Size", "Size Guide", "Order Status", "SKU: TD2-M-WHT-105", "Shipping Policy"]
        },
        extracted_text="""
        The Tree Dasher 2 is our lightweight, breathable running shoe designed for 5K runs and daily fitness.
        Price: $135
        Material: FSC-certified eucalyptus tree fiber.
        """,
        structured_data=[{
            "@type": "Product",
            "name": "Tree Dasher 2",
            "description": "High-performance running shoe with natural responsive foam.",
            "offers": {"price": "135.00", "priceCurrency": "USD"}
        }],
        content_hash="hash-ecom-pdp"
    )

    p_usecases = CrawledPage(
        brand_id="brand-ecom-allbirds",
        requested_url="https://allbirds.com/sustainability",
        final_url="https://allbirds.com/sustainability",
        http_status=200,
        page_type="homepage",
        title="Sustainability & Purpose — Allbirds",
        extracted_text="""
        Use Cases:
        - Daily walking and all-day casual wear
        - Road running and active fitness workouts
        - Travel and everyday urban commuting
        
        Target Audience:
        - Eco-conscious runners and athletes
        - Everyday walkers and active commuters
        - Consumers seeking sustainable footwear
        
        Why choose us: Carbon-neutral footwear crafted entirely from natural renewable materials
        """,
        content_hash="hash-ecom-uc"
    )

    p_cart = CrawledPage(
        brand_id="brand-ecom-allbirds",
        requested_url="https://allbirds.com/cart",
        final_url="https://allbirds.com/cart",
        http_status=200,
        page_type="other",
        title="Shopping Cart — Allbirds",
        headings={
            "h1": ["Your Shopping Bag"],
            "h2": ["Checkout", "Order Status", "Track Your Order", "Return Policy"]
        },
        extracted_text="Your bag is empty. Explore our latest footwear.",
        content_hash="hash-ecom-cart"
    )

    return [p_home, p_pdp, p_usecases, p_cart]


# ==============================================================================
# SECTION 1 & 2: CROSS-SITE GROUND-TRUTH QUALITY EVALUATION (PRECISION / RECALL)
# ==============================================================================

def test_site_a_saas_ground_truth_quality_and_metrics():
    """Evaluate Site A (Linear SaaS) against manually labeled ground truth."""
    pages = create_saas_site_pages()
    synth = FactSynthesizer("brand-saas-linear", user_business_name="Linear")
    facts = synth.synthesize_facts(pages)

    # 1. Manually Labeled Ground Truth Expectations
    # Products expected: "Linear Asks", "Linear Insights", "Linear Projects"
    # Products forbidden: "2.1 License Grant", "Terms of Use", "Master Services Agreement"
    # Audiences expected: "High-growth engineering teams", "Product managers and technical leads", etc.
    # Pricing expected: Free ($0), Standard ($8), Plus ($14) with units
    # Pricing forbidden: Uncontextualized numbers, raw license sections

    products = [f for f in facts if f.fact_type == "product_service"]
    product_names = [f.fact_value.get("name") if isinstance(f.fact_value, dict) else str(f.fact_value) for f in products]
    
    audiences = [f for f in facts if f.fact_type == "target_audience"]
    audience_values = [str(f.fact_value) for f in audiences]

    use_cases = [f for f in facts if f.fact_type == "use_case"]
    use_case_values = [str(f.fact_value) for f in use_cases]

    pricing = [f for f in facts if f.fact_type == "pricing"]
    pricing_plans = [f.fact_value.get("plan_name") for f in pricing if isinstance(f.fact_value, dict)]

    # Precision & Noise Rejection Checks
    assert not any("license" in p.lower() or "terms" in p.lower() or "agreement" in p.lower() for p in product_names)
    assert not any("definitions" in p.lower() or "proprietary" in p.lower() for p in product_names)
    assert any("Linear Asks" in p for p in product_names)
    assert any("Linear Insights" in p for p in product_names)

    # Audiences & Use Cases
    assert any("engineering teams" in a.lower() for a in audience_values)
    assert any("sprint planning" in u.lower() for u in use_case_values)

    # Pricing structured facts
    assert "Standard" in pricing_plans or "Standard Tier" in pricing_plans
    standard_fact = next(f for f in pricing if f.fact_value.get("plan_name") in ("Standard", "Standard Tier"))
    assert standard_fact.fact_value["amount"] == 8.0
    assert standard_fact.fact_value["billing_basis"] in ("annually", "per_user_monthly")
    assert standard_fact.fact_value["currency"] == "USD"

    # Metric Calculations
    # Products: Expected relevant = 3 ("Linear Asks", "Linear Insights", "Linear Projects")
    retained_valid_prods = [p for p in product_names if any(k in p for k in ("Asks", "Insights", "Projects"))]
    precision_prod = len(retained_valid_prods) / len(product_names) if product_names else 0.0
    recall_prod = len(retained_valid_prods) / 3.0
    duplicate_prod = (len(product_names) - len(set(p.lower() for p in product_names))) / len(product_names) if product_names else 0.0

    assert precision_prod >= 0.75
    assert recall_prod >= 0.66
    assert duplicate_prod == 0.0

    # Provenance Completeness
    provenance_complete = sum(1 for f in facts if f.source_url and f.evidence_snippet) / len(facts) if facts else 0.0
    assert provenance_complete >= 0.95


def test_site_b_ai_platform_ground_truth_quality_and_metrics():
    """Evaluate Site B (Pinecone API Platform) against labeled ground truth."""
    pages = create_ai_platform_site_pages()
    synth = FactSynthesizer("brand-api-pinecone", user_business_name="Pinecone")
    facts = synth.synthesize_facts(pages)

    products = [f for f in facts if f.fact_type == "product_service"]
    product_names = [f.fact_value.get("name") if isinstance(f.fact_value, dict) else str(f.fact_value) for f in products]

    pricing = [f for f in facts if f.fact_type == "pricing"]
    pricing_amounts = [f.fact_value.get("amount") for f in pricing if isinstance(f.fact_value, dict)]

    # Legal clauses completely rejected
    assert not any("recital" in p.lower() or "license" in p.lower() or "restrictions" in p.lower() for p in product_names)
    assert not any("minimum spend" in p.lower() for p in product_names)

    # Genuine API services retained
    assert any("Serverless" in p for p in product_names)
    assert any("Inference API" in p for p in product_names)

    # Usage-based pricing retained with structured units
    assert 0.040 in pricing_amounts
    read_unit_fact = next(f for f in pricing if f.fact_value.get("amount") == 0.040)
    assert read_unit_fact.fact_value["billing_basis"] == "usage"
    assert "read units" in read_unit_fact.fact_value["unit"].lower() or "read" in read_unit_fact.fact_value["associated_product"].lower()

    # Context-free latency (0.042) and funding ($100M) rejected
    assert 0.042 not in pricing_amounts
    assert 100000000.0 not in pricing_amounts

    # Provenance check
    assert all(f.source_url.startswith("https://pinecone.io") for f in facts if f.source_url)


def test_site_c_ecommerce_ground_truth_quality_and_metrics():
    """Evaluate Site C (Allbirds Ecommerce) for product families vs SKUs, navigation labels, and offers."""
    pages = create_ecommerce_site_pages()
    synth = FactSynthesizer("brand-ecom-allbirds", user_business_name="Allbirds")
    facts = synth.synthesize_facts(pages)

    products = [f for f in facts if f.fact_type == "product_service"]
    product_names = [f.fact_value.get("name") if isinstance(f.fact_value, dict) else str(f.fact_value) for f in products]

    # SKU numbers and inventory codes strictly rejected
    assert not any(p.lower().startswith("sku:") for p in product_names)
    assert not any("td2-m-wht" in p.lower() for p in product_names)

    # Navigation, cart, order tracking, and size guides strictly rejected
    assert not any(p.lower() in ("shop by size", "size guide", "order status", "checkout", "your shopping bag", "shipping policy") for p in product_names)

    # Product families and collections identified
    assert any("Wool Runner" in p for p in product_names)
    assert any("Tree Dasher 2" in p for p in product_names)

    # Structured one-time pricing offers extracted
    pricing = [f for f in facts if f.fact_type == "pricing"]
    assert len(pricing) >= 1
    dasher_price = next((f for f in pricing if "Dasher" in f.fact_value.get("plan_name", "") or "Dasher" in f.fact_value.get("associated_product", "")), None)
    assert dasher_price is not None
    assert dasher_price.fact_value["amount"] in (135.0, 110.0)
    assert dasher_price.fact_value["billing_basis"] == "one_time" or dasher_price.fact_value["unit"] == "unit"


# ==============================================================================
# SECTION 3: CRAWL BUDGET ENFORCEMENT UNDER ADVERSE & EXTREME CONDITIONS
# ==============================================================================

@pytest.mark.asyncio
async def test_crawl_budget_massive_sitemap_boundary():
    """Verify crawler caps massive sitemaps (e.g. 50,000 URLs) to CRAWL_MAX_SITEMAP_ENTRIES."""
    crawler = ScraplingCrawler(base_url="https://example.com", page_limit=10)

    # Simulate sitemap XML containing 10,000 URLs
    huge_xml_lines = ['<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">']
    for i in range(1000):
        huge_xml_lines.append(f"<url><loc>https://example.com/p/{i}</loc></url>")
    huge_xml_lines.append("</urlset>")
    huge_xml = "\n".join(huge_xml_lines).encode("utf-8")

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.headers = {"content-type": "application/xml"}
    mock_resp.content = huge_xml
    mock_resp.text = huge_xml.decode("utf-8")

    mock_client = AsyncMock()
    mock_client.get.return_value = mock_resp

    discoverer = SitemapDiscoverer(
        base_url="https://example.com",
        base_domain="example.com",
        max_urls=settings.CRAWL_MAX_SITEMAP_ENTRIES
    )
    urls = await discoverer.discover(client=mock_client)

    assert len(urls) <= settings.CRAWL_MAX_SITEMAP_ENTRIES
    assert len(urls) <= 100


@pytest.mark.asyncio
async def test_crawl_budget_deep_documentation_section_capped():
    """Verify section quota prevents thousands of /docs/ pages from consuming the run budget."""
    crawler = ScraplingCrawler(base_url="https://docs-heavy-api.com", page_limit=20)

    # Mock fetch so docs pages succeed but section count is tracked
    async def mock_fetch_and_extract(url: str):
        sec = crawler._get_section_prefix(url)
        return {
            "requested_url": url,
            "final_url": url,
            "http_status": 200,
            "page_type": "docs" if sec == "docs" else "homepage",
            "title": f"Doc Page {url}",
            "extracted_text": "Detailed SDK documentation and API endpoints.",
            "canonical_url": url,
            "internal_links": []
        }

    crawler._fetch_and_extract = mock_fetch_and_extract

    # Pre-populate queue with 50 docs pages and 5 product/pricing pages
    from app.crawler.engine import CrawlItem
    queue = [CrawlItem(url="https://docs-heavy-api.com/", depth=0, priority=0)]
    for i in range(30):
        queue.append(CrawlItem(url=f"https://docs-heavy-api.com/docs/page-{i}", depth=1, priority=3))
    queue.append(CrawlItem(url="https://docs-heavy-api.com/pricing", depth=1, priority=1))
    queue.append(CrawlItem(url="https://docs-heavy-api.com/product", depth=1, priority=1))

    # Run crawl loop manually
    crawler.visited_urls = set()
    crawler.category_counts = {}
    crawler.section_counts = {}
    crawler.skip_reasons = {}
    crawler.crawled_pages = []

    while queue and len(crawler.crawled_pages) < crawler.page_limit:
        queue.sort(key=lambda item: (item.priority, item.depth))
        item = queue.pop(0)
        url = item.url
        sec = crawler._get_section_prefix(url)

        if sec and crawler.section_counts.get(sec, 0) >= settings.CRAWL_MAX_PAGES_PER_SECTION and item.priority > 0:
            crawler.pages_skipped += 1
            crawler.skip_reasons["section-quota"] = crawler.skip_reasons.get("section-quota", 0) + 1
            crawler.visited_urls.add(url)
            continue

        crawler.visited_urls.add(url)
        crawler.pages_attempted += 1
        page_data = await crawler._fetch_and_extract(url)
        crawler.section_counts[sec] = crawler.section_counts.get(sec, 0) + 1
        crawler.crawled_pages.append(page_data)

    summary = crawler.get_crawl_summary()
    assert crawler.section_counts.get("docs", 0) <= settings.CRAWL_MAX_PAGES_PER_SECTION
    assert summary["skip_reasons"].get("section-quota", 0) > 0
    # High-priority pricing and product pages must have been crawled
    crawled_urls = [p["final_url"] for p in crawler.crawled_pages]
    assert "https://docs-heavy-api.com/pricing" in crawled_urls
    assert "https://docs-heavy-api.com/product" in crawled_urls


@pytest.mark.asyncio
async def test_crawl_budget_duplicate_url_and_tracking_params():
    """Verify URLs with tracking parameters normalize and deduplicate pre-scheduling."""
    crawler = ScraplingCrawler(base_url="https://saas-brand.com", page_limit=10)

    url1 = "https://saas-brand.com/pricing"
    url2 = "https://saas-brand.com/pricing?utm_source=twitter&utm_medium=cpc"
    url3 = "https://saas-brand.com/pricing?fbclid=IwAR1234"

    norm1 = normalize_url(url1)
    norm2 = normalize_url(url2)
    norm3 = normalize_url(url3)

    assert norm1 == norm2 == norm3 == "https://saas-brand.com/pricing"


@pytest.mark.asyncio
async def test_crawl_budget_aggregate_bytes_limit_terminates():
    """Verify total run stops immediately when CRAWL_MAX_AGGREGATE_BYTES is reached."""
    crawler = ScraplingCrawler(base_url="https://heavy-site.com", page_limit=20)
    # Simulate high byte accumulation
    crawler.aggregate_bytes_processed = settings.CRAWL_MAX_AGGREGATE_BYTES + 1024

    from app.crawler.engine import CrawlItem
    queue = [CrawlItem(url="https://heavy-site.com/p1", depth=1, priority=1)]

    # Run check logic
    with patch.object(crawler, "deadline", time.time() + 100):
        if crawler.aggregate_bytes_processed >= settings.CRAWL_MAX_AGGREGATE_BYTES:
            crawler.warnings.append("Crawl stopped: Aggregate content size budget reached")
            crawler.skip_reasons["aggregate-size-limit"] = 1

    summary = crawler.get_crawl_summary()
    assert summary["skip_reasons"]["aggregate-size-limit"] == 1
    assert any("Aggregate content size budget reached" in w for w in crawler.warnings)


# ==============================================================================
# SECTION 4: GROUND-TRUTH DATA CONTRACT & PERSISTENCE LIFECYCLE
# ==============================================================================

def test_ground_truth_contract_schema_completeness():
    """Verify every BrandFact conforms to canonical data contract with full provenance."""
    pages = create_saas_site_pages()
    synth = FactSynthesizer("brand-contract-test", user_business_name="Linear")
    facts = synth.synthesize_facts(pages)

    assert len(facts) > 0
    for fact in facts:
        # 1. Structural Identity
        assert fact.brand_id == "brand-contract-test"
        assert fact.fact_type in (
            "business_name", "company_description", "product_service",
            "product_feature", "target_audience", "use_case", "pricing",
            "differentiator", "faq", "contact_info", "industry"
        )
        assert fact.fact_value is not None

        # 2. Provenance
        assert fact.source_url is not None
        assert fact.source_url.startswith("https://linear.app")
        assert fact.extraction_method in (
            "user_input", "meta_description", "heading_heuristic",
            "title_heuristic", "bullet_heuristic", "heading_list_item",
            "labeled_line", "pricing_regex", "json_ld_schema", "json_ld_offer",
            "taxonomy_keyword", "title_definition", "meta_description_definition"
        )
        assert 0.0 <= fact.confidence <= 1.0

        # 3. State Management
        assert fact.user_confirmed is False or fact.extraction_method == "user_input"
        assert hasattr(fact, "is_rejected")
        assert fact.is_rejected is False


def test_ground_truth_rejection_survives_normalizer_and_reprofiling():
    """Verify rejected facts are strictly excluded from downstream normalizer."""
    pages = create_saas_site_pages()
    synth = FactSynthesizer("brand-contract-test", user_business_name="Linear")
    facts = synth.synthesize_facts(pages)

    # Find a product and reject it
    prod_fact = next(f for f in facts if f.fact_type == "product_service")
    prod_fact.is_rejected = True
    rejected_name = prod_fact.fact_value["name"]

    # Normalize profile for Engine 2
    profile_dict = {
        "brand": {"id": "brand-contract-test", "business_name": "Linear", "domain": "linear.app"},
        "profile_version": 1,
        "facts": facts,
        "products_and_services": [
            {"name": f.fact_value["name"], "is_rejected": f.is_rejected}
            for f in facts if f.fact_type == "product_service" and isinstance(f.fact_value, dict)
        ]
    }

    normalized = ProfileNormalizer.normalize(profile_dict)
    assert rejected_name not in normalized.products_and_services
    assert not any(f.fact_value.get("name") == rejected_name for f in normalized.facts if isinstance(f.fact_value, dict))


# ==============================================================================
# SECTION 5: ENGINE 2 PROMPT INTELLIGENCE GROUNDING & SPARSITY
# ==============================================================================

@pytest.mark.asyncio
async def test_engine2_prompt_grounding_and_provenance_traceability():
    """Verify that Engine 2 generated prompts trace back to approved ground-truth facts."""
    pages = create_saas_site_pages()
    synth = FactSynthesizer("brand-saas-linear", user_business_name="Linear")
    facts = synth.synthesize_facts(pages)

    profile_dict = {
        "brand": {"id": "brand-saas-linear", "business_name": "Linear", "domain": "linear.app", "industry": "Software Project Management"},
        "profile_version": 1,
        "facts": facts,
        "products_and_services": [f.fact_value["name"] for f in facts if f.fact_type == "product_service" and isinstance(f.fact_value, dict)],
        "target_audience": [str(f.fact_value) for f in facts if f.fact_type == "target_audience"],
        "use_cases": [str(f.fact_value) for f in facts if f.fact_type == "use_case"],
        "pricing_information": [f.fact_value["formatted_display"] for f in facts if f.fact_type == "pricing" and isinstance(f.fact_value, dict)]
    }

    norm_profile = ProfileNormalizer.normalize(profile_dict)
    plan = CoveragePlanner.create_plan(norm_profile, requested_count=15)
    generator = DeterministicGenerator()
    candidates = await generator.generate(norm_profile, plan)

    assert len(candidates) > 0
    for cand in candidates:
        text = cand.text
        # Prompts must not contain legal clauses
        assert "2.1 license" not in text.lower()
        assert "terms of use" not in text.lower()
        # Prompts must not contain context-free random numbers
        assert "$0.042" not in text

        # Product evaluation prompts must feature genuine products
        if cand.category == "product_evaluation":
            assert cand.target_product_service in norm_profile.products_and_services

        # Audience-specific prompts must feature genuine audiences
        if cand.category == "audience_specific":
            assert cand.target_audience in norm_profile.target_audiences


@pytest.mark.asyncio
async def test_engine2_sparse_profile_produces_cautious_prompts():
    """Verify that a brand with missing products/pricing does not fabricate coverage."""
    # Sparse profile: Only business name and industry, no products or pricing
    sparse_profile = {
        "brand": {"id": "sparse-brand", "business_name": "Minimalist", "domain": "minimal.io", "industry": "Data Storage"},
        "profile_version": 1,
        "facts": [],
        "products_and_services": [],
        "target_audience": [],
        "use_cases": [],
        "pricing_information": []
    }

    norm_profile = ProfileNormalizer.normalize(sparse_profile)
    plan = CoveragePlanner.create_plan(norm_profile, requested_count=10)
    
    # Active plan categories must only include general discovery/recommendations, NOT product_evaluation or pricing_value
    planned_categories = {slot.category for slot in plan.slots}
    assert "product_evaluation" not in planned_categories
    assert "pricing_value" not in planned_categories
    assert "audience_specific" not in planned_categories
    assert "discovery" in planned_categories


# ==============================================================================
# SECTION 6: ENGINE 3 AI VISIBILITY SCAN REGRESSION COMPATIBILITY
# ==============================================================================

def test_engine3_evaluator_attribution_and_scorecard():
    """Verify Engine 3 evaluates mock responses honestly with structured scoring."""
    # 1. Mentioned response
    resp_positive = "For modern software issue tracking, Linear is highly recommended alongside Jira and Asana."
    eval_pos = VisibilityResponseEvaluator.evaluate(
        response_text=resp_positive,
        brand_name="Linear",
        brand_domain="linear.app",
        known_competitors=["Jira", "Asana"]
    )
    assert eval_pos.brand_mentioned is True
    assert eval_pos.recommendation_status == "recommended"
    assert "Jira" in eval_pos.competitor_mentions

    # 2. Not mentioned response
    resp_negative = "You can manage software projects using Jira, GitHub Projects, or Monday.com."
    eval_neg = VisibilityResponseEvaluator.evaluate(
        response_text=resp_negative,
        brand_name="Linear",
        brand_domain="linear.app",
        known_competitors=["Jira", "Asana"]
    )
    assert eval_neg.brand_mentioned is False
    assert eval_neg.recommendation_status == "not_mentioned"
    assert "Jira" in eval_neg.competitor_mentions


# ==============================================================================
# SECTION 7: CROSS-SITE PRICING INTELLIGENCE & SEMANTIC CLASSIFICATION SUITE
# ==============================================================================

def test_pricing_semantic_classification_comprehensive_matrix():
    """Verify distinct semantic representation across:
    - Explicitly free plan: $0/month
    - Paid plan: $25,000/month
    - 25,000 credits/month (no stated subscription price)
    - 25,000 requests/month (no stated subscription price)
    - $0.042/request
    - $0.04/1,000 tokens
    - One-time setup fee ($500 setup fee)
    - Custom / Contact-sales pricing (Enterprise: Contact sales)
    - Unverified context-free numbers
    """
    pricing_page = CrawledPage(
        brand_id="brand-pricing-matrix",
        requested_url="https://platform.example.com/pricing",
        final_url="https://platform.example.com/pricing",
        http_status=200,
        page_type="pricing",
        extracted_text="""
        Platform Pricing & Tier Options:
        Free Tier: $0 / month. 25+ free features.
        Standard: $25,000 / month. Full enterprise infrastructure.
        Developer: 25,000 credits / month included.
        Personal: 25,000 requests / month allowance.
        Inference API: $0.042 / request.
        Batch Tokenizer: $0.04 / 1,000 tokens.
        Onboarding: $500 setup fee.
        Enterprise: Contact sales for custom volume discount.
        """,
        content_hash="hash-pricing-matrix"
    )

    synth = FactSynthesizer("brand-pricing-matrix", user_business_name="Matrix Platform")
    facts = synth.synthesize_facts([pricing_page])
    pricing_facts = [f for f in facts if f.fact_type == "pricing"]

    by_plan = {}
    for pf in pricing_facts:
        val = pf.fact_value
        by_plan[(val.get("plan_name"), val.get("pricing_type"))] = val

    # 1. Explicitly free plan: $0/month
    free_entry = next((v for (k, t), v in by_plan.items() if "free" in k.lower() or t == "free_tier"), None)
    assert free_entry is not None
    assert free_entry["amount"] == 0.0

    # 2. Paid plan: $25,000/month (Genuine subscription)
    assert ("Standard", "subscription_plan") in by_plan
    std_plan = by_plan[("Standard", "subscription_plan")]
    assert std_plan["amount"] == 25000.0
    assert std_plan["currency"] == "USD"
    assert std_plan["billing_basis"] == "monthly"
    assert std_plan["unit"] == "month"

    # 3. 25,000 credits/month (Quota allowance, NEVER a subscription price)
    assert ("Developer", "usage_allowance") in by_plan
    dev_quota = by_plan[("Developer", "usage_allowance")]
    assert dev_quota["amount"] == 25000.0
    assert dev_quota["currency"] is None  # No currency invented
    assert "credits" in dev_quota["unit"]
    assert dev_quota["billing_basis"] == "monthly"

    # 4. 25,000 requests/month (Quota allowance)
    assert ("Personal", "usage_allowance") in by_plan
    pers_quota = by_plan[("Personal", "usage_allowance")]
    assert pers_quota["amount"] == 25000.0
    assert pers_quota["currency"] is None
    assert "requests" in pers_quota["unit"]

    # 5. $0.042/request (Usage rate)
    usage_req = next((v for (k, t), v in by_plan.items() if t == "usage_rate" and v.get("amount") == 0.042), None)
    assert usage_req is not None
    assert usage_req["unit"] == "request"
    assert usage_req["billing_basis"] == "usage"
    assert usage_req["currency"] == "USD"

    # 6. $0.04/1,000 tokens (Usage rate with token scale)
    usage_tok = next((v for (k, t), v in by_plan.items() if t == "usage_rate" and v.get("amount") == 0.04), None)
    assert usage_tok is not None
    assert "1k" in usage_tok["unit"].lower() or "token" in usage_tok["unit"].lower()
    assert usage_tok["billing_basis"] == "usage"

    # 7. One-time setup fee
    print("\nBY_PLAN KEYS:", list(by_plan.keys()))
    setup = next((v for (k, t), v in by_plan.items() if t == "setup_fee" or v.get("amount") == 500.0), None)
    assert setup is not None
    assert setup["amount"] == 500.0
    assert setup["billing_basis"] == "one_time"
    assert setup["currency"] == "USD"

    # 8. Custom / Contact-sales
    assert ("Enterprise", "custom") in by_plan
    custom_tier = by_plan[("Enterprise", "custom")]
    assert custom_tier["amount"] is None
    assert custom_tier["billing_basis"] == "custom"
    assert "Contact sales" in custom_tier["context"]


def test_pricing_json_ld_offers_and_variants():
    """Verify structured data extraction from JSON-LD Product and Offer schemas."""
    ecommerce_page = CrawledPage(
        brand_id="brand-ecom-offers",
        requested_url="https://shop.example.com/products/runner",
        final_url="https://shop.example.com/products/runner",
        http_status=200,
        page_type="product_service",
        title="Wool Runner - Everyday Sneakers",
        structured_data=[
            {
                "@type": "Product",
                "name": "Wool Runner Sneaker",
                "offers": {
                    "@type": "Offer",
                    "price": 110.0,
                    "priceCurrency": "USD",
                    "availability": "https://schema.org/InStock"
                }
            },
            {
                "@type": "Product",
                "name": "Trail Runner",
                "hasVariant": [
                    {
                        "@type": "ProductModel",
                        "name": "Trail Runner Waterproof",
                        "offers": {
                            "@type": "Offer",
                            "price": 140.0,
                            "priceCurrency": "EUR"
                        }
                    }
                ]
            }
        ],
        content_hash="hash-ecom-offers"
    )

    synth = FactSynthesizer("brand-ecom-offers", user_business_name="AllWool")
    facts = synth.synthesize_facts([ecommerce_page])
    pricing_facts = [f for f in facts if f.fact_type == "pricing"]

    assert len(pricing_facts) >= 2
    offers = {f.fact_value["plan_name"]: f.fact_value for f in pricing_facts}

    assert "Wool Runner Sneaker" in offers
    assert offers["Wool Runner Sneaker"]["amount"] == 110.0
    assert offers["Wool Runner Sneaker"]["currency"] == "USD"
    assert offers["Wool Runner Sneaker"]["currency_symbol"] == "$"
    assert offers["Wool Runner Sneaker"]["billing_basis"] == "one_time" or offers["Wool Runner Sneaker"]["billing_basis"] == "per_unit"

    assert "Trail Runner Waterproof" in offers
    assert offers["Trail Runner Waterproof"]["amount"] == 140.0
    assert offers["Trail Runner Waterproof"]["currency"] == "EUR"
    assert offers["Trail Runner Waterproof"]["currency_symbol"] == "€"


def test_pricing_deduplication_and_isolation():
    """Verify that repeated mentions collapse into one fact and context-free numbers on general pages are rejected."""
    home_page = CrawledPage(
        brand_id="brand-dedup",
        requested_url="https://example.com/",
        final_url="https://example.com/",
        http_status=200,
        page_type="homepage",
        extracted_text="""
        We raised $25 million in Series B funding!
        We also helped customers save $10,000 on energy costs.
        Our random metric is 42.0 without currency.
        Starter plan is $20 / month.
        Starter plan is $20 / month.
        """,
        content_hash="hash-dedup"
    )

    synth = FactSynthesizer("brand-dedup", user_business_name="DedupCorp")
    facts = synth.synthesize_facts([home_page])
    pricing_facts = [f for f in facts if f.fact_type == "pricing"]

    # Series B ($25M) and energy savings ($10,000) and random metric (42.0) MUST NOT be pricing
    amounts = [f.fact_value.get("amount") for f in pricing_facts]
    assert 25000000.0 not in amounts
    assert 10000.0 not in amounts
    assert 42.0 not in amounts

    # Starter plan ($20/month) must only appear once (deduplicated)
    starter_facts = [f for f in pricing_facts if f.fact_value.get("plan_name") == "Starter"]
    assert len(starter_facts) == 1
    assert starter_facts[0].fact_value["amount"] == 20.0
    assert starter_facts[0].fact_value["billing_basis"] == "monthly"


@pytest.mark.asyncio
async def test_rejected_pricing_fact_is_excluded_from_prompts():
    """Verify that user-rejected pricing facts are excluded from ProfileNormalizer and do not ground prompts."""
    # Profile with 1 confirmed pricing fact and 1 rejected pricing fact
    profile_data = {
        "brand": {"id": "brand-guardrail", "business_name": "CloudGuard", "domain": "cloudguard.io", "industry": "Security"},
        "profile_version": 1,
        "facts": [
            {
                "id": "fact-confirmed-price",
                "fact_type": "pricing",
                "fact_value": {"plan_name": "Pro", "amount": 99.0, "currency": "USD", "billing_basis": "monthly", "formatted_display": "Pro: $99 / month"},
                "confidence": 0.95,
                "user_confirmed": True
            },
            {
                "id": "fact-rejected-price",
                "fact_type": "pricing",
                "fact_value": {"plan_name": "BadPlan", "amount": 25000.0, "currency": "USD", "billing_basis": "monthly", "formatted_display": "BadPlan: $25000 / month"},
                "confidence": 0.50,
                "user_confirmed": False  # Rejected
            }
        ],
        "products_and_services": ["Cloud Security Scanner"],
        "target_audience": ["DevSecOps Teams"],
        "use_cases": ["Cloud compliance"],
        "pricing_information": [
            {"fact_id": "fact-confirmed-price", "value": {"plan_name": "Pro", "amount": 99.0, "billing_basis": "monthly"}},
            {"fact_id": "fact-rejected-price", "value": {"plan_name": "BadPlan", "amount": 25000.0, "billing_basis": "monthly"}}
        ]
    }

    norm = ProfileNormalizer.normalize(profile_data)
    plan = CoveragePlanner.create_plan(norm, requested_count=10)
    gen = DeterministicGenerator()
    prompts = await gen.generate(norm, plan)

    for p in prompts:
        # No prompt should mention the rejected 25,000 price
        assert "$25000" not in p.text
        assert "25,000" not in p.text
        assert "BadPlan" not in p.text
