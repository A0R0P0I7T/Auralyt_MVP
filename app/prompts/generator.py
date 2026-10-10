"""Stage C: Candidate Generation for Engine 2 Prompt Intelligence.
Provides pluggable generators: DeterministicGenerator and optional GeminiGenerator.
"""
import abc
import json
import logging
from typing import List, Dict, Any, Optional
import httpx

from app.core.config import settings
from app.prompts.models import (
    NormalizedBrandProfile,
    CoveragePlan,
    PlannedPromptSlot,
    GeneratedPromptCandidate,
)

logger = logging.getLogger(__name__)


class PromptGeneratorProvider(abc.ABC):
    """Abstract base class for prompt generation providers."""

    @abc.abstractmethod
    async def generate(
        self, profile: NormalizedBrandProfile, plan: CoveragePlan
    ) -> List[GeneratedPromptCandidate]:
        pass


class DeterministicGenerator(PromptGeneratorProvider):
    """
    Deterministic prompt generation engine.
    Produces highly tailored, natural-language prompts grounded strictly in
    the brand's verified facts, products, audiences, and capabilities without external LLMs.
    """

    TEMPLATES: Dict[str, List[str]] = {
        "discovery": [
            "What are the best tools for {industry}?",
            "Top platforms for {industry} in {market}?",
            "How do modern teams approach {industry}?",
            "What solutions exist for managing {industry}?",
            "Best modern platforms for {industry} in 2026?",
        ],
        "recommendations": [
            "Which platform would you recommend for {industry}?",
            "Is {brand} a recommended platform for {industry}?",
            "What software should growing businesses use for {industry}?",
            "Which tool offers the best capabilities for {industry}?",
        ],
        "product_evaluation": [
            "What should I consider before choosing {product}?",
            "How does {brand}'s {product} work?",
            "What are the core capabilities of {product}?",
            "Is {brand}'s {product} suitable for enterprise use?",
            "What are the pros and cons of {brand} {product}?",
        ],
        "comparisons": [
            "How does {brand} compare with other {industry} alternatives?",
            "What are the main competitors to {brand} for {product}?",
            "What makes {brand} different from legacy {industry} tools?",
            "How does {brand} stack up against leading solutions in {industry}?",
        ],
        "audience_specific": [
            "What is the best {industry} solution for {audience}?",
            "Why do {audience} choose {brand}?",
            "How does {brand} address the specific needs of {audience}?",
            "Is {brand} tailored for {audience}?",
        ],
        "use_cases": [
            "Which tools can help a business accomplish {use_case}?",
            "Can {brand} be used for {use_case}?",
            "How do teams implement {use_case} using {brand}?",
            "Best practices for {use_case} with {brand}?",
        ],
        "pricing_value": [
            "What are the most cost-effective options for {industry}?",
            "How is {brand} priced ({pricing})?",
            "Is {brand} cost-effective for growing teams?",
            "What is the total cost of ownership for {brand}?",
        ],
        "brand_research": [
            "What makes {brand} unique in the {industry} market?",
            "What are the key differentiators of {brand} ({differentiator})?",
            "What is {brand}'s core technology and approach?",
            "What do industry analysts say about {brand}?",
        ],
    }

    async def generate(
        self, profile: NormalizedBrandProfile, plan: CoveragePlan
    ) -> List[GeneratedPromptCandidate]:
        candidates: List[GeneratedPromptCandidate] = []
        brand_name = profile.business_name
        industry_name = profile.industry or "digital solutions"
        market_name = profile.target_market or "global markets"

        # Index templates by category
        for idx, slot in enumerate(plan.slots):
            cat = slot.category
            templates = self.TEMPLATES.get(cat, self.TEMPLATES["discovery"])
            template = templates[idx % len(templates)]

            # Context parameters
            product_val = slot.dimension_value if slot.target_dimension == "product" else (
                profile.products_and_services[0] if profile.products_and_services else "its core product"
            )
            audience_val = slot.dimension_value if slot.target_dimension == "audience" else (
                profile.target_audiences[0] if profile.target_audiences else "teams"
            )
            use_case_val = slot.dimension_value if slot.target_dimension == "use_case" else (
                profile.use_cases[0] if profile.use_cases else "business operations"
            )
            pricing_val = slot.dimension_value if slot.target_dimension == "pricing" else (
                profile.pricing_models[0] if profile.pricing_models else "standard pricing"
            )
            diff_val = slot.dimension_value if slot.target_dimension == "differentiator" else (
                profile.differentiators[0] if profile.differentiators else "advanced capabilities"
            )

            # Format template safely
            prompt_text = template.format(
                brand=brand_name,
                industry=industry_name,
                market=market_name,
                product=product_val,
                audience=audience_val,
                use_case=use_case_val,
                pricing=pricing_val,
                differentiator=diff_val,
            )

            # Build candidate with provenance references
            cand = GeneratedPromptCandidate(
                text=prompt_text,
                category=slot.category,
                intent=slot.intent,
                buying_stage=slot.buying_stage,
                target_audience=audience_val if slot.category == "audience_specific" else None,
                target_product_service=product_val if slot.category in ("product_evaluation", "comparisons") else None,
                language=profile.primary_language,
                provenance_fact_ids=slot.source_fact_ids,
                grounding_evidence=[slot.evidence_snippet] if slot.evidence_snippet else [],
                scores={},
                quality_score=1.0,
            )
            candidates.append(cand)

        return candidates


class GeminiGenerator(PromptGeneratorProvider):
    """
    LLM generation provider using Google Gemini API with structured JSON output,
    bounded token limits, and safe fallback to DeterministicGenerator on errors.
    """

    def __init__(self, fallback: Optional[PromptGeneratorProvider] = None):
        self.fallback = fallback or DeterministicGenerator()

    async def generate(
        self, profile: NormalizedBrandProfile, plan: CoveragePlan
    ) -> List[GeneratedPromptCandidate]:
        if not settings.LLM_API_KEY:
            logger.info("LLM_API_KEY missing. Falling back to DeterministicGenerator.")
            return await self.fallback.generate(profile, plan)

        # Build prompt payload for Gemini
        system_instructions = (
            "You are an expert AI visibility research engineer. "
            "Generate realistic, natural search engine and AI assistant prompts that users ask "
            "when researching, evaluating, or comparing products in the specified brand's domain. "
            "STRICT GROUNDING: Only use documented products, use cases, and capabilities from the profile. "
            "Never hallucinate features, competitors, or pricing tiers not present in the profile."
        )

        user_content = {
            "brand_name": profile.business_name,
            "domain": profile.domain,
            "industry": profile.industry,
            "products": profile.products_and_services,
            "target_audiences": profile.target_audiences,
            "use_cases": profile.use_cases,
            "pricing_models": profile.pricing_models,
            "differentiators": profile.differentiators,
            "required_slots": [
                {"category": s.category, "intent": s.intent, "buying_stage": s.buying_stage, "dimension": s.dimension_value}
                for s in plan.slots
            ]
        }

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{settings.LLM_MODEL}:generateContent?key={settings.LLM_API_KEY}"
        headers = {"Content-Type": "application/json"}
        payload = {
            "contents": [
                {
                    "parts": [
                        {"text": system_instructions},
                        {"text": f"Generate prompts according to this profile and slot specification: {json.dumps(user_content)}"},
                        {"text": "Return JSON array of objects with keys: 'text', 'category', 'intent', 'buying_stage'."}
                    ]
                }
            ],
            "generationConfig": {
                "responseMimeType": "application/json",
                "temperature": 0.3,
                "maxOutputTokens": 2048,
            }
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                res = await client.post(url, json=payload, headers=headers)
                if res.status_code != 200:
                    logger.warning(f"Gemini API returned {res.status_code}. Using fallback generator.")
                    return await self.fallback.generate(profile, plan)

                data = res.json()
                content_text = data["candidates"][0]["content"]["parts"][0]["text"]
                parsed_prompts = json.loads(content_text)

                candidates: List[GeneratedPromptCandidate] = []
                for p in parsed_prompts:
                    cand = GeneratedPromptCandidate(
                        text=p.get("text", "").strip(),
                        category=p.get("category", "discovery"),
                        intent=p.get("intent", "informational"),
                        buying_stage=p.get("buying_stage", "consideration"),
                        language=profile.primary_language,
                        provenance_fact_ids=[],
                        grounding_evidence=[],
                        scores={},
                        quality_score=1.0,
                    )
                    if cand.text:
                        candidates.append(cand)

                if candidates:
                    return candidates

        except Exception as e:
            logger.warning(f"Gemini generation failed: {e}. Falling back to DeterministicGenerator.")

        return await self.fallback.generate(profile, plan)


def get_prompt_generator() -> PromptGeneratorProvider:
    """Factory for selecting the active prompt generator provider."""
    if settings.LLM_ENABLED and settings.LLM_PROVIDER.lower() == "gemini":
        return GeminiGenerator()
    return DeterministicGenerator()
