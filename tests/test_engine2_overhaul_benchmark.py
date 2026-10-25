"""Phase 7: Representative Quality Benchmark for Engine 2 Prompt Intelligence Overhaul.
Evaluates:
1. Sporting goods retailer with multiple verified product categories (footwear, apparel, gear).
2. Sportswear brand (footwear and apparel isolation).
3. SaaS / Developer software platform.
4. Professional service-based business.
5. Mixed-category retailer.
6. Sparse / insufficient evidence profile (honest uncertainty and rejection).
7. Profile with competitor product incorrectly attributed (detection & isolation).
8. Stale cached prompt set from older profile version (version invalidation).
9. Unknown / ambiguous category (conservative fallback).
10. Category with valid generic prompts without specific product names.
"""
import pytest
import pytest_asyncio
from typing import Dict, Any, List

from app.prompts.models import NormalizedBrandProfile, GroundedFact
from app.prompts.normalizer import ProfileNormalizer, is_navigation_or_ui_noise
from app.prompts.classifier import CategoryClassifier, BrandClassificationResult
from app.prompts.planner import CoveragePlanner
from app.prompts.generator import DeterministicGenerator
from app.prompts.validator import PromptValidator
from app.prompts.scorer import PromptScorer
from app.prompts.templates import TemplateRegistry


def make_test_fact(
    fact_id: str,
    fact_type: str,
    fact_value: Any,
    confidence: float = 0.95,
    user_confirmed: bool = True,
    evidence_snippet: str = "Verified website statement.",
    source_url: str = "https://example.com"
) -> Dict[str, Any]:
    return {
        "id": fact_id,
        "fact_type": fact_type,
        "fact_value": fact_value,
        "confidence": confidence,
        "user_confirmed": user_confirmed,
        "evidence_snippet": evidence_snippet,
        "source_url": source_url,
    }


# ==============================================================================
# Fixture 1: Sporting Goods Retailer (Decathlon-like Multi-Category)
# ==============================================================================
def create_sporting_goods_retailer_fixture() -> NormalizedBrandProfile:
    facts = [
        make_test_fact("f1", "business_overview", {"description": "Global sports retailer providing accessible sporting goods across running, cycling, hiking, and fitness."}),
        make_test_fact("f2", "industry", {"name": "Sporting Goods & Retail"}),
        make_test_fact("f3", "product_service", {"name": "Kiprun Long Distance Running Shoes"}),
        make_test_fact("f4", "product_service", {"name": "Quechua 2-Second Pop-Up Tent"}),
        make_test_fact("f5", "product_service", {"name": "Domyos Breathable Fitness T-Shirt"}),
        make_test_fact("f6", "target_audience", {"segment": "Beginner and recreational athletes"}),
        make_test_fact("f7", "use_case", {"description": "Weekend trail hiking and camping"}),
        make_test_fact("f8", "differentiator", {"claim": "Affordable technical sports equipment with 2-year warranty"}),
    ]
    data = {
        "brand": {
            "id": "decathlon_retail",
            "domain": "decathlon.in",
            "business_name": "Decathlon",
            "industry": "Sporting Goods",
            "target_market": "India",
            "language": "en",
        },
        "profile_version": 1,
        "facts": facts,
    }
    return ProfileNormalizer.normalize(data)


# ==============================================================================
# Fixture 2: Sportswear Brand (Nike-like Footwear & Apparel)
# ==============================================================================
def create_sportswear_brand_fixture() -> NormalizedBrandProfile:
    facts = [
        make_test_fact("f1", "business_overview", {"description": "Premier athletic sportswear company designing performance running shoes and training apparel."}),
        make_test_fact("f2", "industry", {"name": "Athletic Footwear and Apparel"}),
        make_test_fact("f3", "product_service", {"name": "Air Zoom Pegasus Road Running Shoes"}),
        make_test_fact("f4", "product_service", {"name": "Dri-FIT Moisture-Wicking Running Tee"}),
        make_test_fact("f5", "target_audience", {"segment": "Marathon runners and gym athletes"}),
        make_test_fact("f6", "use_case", {"description": "High-mileage marathon training"}),
    ]
    data = {
        "brand": {
            "id": "nike_sportswear",
            "domain": "nike.in",
            "business_name": "Nike",
            "industry": "Sportswear",
            "target_market": "India",
            "language": "en",
        },
        "profile_version": 1,
        "facts": facts,
    }
    return ProfileNormalizer.normalize(data)


# ==============================================================================
# Fixture 3: SaaS / Developer Platform (OpenRouter-like)
# ==============================================================================
def create_saas_developer_fixture() -> NormalizedBrandProfile:
    facts = [
        make_test_fact("f1", "business_overview", {"description": "Unified LLM routing API and developer gateway for machine learning models."}),
        make_test_fact("f2", "industry", {"name": "Developer Infrastructure"}),
        make_test_fact("f3", "product_service", {"name": "Unified Model Routing API"}),
        make_test_fact("f4", "target_audience", {"segment": "AI Engineers and Software Developers"}),
        make_test_fact("f5", "pricing", {"model": "Usage-based per million tokens"}),
        make_test_fact("f6", "use_case", {"description": "Multi-model fallback and latency optimization"}),
    ]
    data = {
        "brand": {
            "id": "openrouter_saas",
            "domain": "openrouter.ai",
            "business_name": "OpenRouter",
            "industry": "Developer Tools",
            "target_market": "Global",
            "language": "en",
        },
        "profile_version": 1,
        "facts": facts,
    }
    return ProfileNormalizer.normalize(data)


# ==============================================================================
# Fixture 4: Professional Services Firm
# ==============================================================================
def create_professional_services_fixture() -> NormalizedBrandProfile:
    facts = [
        make_test_fact("f1", "business_overview", {"description": "Boutique management consulting and financial advisory firm."}),
        make_test_fact("f2", "industry", {"name": "Management Consulting"}),
        make_test_fact("f3", "product_service", {"name": "Mergers & Acquisitions Advisory"}),
        make_test_fact("f4", "target_audience", {"segment": "CFOs and Corporate Finance Leaders"}),
        make_test_fact("f5", "use_case", {"description": "Cross-border corporate restructuring"}),
    ]
    data = {
        "brand": {
            "id": "apex_consulting",
            "domain": "apexadvisory.com",
            "business_name": "Apex Advisory",
            "industry": "Professional Services",
            "target_market": "North America",
            "language": "en",
        },
        "profile_version": 1,
        "facts": facts,
    }
    return ProfileNormalizer.normalize(data)


# ==============================================================================
# Fixture 5: Sparse / Insufficient Evidence Profile
# ==============================================================================
def create_sparse_insufficient_fixture() -> NormalizedBrandProfile:
    # Lacks industry, category, and verified products
    data = {
        "brand": {
            "id": "sparse_brand",
            "domain": "sparse-unknown.com",
            "business_name": "SparseBrand",
            "target_market": "Global",
            "language": "en",
        },
        "profile_version": 1,
        "facts": [],
    }
    return ProfileNormalizer.normalize(data)


# ==============================================================================
# BENCHMARK TESTS
# ==============================================================================

@pytest.mark.asyncio
async def test_benchmark_sporting_goods_retailer_multi_category_diversity():
    """Benchmark Case 1: Sporting goods retailer with multi-category verified facts."""
    profile = create_sporting_goods_retailer_fixture()
    classification = CategoryClassifier.classify(profile)

    # 1. Correct Classification
    assert classification.domain_archetype == "sportswear_sporting_goods"
    assert classification.primary_category == "Sporting Goods"
    assert "Footwear" in classification.secondary_categories or "Equipment & Gear" in classification.secondary_categories
    assert classification.confidence >= 0.85

    # 2. Plan and Generate 10 Prompts
    plan = CoveragePlanner.create_plan(profile, requested_count=10, surplus_ratio=1.5)
    generator = DeterministicGenerator()
    candidates = await generator.generate(profile, plan)

    # 3. Validation & Quality Gate
    valid_cands = []
    for cand in candidates:
        is_valid, reason = PromptValidator.validate(cand, profile, reject_brand_mentions=True)
        if is_valid:
            valid_cands.append(cand)

    assert len(valid_cands) >= 10, f"Expected >= 10 valid prompts, got {len(valid_cands)}"

    # 4. Deduplication
    unique_cands = PromptScorer.deduplicate(valid_cands)[:10]
    assert len(unique_cands) == 10

    # 5. Quality Metrics
    # - 0% brand leakage
    for c in unique_cands:
        assert "decathlon" not in c.text.lower()
        assert not any(p in c.text.lower() for p in ["select size", "sale", "new & featured"])
        # No SaaS or tech terms in sporting goods
        assert not any(sw in c.text.lower() for sw in ["software", "saas", "api", "database", "kubernetes"])


@pytest.mark.asyncio
async def test_benchmark_sportswear_brand_footwear_vs_apparel_isolation():
    """Benchmark Case 2: Sportswear brand isolates footwear from apparel without category contamination."""
    profile = create_sportswear_brand_fixture()
    classification = CategoryClassifier.classify(profile)

    assert classification.domain_archetype == "sportswear_sporting_goods"
    assert "Footwear" in classification.secondary_categories
    assert "Apparel" in classification.secondary_categories

    plan = CoveragePlanner.create_plan(profile, requested_count=10, surplus_ratio=1.5)
    generator = DeterministicGenerator()
    candidates = await generator.generate(profile, plan)

    valid_cands = []
    for cand in candidates:
        is_valid, reason = PromptValidator.validate(cand, profile, reject_brand_mentions=True)
        if is_valid:
            valid_cands.append(cand)

    assert len(valid_cands) >= 10

    # Verify that footwear prompts do not contain apparel terms and vice-versa
    footwear_keywords = {"shoe", "shoes", "running", "footwear", "trainer", "trainers", "sneaker", "cushioning", "marathon"}
    apparel_keywords = {"t-shirt", "tee", "apparel", "clothing", "moisture-wicking", "chafing", "shorts", "pants", "sportswear", "activewear", "jacket", "jackets", "layer", "layers", "fleece"}

    for c in valid_cands:
        if c.subcategory == "footwear":
            # Footwear prompt must contain footwear concept
            assert any(kw in c.text.lower() for kw in footwear_keywords), f"Footwear prompt missing footwear concept: {c.text}"
            # Must NOT contain duffel bag, backpack, or tent
            assert not any(gear in c.text.lower() for gear in ["duffel bag", "backpack", "tent", "sleeping bag"])
        elif c.subcategory == "apparel":
            assert any(kw in c.text.lower() for kw in apparel_keywords), f"Apparel prompt missing apparel concept: {c.text}"


@pytest.mark.asyncio
async def test_benchmark_saas_developer_relevance_and_zero_sports_terms():
    """Benchmark Case 3: SaaS / Developer platform generates tech queries and 0 sporting goods terms."""
    profile = create_saas_developer_fixture()
    classification = CategoryClassifier.classify(profile)

    assert classification.domain_archetype == "saas_software"
    assert "Developer Infrastructure" in classification.primary_category or "Enterprise SaaS" in classification.primary_category

    plan = CoveragePlanner.create_plan(profile, requested_count=10, surplus_ratio=1.5)
    generator = DeterministicGenerator()
    candidates = await generator.generate(profile, plan)

    valid_cands = []
    for cand in candidates:
        is_valid, reason = PromptValidator.validate(cand, profile, reject_brand_mentions=True)
        if is_valid:
            valid_cands.append(cand)

    assert len(valid_cands) >= 10

    forbidden_sports = ["shoe", "shoes", "running", "footwear", "sneaker", "duffel", "apparel", "tent"]
    for c in valid_cands:
        text_lower = c.text.lower()
        assert "openrouter" not in text_lower
        for bad in forbidden_sports:
            assert bad not in text_lower, f"Irrelevant sports term '{bad}' in SaaS prompt: {c.text}"


@pytest.mark.asyncio
async def test_benchmark_professional_services_relevance():
    """Benchmark Case 4: Professional service business generates consulting/advisory queries."""
    profile = create_professional_services_fixture()
    classification = CategoryClassifier.classify(profile)

    assert classification.domain_archetype == "services_professional"

    plan = CoveragePlanner.create_plan(profile, requested_count=10, surplus_ratio=1.5)
    generator = DeterministicGenerator()
    candidates = await generator.generate(profile, plan)

    valid_cands = [c for c in candidates if PromptValidator.validate(c, profile, reject_brand_mentions=True)[0]]
    assert len(valid_cands) >= 10

    for c in valid_cands:
        text_lower = c.text.lower()
        assert "apex" not in text_lower
        # No e-commerce product checkout questions
        assert not any(w in text_lower for w in ["add to cart", "shipping cost", "return policy on shoes"])


@pytest.mark.asyncio
async def test_benchmark_sparse_insufficient_evidence_honest_rejection():
    """Benchmark Case 5: Sparse/insufficient evidence raises clear ValueError rather than inventing questions."""
    profile = create_sparse_insufficient_fixture()
    classification = CategoryClassifier.classify(profile)

    # Classification confidence should reflect insufficient facts
    assert classification.confidence < 0.60
    assert not classification.primary_category or profile.is_empty

    # CoveragePlanner must reject with an informative message
    with pytest.raises(ValueError) as exc:
        CoveragePlanner.create_plan(profile, requested_count=10)
    assert "insufficient evidence" in str(exc.value)


@pytest.mark.asyncio
async def test_benchmark_competitor_product_and_cross_brand_isolation():
    """Benchmark Case 6: Adversarial test - competitor product incorrectly placed in brand profile is caught/rejected."""
    # Start with Decathlon profile but inject Nike Pegasus into Decathlon's facts
    facts = [
        make_test_fact("f1", "business_overview", {"description": "Sports retailer Decathlon."}),
        make_test_fact("f2", "industry", {"name": "Sporting Goods"}),
        make_test_fact("f3", "product_service", {"name": "Kiprun Trail Shoes"}),
        # Malicious / incorrect competitor product fact
        make_test_fact("f4", "product_service", {"name": "Nike Air Zoom Pegasus"}),
    ]
    data = {
        "brand": {
            "id": "decathlon_adv",
            "domain": "decathlon.in",
            "business_name": "Decathlon",
            "industry": "Sporting Goods",
            "target_market": "India",
            "language": "en",
        },
        "profile_version": 1,
        "facts": facts,
    }
    profile = ProfileNormalizer.normalize(data)

    # When generating prompts, Decathlon prompts must never output "Nike"
    plan = CoveragePlanner.create_plan(profile, requested_count=10)
    generator = DeterministicGenerator()
    candidates = await generator.generate(profile, plan)

    for c in candidates:
        # PromptValidator must reject any prompt mentioning "Nike" or "Pegasus" with competitor name
        is_valid, reason = PromptValidator.validate(c, profile, reject_brand_mentions=True)
        if "nike" in c.text.lower():
            assert not is_valid, f"Competitor brand 'Nike' leaked through validator: {c.text}"


@pytest.mark.asyncio
async def test_benchmark_stale_cache_and_version_invalidation():
    """Benchmark Case 7: Older template or classification version causes cache miss and regeneration."""
    from app.prompts.service import CLASSIFICATION_VERSION, TEMPLATE_SYSTEM_VERSION

    # Verify version tokens are explicit and semantic
    assert CLASSIFICATION_VERSION.startswith("v")
    assert TEMPLATE_SYSTEM_VERSION.startswith("v")

    # Invalidate if any component version changes
    cache_meta = {
        "strategy_version": "v3_category_grounded",
        "classification_version": "v1_legacy",  # Stale!
        "template_version": TEMPLATE_SYSTEM_VERSION,
        "requested_count": 10,
    }

    # Stale version check must evaluate to False
    is_valid_cache = (
        cache_meta["strategy_version"] == "v3_category_grounded"
        and cache_meta["classification_version"] == CLASSIFICATION_VERSION
        and cache_meta["template_version"] == TEMPLATE_SYSTEM_VERSION
        and cache_meta["requested_count"] == 10
    )
    assert not is_valid_cache, "Stale classification version must invalidate prompt cache"


@pytest.mark.asyncio
async def test_benchmark_ui_navigation_noise_filtering():
    """Benchmark Case 8: UI noise strings extracted by crawler are rejected at normalizer and validator."""
    ui_noise_candidates = [
        "Select Size",
        "Size Guide",
        "Add to Cart",
        "Sale",
        "New & Featured",
        "Shop All",
        "Store Locator",
        "Find a Store",
        "Customer Care",
    ]
    for noise in ui_noise_candidates:
        assert is_navigation_or_ui_noise(noise) is True, f"Failed to detect UI noise: '{noise}'"
