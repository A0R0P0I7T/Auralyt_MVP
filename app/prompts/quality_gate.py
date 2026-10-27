"""Quality Gate between Engine 2 and Engine 3.

Validates each Engine 2 prompt candidate for:
- Category match with the target brand
- Brand mention / domain steering
- Discovery intent (rejects feature-check or support questions)
- Minimum text length
- Duplicate detection within the batch

Replaces rejected prompts with unused gold queries from the same category.
Tracks provenance (generated vs gold_fallback) and reports separate rates.
"""
import json
import re
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from app.prompts.scorer import normalize_prompt_text

logger = logging.getLogger(__name__)

# Unicode smart/curly quote translation table for normalization
_SMART_QUOTE_TABLE = str.maketrans({
    "\u2018": "'", "\u2019": "'",  # ' '
    "\u201C": '"', "\u201D": '"',  # " "
    "\u2013": "-", "\u2014": "-",  # – —
})


def _normalize_for_dedup(text: str) -> str:
    """Normalize text for deduplication — handles smart quotes before standard normalization."""
    return normalize_prompt_text(text.translate(_SMART_QUOTE_TABLE))

# Path to the gold queries file (project root)
GOLD_FILE_PATH = Path(__file__).parent.parent.parent / "auralyt_engine2_prompt_quality_gold.json"

# Minimum prompt text length for quality gate acceptance (aligned with PromptValidator)
MIN_TEXT_LENGTH = 12

# Benchmark categories defined in the gold dataset
KNOWN_BENCHMARK_CATEGORIES = {"crm", "ai_assistants", "clothing", "footwear", "skincare"}

_CATEGORY_KEYWORDS = {
    "crm": ["crm", "sales pipeline", "lead management", "customer relationship"],
    "ai_assistants": ["ai assistant", "chatbot", "chatgpt", "large language model"],
    "clothing": ["clothing", "apparel", "jacket", "shirt", "pants", "dress", "outfit"],
    "footwear": ["shoes", "footwear", "sneakers", "boots", "running shoes"],
    "skincare": ["skincare", "moisturizer", "serum", "cleanser", "lotion", "sunscreen"],
}

# Feature-check / non-discovery signal patterns
_FEATURE_CHECK_PATTERNS = [
    re.compile(r"\bdoes\s+(this|it|the)\s+\w+\s+support\b", re.IGNORECASE),
    re.compile(r"\bcan\s+(this|it|the)\s+\w+\s+(integrate|connect|sync)\b", re.IGNORECASE),
    re.compile(r"\bhow\s+do\s+I\s+(set\s+up|configure|enable|install)\b", re.IGNORECASE),
    re.compile(r"\bwhat\s+is\s+the\s+API\s+(endpoint|key|limit)\b", re.IGNORECASE),
    re.compile(r"\bhow\s+to\s+(reset|change)\s+(my|the)\s+(password|settings)\b", re.IGNORECASE),
]


def _load_gold_examples() -> Dict[str, List[Dict[str, Any]]]:
    """Load gold examples grouped by category."""
    if not GOLD_FILE_PATH.exists():
        logger.warning(f"Gold file not found at {GOLD_FILE_PATH}")
        return {}
    data = json.loads(GOLD_FILE_PATH.read_text())
    by_category: Dict[str, List[Dict[str, Any]]] = {}
    for ex in data.get("examples", []):
        by_category.setdefault(ex["category"], []).append(ex)
    return by_category


class QualityGate:
    """Validates Engine 2 prompts and replaces rejected ones with gold fallbacks."""

    def __init__(
        self,
        brand_category: str,
        brand_name: Optional[str] = None,
        brand_domain: Optional[str] = None,
    ):
        self.brand_category = brand_category.lower()
        self.brand_name = brand_name
        self.brand_domain = brand_domain

        # Build forbidden brand tokens
        self._forbidden_tokens: List[str] = []
        if brand_name:
            name_lower = brand_name.strip().lower()
            if len(name_lower) >= 3:
                self._forbidden_tokens.append(name_lower)
            for part in name_lower.split():
                if len(part) >= 4 and part not in ("platform", "technologies", "software", "solutions"):
                    self._forbidden_tokens.append(part)
        if brand_domain:
            d_clean = brand_domain.lower().replace("www.", "").strip()
            self._forbidden_tokens.append(d_clean)
            # Extract registrable label (e.g. "hubspot" from "hubspot.com")
            host = d_clean.split(".")[0] if "." in d_clean else d_clean
            if len(host) >= 3 and host not in ("app", "com", "net", "org", "dev", "io"):
                self._forbidden_tokens.append(host)

        # Load gold examples
        self._gold_by_category = _load_gold_examples()
        self._used_gold_ids: Set[str] = set()

        # Stats
        self._total_evaluated = 0
        self._generated_passed = 0
        self._rejected_count = 0
        self._fallback_count = 0
        self._shortfall = 0

    def evaluate(self, prompt: Dict[str, Any]) -> Dict[str, Any]:
        """Evaluate a single prompt. Returns dict with accepted, provenance, etc."""
        self._total_evaluated += 1
        text = prompt.get("text", "").strip()
        text_lower = text.lower()
        prompt_category = prompt.get("category", "").lower()

        # Allow test simulation prompts to pass through to mock provider
        if "[SIMULATE_" in text:
            self._generated_passed += 1
            return {
                "accepted": True,
                "text": text,
                "provenance": "generated",
                "gold_id": None,
                "rejection_reason": None,
                "original_id": prompt.get("id"),
            }

        # Check 1: Minimum text length
        if len(text) < MIN_TEXT_LENGTH:
            self._rejected_count += 1
            return {
                "accepted": False,
                "text": text,
                "provenance": "generated",
                "gold_id": None,
                "rejection_reason": f"Prompt too short ({len(text)} chars, minimum {MIN_TEXT_LENGTH})",
                "original_id": prompt.get("id"),
            }

        # Check 2: Category match
        # Direct mismatch between two known benchmark product categories
        is_direct_mismatch = (
            prompt_category in KNOWN_BENCHMARK_CATEGORIES
            and self.brand_category in KNOWN_BENCHMARK_CATEGORIES
            and prompt_category != self.brand_category
        )
        # Or prompt text contains clear keywords of a conflicting benchmark category
        has_conflicting_keywords = False
        if self.brand_category in KNOWN_BENCHMARK_CATEGORIES:
            for other_cat, kws in _CATEGORY_KEYWORDS.items():
                if other_cat != self.brand_category:
                    if any(kw in text_lower for kw in kws) and not any(kw in text_lower for kw in _CATEGORY_KEYWORDS.get(self.brand_category, [])):
                        has_conflicting_keywords = True
                        break

        if is_direct_mismatch or has_conflicting_keywords:
            self._rejected_count += 1
            return {
                "accepted": False,
                "text": text,
                "provenance": "generated",
                "gold_id": None,
                "rejection_reason": f"Off-category: prompt category '{prompt_category}' does not match brand category '{self.brand_category}'",
                "original_id": prompt.get("id"),
            }

        # Check 3: Brand mention / domain steering
        for token in self._forbidden_tokens:
            if re.search(rf"\b{re.escape(token)}\b", text_lower):
                self._rejected_count += 1
                return {
                    "accepted": False,
                    "text": text,
                    "provenance": "generated",
                    "gold_id": None,
                    "rejection_reason": f"Brand-steered: prompt contains brand token '{token}'",
                    "original_id": prompt.get("id"),
                }

        # Check 4: Feature-check / non-discovery intent
        for pattern in _FEATURE_CHECK_PATTERNS:
            if pattern.search(text):
                self._rejected_count += 1
                return {
                    "accepted": False,
                    "text": text,
                    "provenance": "generated",
                    "gold_id": None,
                    "rejection_reason": "Non-discovery prompt: appears to be a feature-check or support question rather than a category discovery query",
                    "original_id": prompt.get("id"),
                }

        # Passed all checks
        self._generated_passed += 1
        return {
            "accepted": True,
            "text": text,
            "provenance": "generated",
            "gold_id": None,
            "rejection_reason": None,
            "original_id": prompt.get("id"),
        }

    def evaluate_batch(
        self,
        prompts: List[Dict[str, Any]],
        target_count: Optional[int] = None,
    ) -> List[Dict[str, Any]]:
        """
        Evaluate a batch of prompts:
        1. Validate each prompt
        2. Deduplicate accepted prompts
        3. Replace rejected prompts with gold fallbacks
        4. Return final list with provenance
        """
        if target_count is None:
            target_count = len(prompts)

        results: List[Dict[str, Any]] = []
        seen_normalized: Set[str] = set()
        accepted_count = 0
        rejected_entries: List[Dict[str, Any]] = []

        # Phase 1: Evaluate all prompts
        for prompt in prompts:
            result = self.evaluate(prompt)

            if result["accepted"]:
                # Deduplicate within accepted set
                norm_text = _normalize_for_dedup(result["text"])
                if norm_text in seen_normalized:
                    result["accepted"] = False
                    result["rejection_reason"] = "Duplicate prompt within batch"
                    self._generated_passed -= 1  # Undo pass count
                    self._rejected_count += 1
                    rejected_entries.append(result)
                else:
                    seen_normalized.add(norm_text)
                    results.append(result)
                    accepted_count += 1
            else:
                rejected_entries.append(result)

        # Phase 2: Fill shortfall with gold fallbacks
        needed = target_count - accepted_count
        if needed > 0:
            gold_candidates = self._gold_by_category.get(self.brand_category) or self._gold_by_category.get("crm", [])
            for gold in gold_candidates:
                if needed <= 0:
                    break
                if gold["id"] in self._used_gold_ids:
                    continue

                # Ensure gold text isn't a duplicate of an already accepted prompt
                gold_norm = _normalize_for_dedup(gold["query"])
                if gold_norm in seen_normalized:
                    continue

                self._used_gold_ids.add(gold["id"])
                seen_normalized.add(gold_norm)
                self._fallback_count += 1

                results.append({
                    "accepted": True,
                    "text": gold["query"],
                    "provenance": "gold_fallback",
                    "gold_id": gold["id"],
                    "rejection_reason": None,
                    "original_id": None,
                    "category": gold.get("category", self.brand_category),
                    "intent": gold.get("intent", "broad_recommendation"),
                })
                needed -= 1

            if needed > 0:
                self._shortfall += needed

        # Also include rejected entries for provenance reporting
        results.extend(rejected_entries)
        return results

    def get_stats(self) -> Dict[str, Any]:
        """Return quality gate statistics with separate pass/fallback rates."""
        total = self._total_evaluated or 1
        return {
            "total_evaluated": self._total_evaluated,
            "generated_passed": self._generated_passed,
            "rejected_count": self._rejected_count,
            "fallback_count": self._fallback_count,
            "shortfall": self._shortfall,
            "generated_pass_rate": round(self._generated_passed / total, 4),
            "fallback_rate": round(self._fallback_count / total, 4),
        }
