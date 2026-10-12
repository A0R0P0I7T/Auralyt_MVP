"""Stage B: Intent and Coverage Planning for Engine 2 Prompt Intelligence."""
import logging
from typing import List, Dict, Optional, Any
from app.prompts.models import NormalizedBrandProfile, CoveragePlan, PlannedPromptSlot

logger = logging.getLogger(__name__)


class CoveragePlanner:
    """Creates a balanced, grounded coverage plan based on available profile dimensions."""

    @staticmethod
    def create_plan(
        profile: NormalizedBrandProfile,
        requested_count: int = 20,
        allowed_categories: Optional[List[str]] = None
    ) -> CoveragePlan:
        # Determine active dimensions based on real grounded data
        active_dimensions: List[str] = []
        candidate_categories: List[Dict[str, Any]] = []

        # 1. Discovery (Always applicable if industry/business name exists)
        candidate_categories.append({
            "category": "discovery",
            "intent": "informational",
            "buying_stage": "awareness",
            "weight": 3,
            "dimension": "industry",
            "values": [profile.industry] if profile.industry else ["solutions in this domain"]
        })
        active_dimensions.append("discovery")

        # 2. Recommendations
        candidate_categories.append({
            "category": "recommendations",
            "intent": "commercial",
            "buying_stage": "consideration",
            "weight": 3,
            "dimension": "category",
            "values": [profile.industry or profile.business_name]
        })
        active_dimensions.append("recommendations")

        # 3. Product Evaluation (Only if products/services exist)
        if profile.products_and_services:
            candidate_categories.append({
                "category": "product_evaluation",
                "intent": "commercial",
                "buying_stage": "consideration",
                "weight": 4,
                "dimension": "product",
                "values": profile.products_and_services
            })
            active_dimensions.append("product_evaluation")

        # 4. Comparisons (Only if brand has products or differentiators)
        if profile.products_and_services or profile.differentiators:
            candidate_categories.append({
                "category": "comparisons",
                "intent": "comparative",
                "buying_stage": "consideration",
                "weight": 3,
                "dimension": "competitors",
                "values": profile.products_and_services or [profile.business_name]
            })
            active_dimensions.append("comparisons")

        # 5. Audience-Specific Needs (Only if documented target audiences exist)
        if profile.target_audiences:
            candidate_categories.append({
                "category": "audience_specific",
                "intent": "commercial",
                "buying_stage": "awareness",
                "weight": 3,
                "dimension": "audience",
                "values": profile.target_audiences
            })
            active_dimensions.append("audience_specific")

        # 6. Use Cases & Problem Discovery (Only if use cases or FAQs exist)
        if profile.use_cases:
            candidate_categories.append({
                "category": "use_cases",
                "intent": "informational",
                "buying_stage": "consideration",
                "weight": 3,
                "dimension": "use_case",
                "values": profile.use_cases
            })
            active_dimensions.append("use_cases")

        # 7. Pricing and Value (Only if documented pricing models exist)
        if profile.pricing_models:
            candidate_categories.append({
                "category": "pricing_value",
                "intent": "transactional",
                "buying_stage": "decision",
                "weight": 2,
                "dimension": "pricing",
                "values": profile.pricing_models
            })
            active_dimensions.append("pricing_value")

        # 8. Brand Research & Differentiators
        if profile.differentiators or profile.tagline_or_description:
            candidate_categories.append({
                "category": "brand_research",
                "intent": "informational",
                "buying_stage": "decision",
                "weight": 3,
                "dimension": "differentiator",
                "values": profile.differentiators or [profile.business_name]
            })
            active_dimensions.append("brand_research")

        # Filter categories if caller specified allowed_categories
        if allowed_categories:
            allowed_set = set(allowed_categories)
            candidate_categories = [c for c in candidate_categories if c["category"] in allowed_set]

        if not candidate_categories:
            # Fallback minimal slot
            candidate_categories = [{
                "category": "discovery",
                "intent": "informational",
                "buying_stage": "awareness",
                "weight": 1,
                "dimension": "brand",
                "values": [profile.business_name]
            }]

        # Generate slots based on weights and quotas
        slots: List[PlannedPromptSlot] = []
        total_weight = sum(c["weight"] for c in candidate_categories)
        cat_counts: Dict[str, int] = {}

        # Round 1: Proportional distribution
        for cat_info in candidate_categories:
            quota = max(1, round((cat_info["weight"] / total_weight) * requested_count))
            cat_counts[cat_info["category"]] = quota

        # Adjust total to exactly requested_count
        current_total = sum(cat_counts.values())
        diff = requested_count - current_total
        if diff != 0:
            primary_cat = candidate_categories[0]["category"]
            cat_counts[primary_cat] = max(1, cat_counts[primary_cat] + diff)

        # Assemble individual slots
        for cat_info in candidate_categories:
            cat_name = cat_info["category"]
            quota = cat_counts.get(cat_name, 1)
            values_list = cat_info["values"]

            for i in range(quota):
                # Find matching fact IDs for provenance
                matching_fact_ids = []
                evidence_text = None
                relevant_types = {
                    "product": {"product_service", "product_feature"},
                    "audience": {"target_audience"},
                    "use_case": {"use_case"},
                    "pricing": {"pricing"},
                    "differentiator": {"differentiator", "company_description"},
                    "industry": {"industry"},
                    "category": {"industry", "business_name"},
                    "brand": {"business_name", "company_description"},
                }.get(cat_info["dimension"], set())
                grounded_values = set()
                if relevant_types:
                    for fact in profile.facts:
                        if fact.fact_type not in relevant_types:
                            continue
                        if isinstance(fact.fact_value, dict):
                            fact_value = (
                                fact.fact_value.get("name")
                                or fact.fact_value.get("plan_name")
                                or fact.fact_value.get("model")
                                or fact.fact_value.get("segment")
                                or fact.fact_value.get("claim")
                                or fact.fact_value.get("title")
                            )
                        else:
                            fact_value = fact.fact_value
                        grounded_values.add(str(fact_value).lower())
                if grounded_values:
                    values_list = [
                        value for value in values_list
                        if str(value).lower() in grounded_values
                    ] or values_list
                val = values_list[i % len(values_list)] if values_list else None
                for f in profile.facts:
                    if isinstance(f.fact_value, dict):
                        f_val = (
                            f.fact_value.get("name")
                            or f.fact_value.get("plan_name")
                            or f.fact_value.get("model")
                            or f.fact_value.get("segment")
                            or f.fact_value.get("claim")
                            or f.fact_value.get("title")
                        )
                    else:
                        f_val = f.fact_value
                    f_val_str = str(f_val).lower()
                    if f.fact_type in relevant_types and val and str(val).lower() in f_val_str:
                        if f.id:
                            matching_fact_ids.append(f.id)
                        evidence_text = evidence_text or f.evidence_snippet

                slot = PlannedPromptSlot(
                    category=cat_name,
                    intent=cat_info["intent"],
                    buying_stage=cat_info["buying_stage"],
                    target_dimension=cat_info["dimension"],
                    dimension_value=val,
                    source_fact_ids=matching_fact_ids,
                    evidence_snippet=evidence_text
                )
                slots.append(slot)

        # Re-verify total count
        if len(slots) > requested_count:
            slots = slots[:requested_count]

        distribution: Dict[str, int] = {}
        for s in slots:
            distribution[s.category] = distribution.get(s.category, 0) + 1

        return CoveragePlan(
            total_slots_requested=requested_count,
            slots=slots,
            category_distribution=distribution,
            active_dimensions=active_dimensions
        )
