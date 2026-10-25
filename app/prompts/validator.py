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

        if text.count('"') % 2 != 0:
            return False, "Prompt contains unbalanced quotation marks."

        valid_starters = (
            "what", "which", "how", "why", "where", "who", "when", "is", "can",
            "are", "does", "do", "best", "top", "compare", "should", "recommend", "i'm", "im"
        )
        if not any(lowered.startswith(w) or f" {w} " in lowered for w in valid_starters):
            return False, "Prompt lacks natural query or question structure."

        # 2a. Deterministic Natural-Language & Spelling Integrity Checks
        # Repeated words check (e.g. 'the the', 'for for')
        rep_match = re.search(r"\b([a-zA-Z]{2,})\s+\1\b", lowered)
        if rep_match:
            return False, f"Prompt contains repeated consecutive word '{rep_match.group(1)}'."
        # Check for malformed gerund spelling (e.g. createing, completeing, writeing where silent 'e' was not dropped)
        # Excludes valid English words like being, well-being, ageing
        malformed_gerund = re.search(r"\b(?!(?:being|well-being|ageing)\b)[a-z]+[bcdfghjklmnpqrstvwxz]eing\b", lowered)
        if malformed_gerund:
            return False, f"Prompt contains malformed gerund spelling '{malformed_gerund.group(0)}'."

        # Check for awkward double participles / ungrammatical 'needing <gerund>'
        if re.search(r"\bneeding\s+[a-z]+ing\b", lowered):
            return False, "Prompt contains awkward double participle or ungrammatical 'needing <gerund>' phrasing."

        # Check for compound capability dumps / mechanically spliced capability lists
        if re.search(r"(?:,\s*(?:write|create|complete|code|answer|generate|build|manage|track|scale|and\s+[a-z]+)){2,}", lowered) or (
            lowered.count(",") >= 3 and any(w in lowered for w in ("write", "create", "complete", "code", "answer", "images", "questions"))
        ):
            return False, "Prompt contains unnatural compound capability dump combining multiple unrelated actions."

        # 2b. Domain Archetype Category Locking & Navigation Noise Rejection
        from app.prompts.normalizer import is_navigation_or_ui_noise, UI_NAVIGATION_NOISE_PATTERNS

        # Check for navigation noise in text or target_product_service
        if candidate.target_product_service and is_navigation_or_ui_noise(candidate.target_product_service):
            return False, f"Prompt targets navigation or UI artifact '{candidate.target_product_service}' instead of a valid product."

        for noise in ("select size", "new & featured", "new and featured", "official online store", "shop all sale"):
            if re.search(rf"\b{re.escape(noise)}\b", lowered):
                return False, f"Prompt contains navigation/UI noise phrase '{noise}'."

        archetype = profile.get_domain_archetype()
        if archetype in ("footwear_apparel", "sportswear_sporting_goods"):
            incompatible_terms = (
                "software", "api", "database", "saas", "cloud infrastructure", "backend",
                "devops", "kubernetes", "sql", "crm", "serverless", "microservices",
                "headphones", "earbuds", "audio", "speakers", "smartphones", "laptop",
                "monitor", "television", "cryptocurrency", "real estate", "mortgage"
            )
            for term in incompatible_terms:
                if re.search(rf"\b{re.escape(term)}\b", lowered):
                    return False, f"Prompt contains term '{term}' incompatible with footwear/apparel archetype."

            # Category / Subcategory Semantic Compatibility
            # Footwear-specific questions: cushioning, arch support, running shoe mileage, daily trainers, etc.
            footwear_query_signals = (
                "cushioning", "arch support", "shock absorption", "daily trainer", "daily trainers",
                "racing shoe", "trail running", "road running", "long distance run", "long distance runs",
                "high mileage", "cushioned and lightweight", "stability or neutral", "blister",
                "running shoe", "running shoes", "marathon"
            )
            is_footwear_query = any(sig in lowered for sig in footwear_query_signals)

            prod_target = (candidate.target_product_service or "").lower()
            apparel_signals = ("shirt", "t-shirt", "top", "crew-neck", "jacket", "hoodie", "tracksuit", "trousers", "pants", "shorts", "bra", "dress")
            gear_signals = ("bag", "duffel", "backpack", "tent", "sleeping bag", "mat", "bottle", "racket", "ball")

            if is_footwear_query:
                # If question is explicitly about footwear features/cushioning/running, product must not be a bag or shirt
                if any(re.search(rf"\b{re.escape(sig)}\b", prod_target) for sig in apparel_signals) or any(re.search(rf"\b{re.escape(sig)}\b", lowered) and sig in prod_target for sig in apparel_signals):
                    return False, "Category mismatch: footwear-specific feature or running query applied to incompatible apparel product."
                if any(re.search(rf"\b{re.escape(sig)}\b", prod_target) for sig in gear_signals) or any(re.search(rf"\b{re.escape(sig)}\b", lowered) and sig in prod_target for sig in gear_signals):
                    return False, "Category mismatch: footwear-specific feature or running query applied to incompatible bag or gear product."
                # Also check prompt text itself for incompatible phrasing (e.g. duffel bag have best cushioning)
                for bag_word in ("duffel bag", "training duffel", "backpack", "gym bag"):
                    if bag_word in lowered and any(f in lowered for f in ("cushioning", "arch support", "shock absorption", "high mileage", "long distance")):
                        return False, f"Category mismatch: footwear feature query combined with bag product '{bag_word}'."
                for app_word in ("crew-neck", "button-up shirt", "t-shirt", "oversized top", "tracksuit"):
                    if app_word in lowered and any(f in lowered for f in ("cushioning", "arch support", "long distance runs", "high mileage")):
                        return False, f"Category mismatch: footwear feature query combined with apparel product '{app_word}'."

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
