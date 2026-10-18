"""Stage C: Candidate Generation for Engine 2 Prompt Intelligence.
Provides pluggable generators: DeterministicGenerator and optional GeminiGenerator.
"""
import abc
import json
import logging
import re
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


GERUND_TO_BASE = {
    "switching": "switch",
    "automating": "automate",
    "managing": "manage",
    "tracking": "track",
    "building": "build",
    "scaling": "scale",
    "deploying": "deploy",
    "optimizing": "optimize",
    "collaborating": "collaborate",
    "migrating": "migrate",
    "monitoring": "monitor",
    "streamlining": "streamline",
    "evaluating": "evaluate",
    "integrating": "integrate",
    "organizing": "organize",
    "coordinating": "coordinate",
}

BASE_TO_GERUND = {v: k for k, v in GERUND_TO_BASE.items()}


def normalize_use_case_forms(phrase: str) -> tuple:
    """Returns (base_form, gerund_form) for grammar-aware slot substitution (DEF-E2-01)."""
    p = phrase.strip()
    if p.lower().startswith("to "):
        p = p[3:].strip()
    words = p.split()
    if not words:
        return phrase, phrase
    first_lower = words[0].lower()
    rest = " ".join(words[1:]) if len(words) > 1 else ""

    if first_lower in GERUND_TO_BASE:
        base = GERUND_TO_BASE[first_lower] + (f" {rest}" if rest else "")
        gerund = p
    elif first_lower in BASE_TO_GERUND:
        base = p
        gerund = BASE_TO_GERUND[first_lower] + (f" {rest}" if rest else "")
    elif first_lower.endswith("ing"):
        base = first_lower[:-3] + (f" {rest}" if rest else "")
        gerund = p
    else:
        base = p
        gerund = (first_lower + "ing") + (f" {rest}" if rest else "")

    return base, gerund


def transform_article_title_to_question(title: str, category: str = "products") -> str:
    """
    Transforms an article title, buying guide, or blog topic into a natural conversational
    question an ordinary person would ask an AI assistant.
    """
    clean = re.sub(r"[\u200b\u200c\u200d\ufeff\xa0]", " ", title).strip()
    clean = re.sub(r"\s+", " ", clean).strip()
    # Strip common editorial subtitle suffixes like ': What you need to know', '- Complete Guide'
    clean = re.sub(r"\s*:\s*(?:what\s+you\s+need\s+to\s+know|a\s+complete\s+guide|everything\s+you\s+need\s+to\s+know|tips\s+and\s+tricks|buyer'?s?\s+guide|explained|full\s+guide).*$", "", clean, flags=re.IGNORECASE)
    clean = re.sub(r"\s*[-|–]\s*(?:a\s+)?(?:complete\s+)?guide.*$", "", clean, flags=re.IGNORECASE)

    # Rule 1: "Best X for Y" (e.g. "Best running shoes for summer")
    m_best = re.match(r"^(?:the\s+)?best\s+(.+?)\s+for\s+(.+)$", clean, re.IGNORECASE)
    if m_best:
        item = m_best.group(1).strip()
        purpose = m_best.group(2).strip().rstrip(".?")
        if purpose.lower() in ("summer", "hot weather"):
            return f"What {item} would you recommend for hot weather?"
        elif purpose.lower() in ("winter", "cold weather", "snow"):
            return f"What {item} would you recommend for cold weather?"
        return f"What {item} would you recommend for {purpose}?"

    # Rule 2: "X vs Y" (e.g. "Road running vs trail running")
    m_vs = re.match(r"^(.+?)\s+(?:vs\.?|versus)\s+(.+)$", clean, re.IGNORECASE)
    if m_vs:
        left = m_vs.group(1).strip()
        right = m_vs.group(2).strip().rstrip(".?")
        return f"What is the difference between {left} and {right}?"

    # Rule 3: "How to choose a running shoe" / "How to choose shoes for marathon training"
    m_choose = re.match(r"^how\s+to\s+(?:choose|pick|select)\s+(?:a\s+|an\s+|the\s+)?(.+)$", clean, re.IGNORECASE)
    if m_choose:
        target = m_choose.group(1).strip().rstrip(".?")
        return f"What features matter most when choosing {target}?"

    # Rule 4: "Choosing the right X for Y"
    m_choosing = re.match(r"^(?:choosing|picking|finding)\s+the\s+(?:right|best)\s+(.+?)(?:\s+for\s+(.+))?$", clean, re.IGNORECASE)
    if m_choosing:
        item = m_choosing.group(1).strip()
        purpose = m_choosing.group(2).strip().rstrip(".?") if m_choosing.group(2) else ""
        if purpose:
            return f"What should I look for in a pair of {item} for {purpose}?"
        return f"What should I look for when choosing {item}?"

    # Rule 5: "What to look for in X"
    m_look = re.match(r"^what\s+to\s+look\s+for\s+in\s+(.+)$", clean, re.IGNORECASE)
    if m_look:
        target = m_look.group(1).strip().rstrip(".?")
        return f"What should I look for in {target}?"

    # Rule 6: If already framed as a natural question
    if any(clean.lower().startswith(w) for w in ("what", "which", "how", "are", "is", "should", "can")):
        return clean.rstrip(".") + "?"

    return f"What should someone consider regarding {clean.rstrip('.')}?"


class DeterministicGenerator(PromptGeneratorProvider):
    """
    Deterministic prompt generation engine.
    Produces highly tailored, natural-language prompts grounded strictly in
    the brand's verified facts, products, audiences, and capabilities without external LLMs.
    """

    ARCHETYPE_TEMPLATES: Dict[str, Dict[str, List[str]]] = {
        "footwear_apparel": {
            "discovery": [
                "What are some good {category} for someone who runs a few times a week?",
                "Which {category} are considered the best all-around options right now?",
                "What are the most popular {category} for daily training?",
                "Which brands make durable {category} without charging a premium?",
                "What should a beginner look for in a pair of {category}?",
                "What are the leading options for {category} this season?",
            ],
            "recommendations": [
                "Which {category} offer the best value for money right now?",
                "What should I look for if I want comfortable {category} for everyday training?",
                "Which {category} are worth considering for long distance runs?",
                "What {category} would you recommend for daily walking and running?",
                "Which {category} have the best cushioning for high mileage?",
            ],
            "product_evaluation": [
                "How do I choose between cushioned and lightweight {category}?",
                "What features matter most when choosing {category} for everyday training?",
                "What should I consider when replacing my old {category}?",
                "How do I know if I need stability or neutral {category}?",
                "What criteria should runners evaluate when picking {category}?",
            ],
            "comparisons": [
                "What's the difference between road {category} and trail {category}?",
                "How do top {category} brands compare for arch support and durability?",
                "Are expensive {category} actually worth it for a beginner?",
                "Which {category} provide better shock absorption for road running?",
                "What is the difference between daily trainers and racing {category}?",
            ],
            "audience_specific": [
                "I'm training for my first half marathon. What should I look for in a pair of {category}?",
                "What are the best {category} for {audience}?",
                "Which {category} work best for runners with wider feet?",
                "What footwear do running coaches recommend for {audience}?",
                "What {category} offer the best support for flat feet?",
            ],
            "use_cases": [
                "What footwear is best suited for {use_case}?",
                "What {category} would you recommend for {use_case}?",
                "What are the best shoe options for someone focusing on {use_case}?",
                "How do I pick the right shoes for {use_case}?",
            ],
            "pricing_value": [
                "Which {category} provide the best durability for the price?",
                "Are premium carbon-plated {category} worth the cost for non-elite runners?",
                "What is a reasonable price to pay for a quality pair of {category}?",
                "Which brands offer affordable {category} that last over 400 miles?",
            ],
            "brand_research": [
                "What should someone know before buying their first pair of {category}?",
                "How often should you replace your {category} based on mileage?",
                "What are the key differences between training shoes and racing shoes?",
                "What innovations in shoe foam and cushioning are worth paying for?",
            ],
        },
        "developer_infrastructure": {
            "discovery": [
                "What are the best modern platforms for {category}?",
                "Which platforms are leading the market in {category}?",
                "How do modern engineering teams approach {category}?",
                "What solutions exist for managing {category} at scale?",
                "What are the top open developer tools for {category}?",
            ],
            "recommendations": [
                "Which platform would you recommend for {category}?",
                "What infrastructure should growing engineering teams use for {category}?",
                "Which tools offer the most reliable capabilities for {category}?",
                "What are the top recommended solutions for {category}?",
                "What is the highest-rated platform for {category}?",
            ],
            "product_evaluation": [
                "What should teams evaluate when choosing a solution for {category}?",
                "What architectural capabilities matter most in {category} platforms?",
                "What are the key trade-offs between different {category} providers?",
                "What criteria should engineers evaluate when comparing {category} tools?",
            ],
            "comparisons": [
                "What are the leading alternatives and competitors in {category}?",
                "How do the top solutions in {category} compare on latency and reliability?",
                "Which providers offer the strongest alternative to traditional {category} setups?",
                "What are the main architectural differences between {category} platforms?",
            ],
            "audience_specific": [
                "What is the best {category} solution for {audience}?",
                "Which {category} tools do {audience} recommend for production?",
                "How do {audience} evaluate different {category} platforms?",
                "Top {category} infrastructure designed for {audience}?",
            ],
            "use_cases": [
                "What solutions are best suited for {use_case}?",
                "Which platforms help teams handle {use_case}?",
                "What architecture enables engineering teams to {use_case}?",
            ],
            "pricing_value": [
                "Which {category} platforms offer transparent usage-based pricing?",
                "What should teams expect to budget for a modern {category} platform?",
                "Which {category} tools offer the best performance per dollar?",
            ],
            "brand_research": [
                "What key differentiators separate the best platforms in {category}?",
                "What capabilities distinguish leading {category} platforms from standard tools?",
                "What architectural patterns are emerging in {category}?",
            ],
        },
        "enterprise_saas": {
            "discovery": [
                "What are the best modern software solutions for {category}?",
                "Which platforms are leading the market in {category}?",
                "How do modern organizations approach {category}?",
                "What solutions exist for streamlining {category}?",
            ],
            "recommendations": [
                "Which software would you recommend for {category}?",
                "What platform should growing organizations use for {category}?",
                "What are the top recommended solutions for {category}?",
            ],
            "product_evaluation": [
                "What criteria should teams evaluate when choosing a {category} solution?",
                "What features matter most when evaluating {category} software?",
                "What are the pros and cons of different {category} systems?",
            ],
            "comparisons": [
                "What are the leading alternatives and competitors in {category}?",
                "How do top {category} platforms compare on ease of use and security?",
                "Which solutions offer the strongest alternative to traditional {category} software?",
            ],
            "audience_specific": [
                "What is the best {category} platform for {audience}?",
                "Which {category} tools do {audience} recommend?",
                "Top {category} systems designed for {audience}?",
            ],
            "use_cases": [
                "What software is best suited for {use_case}?",
                "Which platforms help teams manage {use_case}?",
                "What solutions enable teams to {use_case}?",
            ],
            "pricing_value": [
                "What should organizations expect to pay for modern {category} software?",
                "Which {category} platforms offer transparent pricing and strong ROI?",
                "What is the typical pricing model for {category} software?",
            ],
            "brand_research": [
                "What key capabilities distinguish leading {category} platforms?",
                "What features should enterprise buyers look for in {category}?",
                "What trends are shaping the future of {category}?",
            ],
        },
        "creative_tools": {
            "discovery": [
                "What are the best tools for {category} right now?",
                "Top platforms for {category} in 2026?",
                "What creative solutions exist for {category}?",
            ],
            "recommendations": [
                "Which creative platform would you recommend for {category}?",
                "What are the top recommended tools for {category}?",
            ],
            "product_evaluation": [
                "What features matter most when choosing a {category} tool?",
                "What are the pros and cons of modern {category} platforms?",
            ],
            "comparisons": [
                "What are the leading alternatives in {category}?",
                "How do top {category} tools compare in rendering speed and quality?",
            ],
            "audience_specific": [
                "What is the best {category} tool for {audience}?",
                "Which {category} software do {audience} recommend?",
            ],
            "use_cases": [
                "What tools are best suited for {use_case}?",
                "How do creators handle {use_case}?",
            ],
            "pricing_value": [
                "Which {category} tools offer flexible or creator-friendly pricing?",
                "What is the most cost-effective solution for {category}?",
            ],
            "brand_research": [
                "What emerging features are reshaping {category}?",
                "What distinguishes high-end {category} platforms from entry-level tools?",
            ],
        },
        "general": {
            "discovery": [
                "What are the most recommended options for {category}?",
                "Which providers are leading the market in {category}?",
                "What solutions exist for {category}?",
                "What are the top choices for {category} right now?",
            ],
            "recommendations": [
                "Which option would you recommend for {category}?",
                "What should someone look for when seeking a {category} solution?",
                "What are the highest-rated providers for {category}?",
            ],
            "product_evaluation": [
                "What features matter most when evaluating {category}?",
                "What criteria should buyers look for when choosing {category}?",
                "What are the advantages and drawbacks of different {category} options?",
            ],
            "comparisons": [
                "What are the leading alternatives and competitors in {category}?",
                "How do top providers in {category} compare on quality and value?",
                "What are the key differences between leading {category} brands?",
            ],
            "audience_specific": [
                "What is the best {category} choice for {audience}?",
                "Which {category} options do {audience} recommend?",
                "What solutions are specifically tailored for {audience}?",
            ],
            "use_cases": [
                "What options are best suited for {use_case}?",
                "What would you recommend for someone needing {use_case}?",
                "Which providers specialize in {use_case}?",
            ],
            "pricing_value": [
                "Which {category} options offer the best value for money?",
                "What should customers expect to pay for quality {category}?",
                "Which providers offer transparent and fair pricing in {category}?",
            ],
            "brand_research": [
                "What key factors separate the best options in {category}?",
                "What should buyers consider before committing to a {category} provider?",
                "What recent innovations are improving {category}?",
            ],
        },
    }

    # Backward compatibility alias
    TEMPLATES = ARCHETYPE_TEMPLATES["general"]

    async def generate(
        self, profile: NormalizedBrandProfile, plan: CoveragePlan
    ) -> List[GeneratedPromptCandidate]:
        candidates: List[GeneratedPromptCandidate] = []
        archetype = profile.get_domain_archetype()
        archetype_dict = self.ARCHETYPE_TEMPLATES.get(archetype, self.ARCHETYPE_TEMPLATES["general"])

        category = profile.get_primary_category() or "solutions in this field"
        clean_category = profile.clean_text_of_brand(category) or "solutions in this field"
        clean_subcategories = profile.get_clean_subcategories()
        market_name = profile.target_market or "global markets"

        clean_products = profile.get_clean_products()
        clean_audiences = profile.get_clean_audiences()
        clean_use_cases = profile.get_clean_use_cases()
        clean_diffs = profile.get_clean_differentiators()

        # Index templates by category and archetype
        for idx, slot in enumerate(plan.slots):
            cat = slot.category
            slot_archetype = slot.archetype or archetype
            slot_templates = self.ARCHETYPE_TEMPLATES.get(slot_archetype, archetype_dict).get(cat, archetype_dict.get("discovery", []))
            template = slot_templates[idx % len(slot_templates)] if slot_templates else "What are the best options for {category}?"

            # Context parameters cleaned of any brand mentions
            raw_product = slot.dimension_value if slot.target_dimension in ("product", "competitors") else (
                clean_products[0] if clean_products else (clean_subcategories[0] if clean_subcategories else clean_category)
            )
            product_val = profile.clean_text_of_brand(str(raw_product)) if raw_product else clean_category
            if not product_val:
                product_val = clean_category

            raw_audience = slot.dimension_value if slot.target_dimension == "audience" else (
                clean_audiences[0] if clean_audiences else ("runners" if archetype == "footwear_apparel" else "teams")
            )
            audience_val = profile.clean_text_of_brand(str(raw_audience)) if raw_audience else ("runners" if archetype == "footwear_apparel" else "teams")
            if not audience_val:
                audience_val = "runners" if archetype == "footwear_apparel" else "teams"

            raw_use_case = slot.dimension_value if slot.target_dimension == "use_case" else (
                clean_use_cases[0] if clean_use_cases else f"evaluating {clean_category}"
            )
            use_case_val = profile.clean_text_of_brand(str(raw_use_case)) if raw_use_case else f"evaluating {clean_category}"
            if use_case_val.lower().startswith("to "):
                use_case_val = use_case_val[3:].strip()
            if not use_case_val:
                use_case_val = f"evaluating {clean_category}"
            use_case_base, use_case_gerund = normalize_use_case_forms(use_case_val)

            raw_pricing = slot.dimension_value if slot.target_dimension == "pricing" else (
                profile.pricing_models[0] if profile.pricing_models else "standard pricing"
            )
            pricing_val = profile.clean_text_of_brand(str(raw_pricing)) if raw_pricing else "transparent pricing"
            if not pricing_val:
                pricing_val = "transparent pricing"

            raw_diff = slot.dimension_value if slot.target_dimension == "differentiator" else (
                clean_diffs[0] if clean_diffs else "advanced capabilities"
            )
            diff_val = profile.clean_text_of_brand(str(raw_diff)) if raw_diff else "advanced capabilities"
            if not diff_val:
                diff_val = "advanced capabilities"

            # Check if this slot is an article topic inspiration
            if slot.is_article_inspired and slot.dimension_value:
                prompt_text = transform_article_title_to_question(slot.dimension_value, clean_category)
            else:
                # Format template safely without brand leakage
                prompt_cat = clean_subcategories[idx % len(clean_subcategories)] if clean_subcategories else clean_category
                prompt_text = template.format(
                    brand=prompt_cat,
                    category=prompt_cat,
                    industry=clean_category,
                    market=market_name,
                    product=product_val,
                    capability=product_val,
                    audience=audience_val,
                    use_case=use_case_gerund,
                    use_case_base=use_case_base,
                    use_case_gerund=use_case_gerund,
                    pricing=pricing_val,
                    differentiator=diff_val,
                )

            # Final sanity clean to guarantee zero brand mentions
            prompt_text = profile.clean_text_of_brand(prompt_text)
            if not prompt_text.endswith("?"):
                prompt_text = prompt_text.rstrip(".") + "?"

            # Resolve exact traceability for target_product_service and target_audience
            matched_raw_product = None
            if slot.category in ("product_evaluation", "comparisons"):
                if raw_product in profile.products_and_services:
                    matched_raw_product = raw_product
                else:
                    for p in profile.products_and_services:
                        if raw_product and (raw_product.lower() in p.lower() or profile.clean_text_of_brand(p).lower() == raw_product.lower()):
                            matched_raw_product = p
                            break
                    if not matched_raw_product and profile.products_and_services:
                        matched_raw_product = profile.products_and_services[0]

            matched_raw_audience = None
            if slot.category == "audience_specific":
                if raw_audience in profile.target_audiences:
                    matched_raw_audience = raw_audience
                else:
                    for a in profile.target_audiences:
                        if raw_audience and (raw_audience.lower() in a.lower() or profile.clean_text_of_brand(a).lower() == raw_audience.lower()):
                            matched_raw_audience = a
                            break
                    if not matched_raw_audience and profile.target_audiences:
                        matched_raw_audience = profile.target_audiences[0]

            # Build candidate with provenance references
            cand = GeneratedPromptCandidate(
                text=prompt_text,
                category=slot.category,
                intent=slot.intent,
                buying_stage=slot.buying_stage,
                target_audience=matched_raw_audience if matched_raw_audience else (audience_val if slot.category == "audience_specific" else None),
                target_product_service=matched_raw_product if matched_raw_product else (product_val if slot.category in ("product_evaluation", "comparisons") else None),
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
    strict unbranded visibility rules, and safe fallback to DeterministicGenerator on errors.
    """

    def __init__(self, fallback: Optional[PromptGeneratorProvider] = None):
        self.fallback = fallback or DeterministicGenerator()

    async def generate(
        self, profile: NormalizedBrandProfile, plan: CoveragePlan
    ) -> List[GeneratedPromptCandidate]:
        if not settings.LLM_API_KEY:
            logger.info("LLM_API_KEY missing. Falling back to DeterministicGenerator.")
            return await self.fallback.generate(profile, plan)

        category = profile.get_primary_category() or "digital solutions"
        clean_category = profile.clean_text_of_brand(category) or "solutions in this domain"

        # Build prompt payload for Gemini
        system_instructions = (
            "You are an expert AI visibility research engineer. "
            "Generate REALISTIC, ORGANIC, UNBRANDED search engine and AI assistant prompts that prospective buyers "
            "and users ask when researching, evaluating, or comparing solutions in the specified industry domain.\n\n"
            "STRICT RULES:\n"
            "1. NEVER mention the brand name, domain, URL, or proprietary brand product names in ANY prompt.\n"
            "2. Prompts must be completely unbranded industry-level queries to test whether the brand appears naturally in AI answers.\n"
            "3. Ground prompts in the supplied industry, target audiences, use cases, and capabilities.\n"
            "4. Return questions that real users actually ask (e.g., 'What are the best tools for...', 'Which platforms offer...')."
        )

        user_content = {
            "industry_category": clean_category,
            "target_market": profile.target_market,
            "products_and_capabilities": profile.get_clean_products(),
            "target_audiences": profile.get_clean_audiences(),
            "use_cases": profile.get_clean_use_cases(),
            "pricing_models": profile.pricing_models,
            "differentiators": profile.get_clean_differentiators(),
            "forbidden_tokens": profile.get_forbidden_brand_tokens(),
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
                        {"text": f"Generate organic unbranded prompts according to this profile and slot specification: {json.dumps(user_content)}"},
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
                forbidden_tokens = profile.get_forbidden_brand_tokens()

                for idx, p in enumerate(parsed_prompts):
                    slot = plan.slots[idx] if idx < len(plan.slots) else None
                    fact_ids = slot.source_fact_ids if slot else []
                    evidence = [slot.evidence_snippet] if (slot and slot.evidence_snippet) else []

                    raw_text = p.get("text", "").strip()
                    clean_text = profile.clean_text_of_brand(raw_text)

                    # Reject candidates that contain forbidden brand tokens
                    if any(t in clean_text.lower() for t in forbidden_tokens):
                        continue

                    cand = GeneratedPromptCandidate(
                        text=clean_text,
                        category=slot.category if slot else p.get("category", "discovery"),
                        intent=slot.intent if slot else p.get("intent", "informational"),
                        buying_stage=slot.buying_stage if slot else p.get("buying_stage", "consideration"),
                        target_audience=slot.dimension_value if (slot and slot.category == "audience_specific") else None,
                        target_product_service=slot.dimension_value if (slot and slot.category in ("product_evaluation", "comparisons")) else None,
                        language=profile.primary_language,
                        provenance_fact_ids=fact_ids,
                        grounding_evidence=evidence,
                        scores={},
                        quality_score=1.0,
                    )
                    if cand.text:
                        candidates.append(cand)

                if len(candidates) >= len(plan.slots) // 2:
                    return candidates

        except Exception as e:
            logger.warning(f"Gemini generation failed: {e}. Falling back to DeterministicGenerator.")

        return await self.fallback.generate(profile, plan)


def get_prompt_generator() -> PromptGeneratorProvider:
    """Factory for selecting the active prompt generator provider."""
    if settings.LLM_ENABLED and settings.LLM_PROVIDER.lower() == "gemini":
        return GeminiGenerator()
    return DeterministicGenerator()
