"""Stage B: Intent and Coverage Planning for Engine 2 Prompt Intelligence."""
import logging
from typing import List, Dict, Optional, Any
from app.prompts.models import NormalizedBrandProfile, CoveragePlan, PlannedPromptSlot
from app.prompts.classifier import CategoryClassifier

logger = logging.getLogger(__name__)


class CoveragePlanner:
    """Creates a balanced, grounded coverage plan based on available profile dimensions and category taxonomy."""

    @staticmethod
    def create_plan(
        profile: NormalizedBrandProfile,
        requested_count: int = 20,
        allowed_categories: Optional[List[str]] = None,
        surplus_ratio: float = 1.0
    ) -> CoveragePlan:
        # 1. First stage: Category Classification
        classification = CategoryClassifier.classify(profile)
        archetype = classification.domain_archetype
        primary_cat = classification.primary_category or profile.get_primary_category()

        if not primary_cat or profile.is_empty:
            raise ValueError(
                "Cannot create coverage plan: brand profile has insufficient evidence (missing industry, category, products, or use cases). "
                "Please complete website profiling first."
            )

        clean_products = profile.get_clean_products()
        clean_subcategories = profile.get_clean_subcategories()
        clean_audiences = profile.get_clean_audiences()
        clean_use_cases = profile.get_clean_use_cases()
        clean_diffs = profile.get_clean_differentiators()
        article_topics = profile.get_article_topics()

        # Identify active subcategories with verified products
        active_subcats = [k for k, v in classification.subcategories.items() if v and k != "general_product"]
        if not active_subcats:
            if archetype in ("footwear_apparel", "sportswear_sporting_goods"):
                active_subcats = ["footwear"]
            elif archetype == "crm_sales":
                active_subcats = ["crm_sales"]
            elif archetype == "marketing_automation":
                active_subcats = ["marketing_automation"]
            elif archetype in ("developer_tools", "saas_software"):
                active_subcats = ["developer_tools"]
            elif archetype == "fintech":
                active_subcats = ["fintech"]
            elif archetype == "healthcare_tech":
                active_subcats = ["healthcare_tech"]
            elif archetype == "ecommerce_retail":
                active_subcats = ["ecommerce_retail"]
            elif archetype in ("services_professional", "professional_services"):
                active_subcats = ["professional_services"]
            elif archetype == "general_business_software":
                active_subcats = ["general_business_software"]
            elif archetype == "uncertain_category":
                active_subcats = ["uncertain_category"]
            else:
                active_subcats = ["general"]

        # Determine active dimensions based on real grounded data
        active_dimensions: List[str] = []
        candidate_categories: List[Dict[str, Any]] = []

        # 1. Discovery (Broad industry/category awareness)
        discovery_values = clean_subcategories if clean_subcategories else [primary_cat]
        candidate_categories.append({
            "category": "discovery",
            "intent": "informational",
            "buying_stage": "awareness",
            "weight": 4,
            "dimension": "industry",
            "values": discovery_values
        })
        active_dimensions.append("discovery")

        # 2. Recommendations (Commercial consideration queries)
        candidate_categories.append({
            "category": "recommendations",
            "intent": "commercial",
            "buying_stage": "consideration",
            "weight": 4,
            "dimension": "category",
            "values": clean_subcategories or [primary_cat]
        })
        active_dimensions.append("recommendations")

        # 3. Product Evaluation (Evaluation criteria and features - only if products exist)
        if clean_products or profile.products_and_services:
            eval_values = clean_products or profile.products_and_services
            candidate_categories.append({
                "category": "product_evaluation",
                "intent": "commercial",
                "buying_stage": "consideration",
                "weight": 4,
                "dimension": "product",
                "values": eval_values
            })
            active_dimensions.append("product_evaluation")

        # 4. Comparisons (Head-to-head or category alternatives)
        comp_values = clean_subcategories or clean_products or [primary_cat]
        candidate_categories.append({
            "category": "comparisons",
            "intent": "comparative",
            "buying_stage": "consideration",
            "weight": 4,
            "dimension": "competitors",
            "values": comp_values
        })
        active_dimensions.append("comparisons")

        # 5. Audience-Specific Needs (Only if audience facts exist)
        if clean_audiences:
            candidate_categories.append({
                "category": "audience_specific",
                "intent": "commercial",
                "buying_stage": "awareness",
                "weight": 3,
                "dimension": "audience",
                "values": clean_audiences
            })
            active_dimensions.append("audience_specific")

        # 6. Use Cases & Problem Discovery (Prioritize article/guide topics if available)
        uc_values = (article_topics + clean_use_cases) if article_topics else (clean_use_cases or [f"evaluating {primary_cat}"])
        candidate_categories.append({
            "category": "use_cases",
            "intent": "informational",
            "buying_stage": "consideration",
            "weight": 4,
            "dimension": "use_case",
            "values": uc_values
        })
        active_dimensions.append("use_cases")

        # 7. Pricing and Value (Only if pricing models exist)
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
        diff_values = clean_diffs or article_topics or clean_subcategories or [primary_cat]
        candidate_categories.append({
            "category": "brand_research",
            "intent": "informational",
            "buying_stage": "decision",
            "weight": 3,
            "dimension": "differentiator",
            "values": diff_values
        })
        active_dimensions.append("brand_research")

        # Filter categories if caller specified allowed_categories
        if allowed_categories:
            allowed_set = set(allowed_categories)
            candidate_categories = [c for c in candidate_categories if c["category"] in allowed_set]

        if not candidate_categories:
            candidate_categories = [{
                "category": "discovery",
                "intent": "informational",
                "buying_stage": "awareness",
                "weight": 1,
                "dimension": "industry",
                "values": [primary_cat]
            }]

        # Surplus planning: plan candidate slots to meet or exceed requested_count
        slots_target = max(requested_count, round(requested_count * surplus_ratio))

        slots: List[PlannedPromptSlot] = []
        total_weight = sum(c["weight"] for c in candidate_categories)
        cat_counts: Dict[str, int] = {}

        for cat_info in candidate_categories:
            quota = max(1, round((cat_info["weight"] / total_weight) * slots_target))
            cat_counts[cat_info["category"]] = quota

        # Adjust total to exactly slots_target
        current_total = sum(cat_counts.values())
        while current_total > slots_target:
            max_cat = max(cat_counts, key=lambda k: cat_counts[k])
            if cat_counts[max_cat] > 1:
                cat_counts[max_cat] -= 1
                current_total -= 1
            else:
                break
        while current_total < slots_target:
            primary_slot_cat = candidate_categories[0]["category"]
            cat_counts[primary_slot_cat] += 1
            current_total += 1

        # Assemble individual slots
        for cat_info in candidate_categories:
            cat_name = cat_info["category"]
            quota = cat_counts.get(cat_name, 1)
            values_list = cat_info["values"]

            for i in range(quota):
                # Assign subcategory cyclically from verified active subcategories
                subcat = active_subcats[i % len(active_subcats)]

                # For product dimension, pick product strictly belonging to this subcategory if available
                subcat_prods = classification.subcategories.get(subcat, [])
                if cat_info["dimension"] in ("product", "competitors") and subcat_prods:
                    val = subcat_prods[(i // len(active_subcats)) % len(subcat_prods)]
                else:
                    val = values_list[i % len(values_list)] if values_list else primary_cat

                matching_fact_ids = []
                evidence_text = None
                relevant_types = {
                    "product": {"product_service", "product_feature"},
                    "competitors": {"product_service", "differentiator"},
                    "audience": {"target_audience"},
                    "use_case": {"use_case"},
                    "pricing": {"pricing"},
                    "differentiator": {"differentiator", "company_description", "business_overview", "industry"},
                    "industry": {"industry", "business_overview", "company_description"},
                    "category": {"industry", "business_overview", "company_description"},
                    "brand": {"industry", "business_overview", "company_description"},
                }.get(cat_info["dimension"], set())

                for f in profile.facts:
                    if f.fact_type not in relevant_types:
                        continue
                    if isinstance(f.fact_value, dict):
                        f_val = (
                            f.fact_value.get("name")
                            or f.fact_value.get("plan_name")
                            or f.fact_value.get("model")
                            or f.fact_value.get("segment")
                            or f.fact_value.get("claim")
                            or f.fact_value.get("title")
                            or f.fact_value.get("description")
                        )
                    else:
                        f_val = f.fact_value
                    f_val_str = str(f_val).lower()
                    if (val and str(val).lower() in f_val_str) or f.fact_type in ("industry", "business_overview", "company_description"):
                        if f.id and f.id not in matching_fact_ids:
                            matching_fact_ids.append(f.id)
                        evidence_text = evidence_text or f.evidence_snippet

                if not matching_fact_ids:
                    for f in profile.facts:
                        if f.fact_type in relevant_types and f.id:
                            matching_fact_ids.append(f.id)
                            evidence_text = evidence_text or f.evidence_snippet
                            break

                is_article = bool(article_topics and val in article_topics)

                slot = PlannedPromptSlot(
                    category=cat_name,
                    intent=cat_info["intent"],
                    buying_stage=cat_info["buying_stage"],
                    subcategory=subcat,
                    target_dimension=cat_info["dimension"],
                    dimension_value=val,
                    source_fact_ids=matching_fact_ids,
                    evidence_snippet=evidence_text,
                    archetype=archetype,
                    is_article_inspired=is_article
                )
                slots.append(slot)

        slots = slots[:slots_target]
        distribution: Dict[str, int] = {}
        for s in slots:
            distribution[s.category] = distribution.get(s.category, 0) + 1

        return CoveragePlan(
            total_slots_requested=requested_count,
            slots=slots,
            category_distribution=distribution,
            active_dimensions=active_dimensions
        )

    @staticmethod
    def create_replenishment_plan(
        profile: NormalizedBrandProfile,
        needed_count: int,
        allowed_categories: Optional[List[str]] = None
    ) -> CoveragePlan:
        """Generates a targeted replenishment plan to fill missing slots."""
        return CoveragePlanner.create_plan(
            profile=profile,
            requested_count=needed_count,
            allowed_categories=allowed_categories,
            surplus_ratio=2.0
        )
