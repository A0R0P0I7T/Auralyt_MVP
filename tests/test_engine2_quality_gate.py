"""Tests for the Engine 2 → Engine 3 quality gate.

Covers:
- Valid prompts pass through unchanged
- Off-category prompts are rejected and replaced with gold fallback
- Brand-steered prompts are rejected
- Feature-check prompts are rejected
- Malformed / too-short prompts are rejected
- Duplicate prompts within the set are rejected
- Gold fallback selects from same category
- No duplicates appear in the final output
- Provenance is recorded (generated vs gold_fallback, gold ID, rejection reason)
- Gold exhaustion produces a shortfall rather than crashing
- Engine 3 receives exactly the validated set
"""
import json
import os
import pytest
from unittest.mock import patch
from pathlib import Path


# ---------------------------------------------------------------------------
# Helpers: minimal prompt dicts that match PromptCandidate-like shapes
# ---------------------------------------------------------------------------

def _make_prompt(text, category="crm", intent="broad_recommendation", quality_score=0.8):
    """Create a minimal prompt dict for quality gate input."""
    return {
        "id": f"test-{hash(text) % 100000:05d}",
        "text": text,
        "category": category,
        "intent": intent,
        "quality_score": quality_score,
        "is_approved": True,
        "target_product_service": None,
        "target_audience": None,
    }


# Canonical gold file path
GOLD_FILE = Path(__file__).parent.parent / "auralyt_engine2_prompt_quality_gold.json"


# ---------------------------------------------------------------------------
# Test: Gold file exists and has expected structure
# ---------------------------------------------------------------------------
class TestGoldFileIntegrity:
    def test_gold_file_exists(self):
        assert GOLD_FILE.exists(), f"Gold file not found at {GOLD_FILE}"

    def test_gold_file_has_100_examples(self):
        data = json.loads(GOLD_FILE.read_text())
        assert len(data["examples"]) == 100

    def test_gold_file_has_5_categories_20_each(self):
        data = json.loads(GOLD_FILE.read_text())
        cats = {}
        for ex in data["examples"]:
            cats.setdefault(ex["category"], []).append(ex)
        assert set(cats.keys()) == {"crm", "ai_assistants", "clothing", "footwear", "skincare"}
        for cat, items in cats.items():
            assert len(items) == 20, f"Category '{cat}' has {len(items)} examples, expected 20"


# ---------------------------------------------------------------------------
# Test: Valid prompts pass gate unchanged
# ---------------------------------------------------------------------------
class TestValidPromptsPassGate:
    def test_valid_crm_prompt_passes(self):
        from app.prompts.quality_gate import QualityGate

        prompt = _make_prompt("What's a good CRM for a small business?", category="crm")
        gate = QualityGate(brand_category="crm")
        result = gate.evaluate(prompt)
        assert result["accepted"] is True
        assert result["provenance"] == "generated"
        assert result["gold_id"] is None
        assert result["rejection_reason"] is None

    def test_valid_prompt_text_unchanged(self):
        from app.prompts.quality_gate import QualityGate

        prompt = _make_prompt("Which CRM is easiest for a small business to get started with?", category="crm")
        gate = QualityGate(brand_category="crm")
        result = gate.evaluate(prompt)
        assert result["text"] == prompt["text"]


# ---------------------------------------------------------------------------
# Test: Off-category prompts are rejected
# ---------------------------------------------------------------------------
class TestOffCategoryRejection:
    def test_skincare_prompt_rejected_for_crm_brand(self):
        from app.prompts.quality_gate import QualityGate

        prompt = _make_prompt("What's the best moisturizer for dry skin?", category="skincare")
        gate = QualityGate(brand_category="crm")
        result = gate.evaluate(prompt)
        assert result["accepted"] is False
        assert "category" in result["rejection_reason"].lower()


# ---------------------------------------------------------------------------
# Test: Brand-steered prompts are rejected
# ---------------------------------------------------------------------------
class TestBrandSteeredRejection:
    def test_prompt_mentioning_specific_brand_rejected(self):
        from app.prompts.quality_gate import QualityGate

        prompt = _make_prompt("Is HubSpot better than Salesforce for small teams?", category="crm")
        gate = QualityGate(brand_category="crm", brand_name="HubSpot", brand_domain="hubspot.com")
        result = gate.evaluate(prompt)
        assert result["accepted"] is False
        assert "brand" in result["rejection_reason"].lower()

    def test_prompt_mentioning_brand_domain_rejected(self):
        from app.prompts.quality_gate import QualityGate

        prompt = _make_prompt("How does hubspot.com compare to other CRMs?", category="crm")
        gate = QualityGate(brand_category="crm", brand_name="HubSpot", brand_domain="hubspot.com")
        result = gate.evaluate(prompt)
        assert result["accepted"] is False
        assert "brand" in result["rejection_reason"].lower()


# ---------------------------------------------------------------------------
# Test: Feature-check / non-discovery prompts are rejected
# ---------------------------------------------------------------------------
class TestFeatureCheckRejection:
    def test_feature_specific_prompt_rejected(self):
        from app.prompts.quality_gate import QualityGate

        prompt = _make_prompt("Does this CRM support Zapier integration?", category="crm")
        gate = QualityGate(brand_category="crm")
        result = gate.evaluate(prompt)
        assert result["accepted"] is False
        assert "feature" in result["rejection_reason"].lower() or "discovery" in result["rejection_reason"].lower()


# ---------------------------------------------------------------------------
# Test: Malformed prompts are rejected
# ---------------------------------------------------------------------------
class TestMalformedRejection:
    def test_too_short_prompt_rejected(self):
        from app.prompts.quality_gate import QualityGate

        prompt = _make_prompt("Best CRM?", category="crm")
        gate = QualityGate(brand_category="crm")
        result = gate.evaluate(prompt)
        assert result["accepted"] is False
        assert "short" in result["rejection_reason"].lower() or "length" in result["rejection_reason"].lower()


# ---------------------------------------------------------------------------
# Test: Duplicate prompts within a batch are rejected
# ---------------------------------------------------------------------------
class TestDuplicateRejection:
    def test_duplicate_prompt_rejected_in_batch(self):
        from app.prompts.quality_gate import QualityGate

        prompts = [
            _make_prompt("What's a good CRM for a small business?", category="crm"),
            _make_prompt("What's a good CRM for a small business?", category="crm"),  # exact dup
        ]
        gate = QualityGate(brand_category="crm")
        results = gate.evaluate_batch(prompts, target_count=2)

        generated_accepted = [r for r in results if r["accepted"] and r["provenance"] == "generated"]
        assert len(generated_accepted) == 1, "Only one of the duplicate generated prompts should be accepted"

        rejected = [r for r in results if not r["accepted"]]
        assert any("duplicate" in (r.get("rejection_reason") or "").lower() for r in rejected), \
            "One prompt should be rejected as duplicate"


# ---------------------------------------------------------------------------
# Test: Gold fallback selects from same category
# ---------------------------------------------------------------------------
class TestGoldFallbackSelection:
    def test_rejected_prompt_replaced_by_same_category_gold(self):
        from app.prompts.quality_gate import QualityGate

        prompt = _make_prompt("What's the best moisturizer for dry skin?", category="skincare")
        gate = QualityGate(brand_category="crm")
        results = gate.evaluate_batch([prompt], target_count=1)

        # The rejected prompt should be replaced with a gold CRM prompt
        final = [r for r in results if r["accepted"]]
        assert len(final) == 1
        assert final[0]["provenance"] == "gold_fallback"
        assert final[0]["gold_id"] is not None
        assert final[0]["gold_id"].startswith("CRM-")

    def test_fallback_prompt_text_matches_gold(self):
        from app.prompts.quality_gate import QualityGate

        data = json.loads(GOLD_FILE.read_text())
        crm_gold = {ex["id"]: ex["query"] for ex in data["examples"] if ex["category"] == "crm"}

        prompt = _make_prompt("What's the best moisturizer for dry skin?", category="skincare")
        gate = QualityGate(brand_category="crm")
        results = gate.evaluate_batch([prompt], target_count=1)

        final = [r for r in results if r["accepted"]]
        assert len(final) == 1
        gold_id = final[0]["gold_id"]
        assert final[0]["text"] == crm_gold[gold_id], "Fallback text must match gold query exactly"


# ---------------------------------------------------------------------------
# Test: No duplicates in the final output set
# ---------------------------------------------------------------------------
class TestNoDuplicatesInOutput:
    def test_final_set_has_unique_texts(self):
        from app.prompts.quality_gate import QualityGate

        prompts = [
            _make_prompt(f"What's a good CRM for a small business #{i}?", category="crm")
            for i in range(18)
        ] + [
            # Two off-category that will need gold fallback
            _make_prompt("Best moisturizer for oily skin?", category="skincare"),
            _make_prompt("What running shoes have best cushioning?", category="footwear"),
        ]
        gate = QualityGate(brand_category="crm")
        results = gate.evaluate_batch(prompts, target_count=20)

        accepted = [r for r in results if r["accepted"]]
        texts = [r["text"] for r in accepted]
        assert len(texts) == len(set(texts)), "Final output must have unique texts"


# ---------------------------------------------------------------------------
# Test: Provenance tracking
# ---------------------------------------------------------------------------
class TestProvenanceTracking:
    def test_generated_prompt_has_generated_provenance(self):
        from app.prompts.quality_gate import QualityGate

        prompt = _make_prompt("What's a good CRM for a small business?", category="crm")
        gate = QualityGate(brand_category="crm")
        result = gate.evaluate(prompt)
        assert result["provenance"] == "generated"
        assert result["gold_id"] is None

    def test_fallback_prompt_has_gold_fallback_provenance(self):
        from app.prompts.quality_gate import QualityGate

        prompt = _make_prompt("Best moisturizer?", category="skincare")
        gate = QualityGate(brand_category="crm")
        results = gate.evaluate_batch([prompt], target_count=1)
        fallbacks = [r for r in results if r["provenance"] == "gold_fallback"]
        assert len(fallbacks) == 1
        assert fallbacks[0]["gold_id"] is not None

    def test_rejection_reason_preserved(self):
        from app.prompts.quality_gate import QualityGate

        prompt = _make_prompt("Best moisturizer?", category="skincare")
        gate = QualityGate(brand_category="crm")
        result = gate.evaluate(prompt)
        assert result["rejection_reason"] is not None
        assert len(result["rejection_reason"]) > 0


# ---------------------------------------------------------------------------
# Test: Gold exhaustion
# ---------------------------------------------------------------------------
class TestGoldExhaustion:
    def test_exhaustion_produces_shortfall_not_crash(self):
        from app.prompts.quality_gate import QualityGate

        # Create 25 off-category prompts — only 20 CRM golds exist
        prompts = [
            _make_prompt(f"Best moisturizer for skin type #{i}?", category="skincare")
            for i in range(25)
        ]
        gate = QualityGate(brand_category="crm")
        results = gate.evaluate_batch(prompts, target_count=25)

        accepted = [r for r in results if r["accepted"]]
        # At most 20 CRM golds available
        assert len(accepted) <= 20
        # Report shortfall
        stats = gate.get_stats()
        assert stats["shortfall"] >= 5

    def test_exhaustion_does_not_duplicate_gold_prompts(self):
        from app.prompts.quality_gate import QualityGate

        prompts = [
            _make_prompt(f"Best moisturizer for skin type #{i}?", category="skincare")
            for i in range(25)
        ]
        gate = QualityGate(brand_category="crm")
        results = gate.evaluate_batch(prompts, target_count=25)

        accepted = [r for r in results if r["accepted"]]
        gold_ids = [r["gold_id"] for r in accepted if r["gold_id"]]
        assert len(gold_ids) == len(set(gold_ids)), "No duplicate gold IDs in exhaustion scenario"


# ---------------------------------------------------------------------------
# Test: Pass rate and fallback rate are separate
# ---------------------------------------------------------------------------
class TestSeparateRates:
    def test_stats_track_separate_rates(self):
        from app.prompts.quality_gate import QualityGate

        prompts = [
            _make_prompt("What's a good CRM for a small business?", category="crm"),
            _make_prompt("Best moisturizer for dry skin?", category="skincare"),
        ]
        gate = QualityGate(brand_category="crm")
        gate.evaluate_batch(prompts, target_count=2)

        stats = gate.get_stats()
        assert "generated_pass_rate" in stats
        assert "fallback_rate" in stats
        assert stats["generated_pass_rate"] == 0.5  # 1 of 2 passed
        assert stats["fallback_rate"] == 0.5  # 1 of 2 is gold fallback
