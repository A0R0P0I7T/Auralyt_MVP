"""Gold-Standard Intelligence Benchmark Suite for Auralyt (DEF-EV-01).

Validates Engine 3's attribution, classification, citation domain isolation,
and rank detection accuracy against ground-truth labelled cases across 4 verticals.
"""
import json
from pathlib import Path
import pytest

from app.evaluator.evaluator import VisibilityResponseEvaluator


def load_gold_standard_cases():
    dataset_path = Path(__file__).parent / "benchmarks" / "gold_standard_dataset.json"
    assert dataset_path.exists(), f"Benchmark dataset not found at {dataset_path}"
    with open(dataset_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data["cases"]


def test_gold_standard_evaluation_metrics():
    """Evaluates Engine 3 across the entire gold standard benchmark and computes precision, recall, and accuracy."""
    cases = load_gold_standard_cases()
    assert len(cases) >= 10, "Gold-standard benchmark must have at least 10 representative cases across verticals"

    tp, fp, fn, tn = 0, 0, 0, 0
    rec_matches = 0
    citation_leak_count = 0
    homonym_tests = 0
    homonym_correct_rejections = 0
    rank_matches = 0
    ranked_cases = 0

    for case in cases:
        gt = case["ground_truth"]
        res = VisibilityResponseEvaluator.evaluate(
            response_text=case["provider_response"],
            brand_name=case["target_brand"],
            brand_domain=case["brand_domain"],
            known_competitors=case.get("known_competitors", [])
        )

        # 1. Mention Attribution (Binary Classification)
        if gt["brand_mentioned"] and res.brand_mentioned:
            tp += 1
        elif not gt["brand_mentioned"] and res.brand_mentioned:
            fp += 1
        elif gt["brand_mentioned"] and not res.brand_mentioned:
            fn += 1
        else:
            tn += 1

        # 2. Homonym Specific Handling
        if gt.get("is_homonym"):
            homonym_tests += 1
            if not res.brand_mentioned:
                homonym_correct_rejections += 1

        # 3. Recommendation Classification
        if res.recommendation_status == gt["recommendation_status"]:
            rec_matches += 1

        # 4. Citation Domain Isolation (DEF-E3-01)
        # Verify NO competitor citations leaked into target_brand_citations
        expected_target_cits = set(gt.get("target_citations", []))
        actual_target_cits = set(getattr(res, "target_brand_citations", []))
        for exp_comp_cit in gt.get("competitor_citations", []):
            if exp_comp_cit in actual_target_cits:
                citation_leak_count += 1
        # Target brand citations must match expected target domain URLs
        assert actual_target_cits == expected_target_cits, f"Target citation mismatch in {case['id']}: expected {expected_target_cits}, got {actual_target_cits}"

        # 5. Visibility Rank Detection
        if gt.get("visibility_rank") is not None:
            ranked_cases += 1
            if res.visibility_rank == gt["visibility_rank"]:
                rank_matches += 1

    precision = tp / (tp + fp) if (tp + fp) > 0 else 1.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 1.0
    rec_accuracy = rec_matches / len(cases)
    homonym_rejection_rate = homonym_correct_rejections / homonym_tests if homonym_tests > 0 else 1.0
    rank_accuracy = rank_matches / ranked_cases if ranked_cases > 0 else 1.0

    print(f"\n--- Auralyt Gold Standard Intelligence Benchmark Results ---")
    print(f"Total Cases: {len(cases)}")
    print(f"Mention Attribution Precision: {precision * 100:.1f}% ({tp}/{tp + fp})")
    print(f"Mention Attribution Recall:    {recall * 100:.1f}% ({tp}/{tp + fn})")
    print(f"Recommendation Classification: {rec_accuracy * 100:.1f}% ({rec_matches}/{len(cases)})")
    print(f"Citation Credit Leakage:      {citation_leak_count} competitor leaks")
    print(f"Homonym Rejection Rate:       {homonym_rejection_rate * 100:.1f}% ({homonym_correct_rejections}/{homonym_tests})")
    print(f"Rank Detection Accuracy:      {rank_accuracy * 100:.1f}% ({rank_matches}/{ranked_cases})")

    # Strict Acceptance Gates
    assert precision >= 0.95, f"Mention precision ({precision:.2f}) below 95% target!"
    assert recall >= 0.95, f"Mention recall ({recall:.2f}) below 95% target!"
    assert citation_leak_count == 0, f"Found {citation_leak_count} competitor citations leaked into target citation score!"
    assert homonym_rejection_rate == 1.0, f"Homonym false positives detected! Rate: {homonym_rejection_rate}"
    assert rec_accuracy >= 0.85, f"Recommendation classification accuracy ({rec_accuracy:.2f}) below 85% target!"
    assert rank_accuracy >= 0.90, f"Rank detection accuracy ({rank_accuracy:.2f}) below 90% target!"
