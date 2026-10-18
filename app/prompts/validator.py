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
        cls,
        candidate: GeneratedPromptCandidate,
        profile: NormalizedBrandProfile,
        reject_brand_mentions: bool = False,
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
        if re.search(r"\{[a-zA-Z_]+\}", text):
            return False, "Prompt contains unreplaced template placeholders."

        if not text.endswith("?"):
            return False, "Prompt must end with a question mark."

        valid_starters = (
            "what", "which", "how", "why", "where", "who", "when", "is", "can",
            "are", "does", "do", "best", "top", "compare", "should", "recommend", "i'm", "im"
        )
        if not any(lowered.startswith(w) or f" {w} " in lowered for w in valid_starters):
            return False, "Prompt lacks natural query or question structure."

        # 2b. Domain Archetype Category Locking
        archetype = profile.get_domain_archetype()
        if archetype == "footwear_apparel":
            incompatible_terms = (
                "software", "api", "database", "saas", "cloud infrastructure", "backend",
                "devops", "kubernetes", "sql", "crm", "serverless", "microservices",
                "headphones", "earbuds", "audio", "speakers", "smartphones", "laptop",
                "monitor", "television", "cryptocurrency", "real estate", "mortgage"
            )
            for term in incompatible_terms:
                if re.search(rf"\b{re.escape(term)}\b", lowered):
                    return False, f"Prompt contains term '{term}' incompatible with footwear/apparel archetype."
        elif archetype == "developer_infrastructure":
            footwear_terms = ("sneakers", "running shoes", "footwear", "trainers", "skincare", "cosmetics", "dresses")
            for term in footwear_terms:
                if re.search(rf"\b{re.escape(term)}\b", lowered):
                    return False, f"Prompt contains consumer goods term '{term}' incompatible with developer infrastructure archetype."

        # 3. Grounding checks by category & fact IDs
        cat = candidate.category
        fact_by_id = {fact.id: fact for fact in profile.facts if fact.id}
        unknown_fact_ids = set(candidate.provenance_fact_ids) - set(fact_by_id)
        if unknown_fact_ids:
            return False, "Prompt references fact IDs outside the active profile snapshot."

        grounded_categories = {
            "product_evaluation": {"product_service", "product_feature"},
            "audience_specific": {"target_audience"},
            "use_cases": {"use_case"},
            "pricing_value": {"pricing"},
            "brand_research": {"differentiator", "industry", "business_overview"},
        }
        required_types = grounded_categories.get(cat, set())
        if required_types and any(f.fact_type in required_types for f in profile.facts):
            if not candidate.provenance_fact_ids:
                return False, f"Category '{cat}' requires provenance from the active profile facts."
            if not any(fact_by_id[fid].fact_type in required_types for fid in candidate.provenance_fact_ids):
                return False, f"Category '{cat}' is not grounded by a relevant fact type."

        clean_prods = profile.get_clean_products()
        if candidate.target_product_service:
            if (candidate.target_product_service not in profile.products_and_services and
                candidate.target_product_service not in clean_prods and
                candidate.target_product_service != profile.get_primary_category()):
                return False, "Prompt references a product outside the active profile."

        clean_auds = profile.get_clean_audiences()
        if candidate.target_audience:
            if (candidate.target_audience not in profile.target_audiences and
                candidate.target_audience not in clean_auds and
                candidate.target_audience != "teams"):
                return False, "Prompt references an audience outside the active profile."

        if candidate.grounding_evidence:
            known_evidence = {
                fact.evidence_snippet for fact in profile.facts if fact.evidence_snippet
            }
            known_evidence.update(
                evidence.get("snippet")
                for fact in profile.facts
                for evidence in fact.supporting_evidence
                if evidence.get("snippet")
            )
            if not set(candidate.grounding_evidence).issubset(known_evidence):
                return False, "Prompt contains evidence not present in the active profile."

        # 4. Check for hallucinated pricing if no pricing exists in profile
        if not profile.pricing_models and any(char in text for char in ("$", "€", "£", "₹")):
            return False, "Prompt contains explicit currency pricing, but no pricing models are documented in the profile."

        # 5. Central Organic Rule: Organic prompts must NOT contain target brand name, domain, or aliases
        if reject_brand_mentions:
            from app.evaluator.evaluator import COMMON_DICTIONARY_BRAND_NAMES

            for token in profile.get_forbidden_brand_tokens():
                token_lower = token.lower()
                matches = list(re.finditer(rf"\b{re.escape(token)}\b", lowered))
                if not matches:
                    continue

                # Contextual disambiguation for common dictionary words (DEF-E2-03)
                if token_lower in COMMON_DICTIONARY_BRAND_NAMES:
                    dict_info = COMMON_DICTIONARY_BRAND_NAMES[token_lower]
                    neg_colls = dict_info.get("negative_collocations", [])
                    all_matches_benign = True
                    for m in matches:
                        win_start = max(0, m.start() - 35)
                        win_end = min(len(lowered), m.end() + 35)
                        window = lowered[win_start:win_end]
                        is_collocation = any(re.search(pat, window, re.IGNORECASE) for pat in neg_colls)
                        if not is_collocation:
                            all_matches_benign = False
                            break
                    if all_matches_benign:
                        continue

                return False, f"Organic prompt must not contain target brand token '{token}'."


        return True, ""
