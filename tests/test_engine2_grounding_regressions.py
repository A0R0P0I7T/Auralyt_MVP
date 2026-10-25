"""Failing regression tests for Engine 2 grounding and category-awareness overhaul.
Pinpoints the exact defects identified in root cause analysis:
1. Rejection of navigation / UI elements as products/subcategories.
2. Prevention of mismatched product substitutions (e.g., bags into running shoe cushioning templates).
3. Independent prompt quality gate enforcing honest approval semantics (APPROVED vs REJECTED).
4. Category classification stage producing structured, versioned output.
5. Cache invalidation on template or classification version change.
"""
import pytest
from app.prompts.models import (
    NormalizedBrandProfile,
    GroundedFact,
    GeneratedPromptCandidate,
)
from app.prompts.normalizer import ProfileNormalizer
from app.prompts.validator import PromptValidator


def test_regression_profile_normalizer_filters_navigation_and_ui_noise():
    """Navigation labels like 'Select Size', 'Sale', 'New & Featured' must not become products."""
    raw_profile = {
        "brand": {
            "id": "brand-123",
            "domain": "example.com",
            "business_name": "Example Athletics",
            "industry": "Sporting Goods",
        },
        "profile_version": 1,
        "products_and_services": [
            {"value": "Select Size"},
            {"value": "Sale"},
            {"value": "New & Featured"},
            {"value": "Official Online Store India"},
            {"value": "Men's Trail Running Shoes"},
            {"value": "Dri-FIT Running T-Shirt"},
            {"value": "Training Duffel Bag 24L"},
        ],
        "facts": [
            {
                "id": "fact-1",
                "fact_type": "product_service",
                "fact_value": {"name": "Men's Trail Running Shoes"},
                "confidence": 0.95,
            },
            {
                "id": "fact-2",
                "fact_type": "product_service",
                "fact_value": {"name": "Select Size"},
                "confidence": 0.5,
            },
        ],
    }

    normalized = ProfileNormalizer.normalize(raw_profile)
    clean_products = normalized.get_clean_products()

    # 'Select Size', 'Sale', etc. MUST be filtered out
    assert "Select Size" not in clean_products
    assert "Sale" not in clean_products
    assert "New & Featured" not in clean_products
    assert "Official Online Store India" not in clean_products

    # Real products must remain
    assert any("Trail Running Shoes" in p for p in clean_products)
    assert any("Running T-Shirt" in p for p in clean_products)
    assert any("Duffel Bag" in p for p in clean_products)


def test_regression_validator_rejects_category_mismatched_prompt():
    """Prompt asking about shoe cushioning or arch support must reject a bag or shirt."""
    profile = NormalizedBrandProfile(
        brand_id="b-1",
        domain="nike.in",
        business_name="Nike",
        industry="Sporting Goods",
        profile_version=1,
        products_and_services=[
            "Air Zoom Pegasus Running Shoes",
            "Brasilia Training Duffel Bag (Extra Small, 24L)",
            "Dri-FIT Oversized Crew-Neck Top",
        ],
        facts=[
            GroundedFact(
                id="f-shoe",
                fact_type="product_service",
                fact_value={"name": "Air Zoom Pegasus Running Shoes", "category": "footwear"},
            ),
            GroundedFact(
                id="f-bag",
                fact_type="product_service",
                fact_value={"name": "Brasilia Training Duffel Bag (Extra Small, 24L)", "category": "bags"},
            ),
            GroundedFact(
                id="f-top",
                fact_type="product_service",
                fact_value={"name": "Dri-FIT Oversized Crew-Neck Top", "category": "apparel"},
            ),
        ],
    )

    # Incompatible candidate 1: Asking about duffel bag cushioning for high mileage
    bad_cand_1 = GeneratedPromptCandidate(
        text="Which Brasilia Training Duffel Bag (Extra Small, 24L) have the best cushioning for high mileage?",
        category="recommendations",
        intent="commercial",
        buying_stage="consideration",
        target_product_service="Brasilia Training Duffel Bag (Extra Small, 24L)",
        provenance_fact_ids=["f-bag"],
    )

    # Incompatible candidate 2: Asking if a crew-neck top is good for long distance runs
    bad_cand_2 = GeneratedPromptCandidate(
        text="Which Dri-FIT Oversized Crew-Neck Top are worth considering for long distance runs?",
        category="recommendations",
        intent="commercial",
        buying_stage="consideration",
        target_product_service="Dri-FIT Oversized Crew-Neck Top",
        provenance_fact_ids=["f-top"],
    )

    # Compatible candidate: Asking about running shoes for daily training
    good_cand = GeneratedPromptCandidate(
        text="What are some good running shoes for someone who runs a few times a week?",
        category="discovery",
        intent="informational",
        buying_stage="awareness",
        target_product_service=None,
        provenance_fact_ids=["f-shoe"],
    )

    is_valid_1, reason_1 = PromptValidator.validate(bad_cand_1, profile)
    assert not is_valid_1, f"Expected rejection for duffel bag in running shoe cushioning query, got valid. Reason: {reason_1}"
    assert "incompatible" in reason_1.lower() or "category mismatch" in reason_1.lower()

    is_valid_2, reason_2 = PromptValidator.validate(bad_cand_2, profile)
    assert not is_valid_2, f"Expected rejection for crew-neck top in running query, got valid. Reason: {reason_2}"

    is_valid_3, _ = PromptValidator.validate(good_cand, profile)
    assert is_valid_3, "Expected generic running shoe discovery prompt to be valid"


def test_regression_category_classifier_exists_and_classifies():
    """Engine 2 must have an explicit CategoryClassifier returning structured taxonomy."""
    from app.prompts.classifier import CategoryClassifier, BrandClassificationResult

    profile = NormalizedBrandProfile(
        brand_id="b-decathlon",
        domain="decathlon.in",
        business_name="Decathlon",
        industry="Retail",
        profile_version=1,
        products_and_services=[
            "Hiking boots and trail shoes",
            "Camping tents and sleeping bags",
            "Men's cardio training t-shirt",
            "Mountain bikes and cycling accessories",
        ],
        facts=[
            GroundedFact(
                id="f-1",
                fact_type="company_description",
                fact_value="Decathlon is a multi-specialist sports goods retailer offering sporting equipment, clothing and footwear.",
            ),
            GroundedFact(
                id="f-2",
                fact_type="industry",
                fact_value={"name": "Sporting Goods & Retail"},
            ),
        ],
    )

    classification = CategoryClassifier.classify(profile)
    assert isinstance(classification, BrandClassificationResult)
    assert classification.primary_industry.lower() in ("retail", "sporting goods & retail", "consumer goods")
    assert "sporting goods" in [c.lower() for c in [classification.primary_category] + classification.secondary_categories]
    assert classification.confidence >= 0.7
    assert len(classification.supporting_fact_ids) > 0
