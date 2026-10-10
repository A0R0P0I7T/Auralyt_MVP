"""Stage E: Deduplication and Explainable Scoring for Engine 2 Prompt Intelligence."""
import re
import string
import logging
from typing import List, Set, Dict, Tuple
from app.prompts.models import GeneratedPromptCandidate, NormalizedBrandProfile

logger = logging.getLogger(__name__)


def normalize_prompt_text(text: str) -> str:
    """Normalize text for exact and near-duplicate matching."""
    t = text.lower().strip()
    # Strip punctuation
    t = t.translate(str.maketrans("", "", string.punctuation))
    # Normalize whitespace
    t = re.sub(r"\s+", " ", t)
    return t


def token_jaccard_similarity(t1: str, t2: str) -> float:
    """Calculate token Jaccard similarity between two normalized strings."""
    tokens1 = set(t1.split())
    tokens2 = set(t2.split())
    if not tokens1 or not tokens2:
        return 0.0
    intersection = tokens1.intersection(tokens2)
    union = tokens1.union(tokens2)
    return len(intersection) / len(union)


class PromptScorer:
    """Deduplicates candidates and computes explainable quality scores."""

    SIMILARITY_THRESHOLD: float = 0.82

    @classmethod
    def deduplicate(
        cls, candidates: List[GeneratedPromptCandidate]
    ) -> List[GeneratedPromptCandidate]:
        unique_candidates: List[GeneratedPromptCandidate] = []
        seen_normalized: List[str] = []

        for cand in candidates:
            norm = normalize_prompt_text(cand.text)
            if not norm:
                continue

            # Check exact match
            if norm in seen_normalized:
                continue

            # Check near-duplicate Jaccard similarity
            is_near_dup = False
            for prev_norm in seen_normalized:
                if token_jaccard_similarity(norm, prev_norm) >= cls.SIMILARITY_THRESHOLD:
                    is_near_dup = True
                    break

            if not is_near_dup:
                unique_candidates.append(cand)
                seen_normalized.append(norm)

        return unique_candidates

    @classmethod
    def score_candidate(
        cls,
        candidate: GeneratedPromptCandidate,
        profile: NormalizedBrandProfile,
        existing_accepted: List[GeneratedPromptCandidate]
    ) -> GeneratedPromptCandidate:
        """
        Compute transparent, explainable scores across relevance, grounding,
        intent clarity, and diversity.
        """
        text_lower = candidate.text.lower()
        brand_name_lower = profile.business_name.lower()
        industry_lower = (profile.industry or "").lower()

        # 1. Relevance Score (0.0 - 1.0)
        relevance = 0.5
        if brand_name_lower in text_lower:
            relevance += 0.3
        if industry_lower and industry_lower in text_lower:
            relevance += 0.2
        relevance = min(1.0, relevance)

        # 2. Grounding Score (0.0 - 1.0)
        grounding = 0.6
        if candidate.provenance_fact_ids:
            grounding += 0.3
        if candidate.grounding_evidence:
            grounding += 0.1
        grounding = min(1.0, grounding)

        # 3. Intent Clarity (0.0 - 1.0)
        intent_clarity = 0.7
        if candidate.text.endswith("?"):
            intent_clarity += 0.15
        if candidate.intent in ("commercial", "comparative", "transactional"):
            intent_clarity += 0.15
        intent_clarity = min(1.0, intent_clarity)

        # 4. Diversity Score (0.0 - 1.0)
        diversity = 1.0
        if existing_accepted:
            norm_curr = normalize_prompt_text(candidate.text)
            sims = [
                token_jaccard_similarity(norm_curr, normalize_prompt_text(prev.text))
                for prev in existing_accepted
            ]
            max_sim = max(sims) if sims else 0.0
            diversity = max(0.2, 1.0 - max_sim)

        # Overall composite quality score
        overall = round(
            (relevance * 0.35) + (grounding * 0.30) + (intent_clarity * 0.20) + (diversity * 0.15),
            2
        )

        candidate.scores = {
            "relevance": round(relevance, 2),
            "grounding": round(grounding, 2),
            "intent_clarity": round(intent_clarity, 2),
            "diversity": round(diversity, 2),
            "overall_quality": overall,
        }
        candidate.quality_score = overall
        return candidate
