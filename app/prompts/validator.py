"""Stage D: Quality Validation for Engine 2 Prompt Intelligence."""
import re
import logging
from typing import Tuple, Set
from app.prompts.models import GeneratedPromptCandidate, NormalizedBrandProfile

logger = logging.getLogger(__name__)


class PromptValidator:
    """Validates prompt candidates for relevance, natural phrasing, length, and factual grounding."""

    MIN_LENGTH: int = 12
    MAX_LENGTH: int = 350

    @classmethod
    def validate(
        cls, candidate: GeneratedPromptCandidate, profile: NormalizedBrandProfile
    ) -> Tuple[bool, str]:
        text = candidate.text.strip()

        # 1. Length constraints
        if len(text) < cls.MIN_LENGTH:
            return False, f"Prompt too short ({len(text)} chars, minimum {cls.MIN_LENGTH})"
        if len(text) > cls.MAX_LENGTH:
            return False, f"Prompt too long ({len(text)} chars, maximum {cls.MAX_LENGTH})"

        # 2. Basic query syntax / phrasing check
        # Must contain at least one question word or search phrasing
        lowered = text.lower()
        valid_starters = (
            "what", "which", "how", "why", "where", "who", "when", "is", "can",
            "are", "does", "do", "best", "top", "compare", "should", "recommend"
        )
        if not any(lowered.startswith(w) or f" {w} " in lowered for w in valid_starters):
            return False, "Prompt lacks natural query or question structure."

        # 3. Grounding checks by category
        brand_name_lower = profile.business_name.lower()
        domain_lower = profile.domain.lower()
        industry_lower = (profile.industry or "").lower()

        known_entities = {brand_name_lower, domain_lower}
        if industry_lower:
            known_entities.add(industry_lower)
        for p in profile.products_and_services:
            known_entities.add(p.lower())
        for a in profile.target_audiences:
            known_entities.add(a.lower())
        for u in profile.use_cases:
            known_entities.add(u.lower())

        cat = candidate.category
        if cat in ("brand_research", "product_evaluation", "comparisons", "recommendations"):
            # Brand or product must be mentioned
            if not any(entity in lowered for entity in known_entities):
                return False, f"Category '{cat}' requires mention of brand, product, or known capability."

        if cat == "audience_specific" and profile.target_audiences:
            # Must mention either brand or one of the audiences
            has_audience = any(a.lower() in lowered for a in profile.target_audiences)
            has_brand = brand_name_lower in lowered
            if not (has_audience or has_brand):
                return False, "Audience-specific prompt lacks reference to target audience or brand."

        # 4. Check for hallucinated pricing if no pricing exists in profile
        if not profile.pricing_models and any(char in text for char in ("$", "€", "£", "₹")):
            return False, "Prompt contains explicit currency pricing, but no pricing models are documented in the profile."

        return True, ""
