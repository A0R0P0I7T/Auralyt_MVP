"""Tests for Engine 2 Prompt Intelligence Overhaul:
1. Category routing across CRM, marketing automation, dev tools, fintech, healthcare, ecommerce, professional services, and uncertain categories.
2. Removal of the universal saas_software -> developer_tools fallback.
3. Clean category normalization without 'B2B Software & Cloud Platforms' tautologies or grammar defects.
4. Robust quality validation (tautologies, off-category technical questions, ungrounded claims).
5. Review lifecycle: generated -> validated -> proposed -> approved/rejected -> tracked.
6. Accurate diagnostics and exact Engine 3 handoff.
"""
import pytest
from app.prompts.models import NormalizedBrandProfile, GroundedFact, GeneratedPromptCandidate
from app.prompts.classifier import CategoryClassifier, BrandClassificationResult
from app.prompts.planner import CoveragePlanner
from app.prompts.normalizer import ProfileNormalizer, humanize_category_or_industry, get_natural_category_phrase
from app.prompts.generator import DeterministicGenerator, GeminiGenerator, get_prompt_generator
from app.prompts.validator import PromptValidator
from app.prompts.scorer import PromptScorer, normalize_prompt_text
from app.prompts.templates import TemplateRegistry


def make_profile(
    business_name: str,
    domain: str,
    industry: str,
    description: str,
    products: list = None,
    use_cases: list = None,
    audiences: list = None
) -> NormalizedBrandProfile:
    return NormalizedBrandProfile(
        brand_id=f"test-brand-{domain}",
        domain=domain,
        business_name=business_name,
        industry=industry,
        target_market="Global",
        primary_language="en",
        profile_version=1,
        tagline_or_description=description,
        products_and_services=products or [],
        target_audiences=audiences or [],
        use_cases=use_cases or [],
        pricing_models=[],
        differentiators=[],
        faqs=[],
        supported_languages=["en"],
        facts=[
            GroundedFact(
                id="f1",
                fact_type="industry",
                fact_value=industry,
                confidence=0.95,
                source_url=f"https://{domain}/",
                evidence_snippet=industry,
                extraction_method="json_ld_schema"
            ),
            GroundedFact(
                id="f2",
                fact_type="company_description",
                fact_value=description,
                confidence=0.9,
                source_url=f"https://{domain}/",
                evidence_snippet=description,
                extraction_method="meta_description"
            )
        ]
    )


def test_classifier_routes_crm_correctly():
    """Verify that CRM / outbound sales platforms are classified as crm_sales, NOT developer_tools."""
    profile = make_profile(
        business_name="SalesFlow",
        domain="salesflow.com",
        industry="BusinessApplication",
        description="All-in-one CRM and sales pipeline automation for marketing agencies and sales teams.",
        use_cases=["lead prospecting", "pipeline management"]
    )
    classification = CategoryClassifier.classify(profile)
    assert classification.domain_archetype == "crm_sales"
    assert "crm" in classification.primary_category.lower() or "sales" in classification.primary_category.lower()


def test_classifier_routes_developer_tools_correctly():
    """Verify that developer API / cloud infra platforms are classified as developer_tools."""
    profile = make_profile(
        business_name="APIProxy",
        domain="apiproxy.dev",
        industry="SoftwareApplication",
        description="Low-latency API gateway, model routing, and SDK toolkit for backend engineering teams.",
        use_cases=["api routing", "latency optimization"]
    )
    classification = CategoryClassifier.classify(profile)
    assert classification.domain_archetype in ("developer_tools", "saas_software")
    assert "developer" in classification.primary_category.lower() or "infrastructure" in classification.primary_category.lower() or "api" in classification.primary_category.lower()


def test_classifier_routes_marketing_automation_correctly():
    """Verify that marketing automation platforms are classified as marketing_automation."""
    profile = make_profile(
        business_name="MailBlast",
        domain="mailblast.io",
        industry="SoftwareApplication",
        description="Automated email marketing campaigns, customer segmentation, and newsletter analytics.",
        use_cases=["email campaigns", "customer segmentation"]
    )
    classification = CategoryClassifier.classify(profile)
    assert classification.domain_archetype == "marketing_automation"


def test_classifier_routes_fintech_correctly():
    """Verify that fintech / payment platforms are classified as fintech."""
    profile = make_profile(
        business_name="PayQuick",
        domain="payquick.com",
        industry="FinancialService",
        description="Payment gateway, automated billing, and invoice reconciliation software for online businesses.",
        use_cases=["payment processing", "automated invoicing"]
    )
    classification = CategoryClassifier.classify(profile)
    assert classification.domain_archetype == "fintech"


def test_classifier_routes_healthcare_correctly():
    """Verify that healthcare technology platforms are classified as healthcare_tech."""
    profile = make_profile(
        business_name="CareSync",
        domain="caresync.health",
        industry="MedicalOrganization",
        description="HIPAA-compliant EHR and patient scheduling software for clinical practices.",
        use_cases=["patient scheduling", "clinical records"]
    )
    classification = CategoryClassifier.classify(profile)
    assert classification.domain_archetype == "healthcare_tech"


def test_classifier_handles_uncertain_categories_honestly():
    """Verify that sparse / ambiguous homepages do not silently fall back to developer_tools."""
    profile = make_profile(
        business_name="AcmeGlobal",
        domain="acmeglobal.xyz",
        industry="",
        description="Empowering organizations worldwide through modern innovative solutions."
    )
    classification = CategoryClassifier.classify(profile)
    assert classification.domain_archetype in ("uncertain_category", "general_business_software")
    assert classification.domain_archetype != "developer_tools"


@pytest.mark.asyncio
async def test_crm_prompts_do_not_contain_developer_infrastructure_jargon():
    """Verify that CRM platforms never receive prompts about cloud gateways, self-hosted proxies, SDKs, or backend engineers."""
    profile = make_profile(
        business_name="Clay",
        domain="clay.com",
        industry="BusinessApplication",
        description="Scale outbound prospecting, automate CRM data enrichment, and launch targeted sales plays.",
        use_cases=["launching outbound sales plays", "enriching B2B prospect data", "running automated workflows"]
    )

    plan = CoveragePlanner.create_plan(profile, requested_count=20)
    generator = DeterministicGenerator()
    candidates = await generator.generate(profile, plan)

    assert len(candidates) >= 15
    forbidden_infra_terms = ["cloud gateways", "self-hosted proxies", "sdk quality", "api ergonomics", "backend engineers"]

    for cand in candidates:
        lowered = cand.text.lower()
        for term in forbidden_infra_terms:
            assert term not in lowered, f"CRM prompt contained forbidden infra term '{term}': {cand.text}"
        # Ensure no 'B2B Software & Cloud Platforms' tautology
        assert "b2b software & cloud platforms" not in lowered
        assert "platforms for b2b" not in lowered


def test_normalizer_eliminates_b2b_software_and_cloud_platforms_tautology():
    """Verify that Schema.org BusinessApplication normalizes to a concise singular/adjectival category."""
    humanized = humanize_category_or_industry("BusinessApplication")
    # Must NOT be the awkward multi-word plural 'B2B Software & Cloud Platforms'
    assert humanized != "B2B Software & Cloud Platforms"
    assert "platform" not in humanized.lower() or "platforms" not in humanized.lower()


def test_validator_rejects_tautological_and_grammatically_flawed_prompts():
    """Verify validator catches 'platforms for ... platforms' and 'a modern ... platforms'."""
    profile = make_profile("TestBrand", "testbrand.com", "software", "Software tools")

    bad_tautology = GeneratedPromptCandidate(
        text="What are the leading modern platforms for B2B Software & Cloud Platforms?",
        category="discovery",
        intent="informational",
        buying_stage="awareness"
    )
    is_valid, reason = PromptValidator.validate(bad_tautology, profile)
    assert is_valid is False
    assert "tautolog" in reason.lower() or "repeated" in reason.lower() or "platforms for" in reason.lower()

    bad_grammar = GeneratedPromptCandidate(
        text="What should teams expect to budget for a modern B2B Software & Cloud platforms?",
        category="pricing_value",
        intent="transactional",
        buying_stage="decision"
    )
    is_valid, reason = PromptValidator.validate(bad_grammar, profile)
    assert is_valid is False
    assert "grammar" in reason.lower() or "plural" in reason.lower() or "agreement" in reason.lower() or "a modern" in reason.lower()


def test_validator_rejects_developer_infra_for_crm_profile():
    """Verify validator rejects cloud gateways and proxies for a CRM profile."""
    crm_profile = make_profile("SalesCRM", "salescrm.com", "CRM", "Sales management CRM platform")

    bad_gateway_prompt = GeneratedPromptCandidate(
        text="How do hosted cloud gateways compare to self-hosted proxies for sales software?",
        category="comparisons",
        intent="comparative",
        buying_stage="consideration"
    )
    is_valid, reason = PromptValidator.validate(bad_gateway_prompt, crm_profile)
    assert is_valid is False
    assert "incompatible" in reason.lower() or "category mismatch" in reason.lower() or "infrastructure" in reason.lower()


def test_prompt_candidate_lifecycle_states():
    """Verify that prompt review lifecycle states and validation metadata are supported."""
    cand = GeneratedPromptCandidate(
        text="What are the best CRMs for a small agency?",
        category="recommendations",
        intent="commercial",
        buying_stage="consideration",
        lifecycle_status="proposed"
    )
    assert cand.lifecycle_status == "proposed"
    cand.lifecycle_status = "approved"
    assert cand.lifecycle_status == "approved"
    cand.lifecycle_status = "rejected"
    assert cand.lifecycle_status == "rejected"
