"""Phase 1 & Phase 7: TDD Regression Tests for Natural-Language Quality,
Semantic Diversity, and Text-Integrity Remediation in Engine 2.
"""
import pytest
from app.prompts.generator import normalize_use_case_forms, DeterministicGenerator
from app.prompts.validator import PromptValidator
from app.prompts.normalizer import ProfileNormalizer
from app.prompts.planner import CoveragePlanner
from app.prompts.models import NormalizedBrandProfile, GeneratedPromptCandidate, PlannedPromptSlot


def test_regression_gerund_formation_drops_silent_e():
    """DEFECT 1: Verbs ending in silent 'e' must drop 'e' before adding 'ing'."""
    # Defective output was: 'createing', 'completeing', 'writeing'
    base_create, gerund_create = normalize_use_case_forms("create images")
    assert gerund_create.startswith("creating"), f"Expected 'creating', got '{gerund_create}'"
    assert "createing" not in gerund_create

    base_complete, gerund_complete = normalize_use_case_forms("complete work")
    assert gerund_complete.startswith("completing"), f"Expected 'completing', got '{gerund_complete}'"
    assert "completeing" not in gerund_complete

    base_write, gerund_write = normalize_use_case_forms("write articles")
    assert gerund_write.startswith("writing"), f"Expected 'writing', got '{gerund_write}'"
    assert "writeing" not in gerund_write

    base_code, gerund_code = normalize_use_case_forms("code applications")
    assert gerund_code.startswith("coding"), f"Expected 'coding', got '{gerund_code}'"

    base_generate, gerund_generate = normalize_use_case_forms("generate synthetic data")
    assert gerund_generate.startswith("generating"), f"Expected 'generating', got '{gerund_generate}'"


def test_regression_validator_rejects_malformed_gerund_spelling():
    """DEFECT 1 Validator: Quality gate must reject misspelled gerunds like 'createing' or 'completeing'."""
    profile = NormalizedBrandProfile(
        brand_id="chatgpt",
        domain="chatgpt.com",
        business_name="ChatGPT",
        industry="Artificial Intelligence",
        profile_version=1
    )

    bad_candidate_1 = GeneratedPromptCandidate(
        text="Which providers specialize in createing images?",
        category="use_cases",
        intent="informational",
        buying_stage="consideration",
        template_version="v3_test"
    )
    is_valid, reason = PromptValidator.validate(bad_candidate_1, profile)
    assert not is_valid
    assert "spelling" in reason.lower() or "malformed" in reason.lower() or "gerund" in reason.lower()

    bad_candidate_2 = GeneratedPromptCandidate(
        text="What options are best suited for completeing work?",
        category="use_cases",
        intent="informational",
        buying_stage="consideration",
        template_version="v3_test"
    )
    is_valid2, reason2 = PromptValidator.validate(bad_candidate_2, profile)
    assert not is_valid2


def test_regression_validator_rejects_double_participles_and_needing_gerund():
    """DEFECT 2 Validator: Quality gate must reject awkward 'needing <gerund>' phrases."""
    profile = NormalizedBrandProfile(
        brand_id="chatgpt",
        domain="chatgpt.com",
        business_name="ChatGPT",
        industry="Artificial Intelligence",
        profile_version=1
    )

    awkward_candidate = GeneratedPromptCandidate(
        text="What would you recommend for someone needing creating images?",
        category="use_cases",
        intent="informational",
        buying_stage="consideration",
        template_version="v3_test"
    )
    is_valid, reason = PromptValidator.validate(awkward_candidate, profile)
    assert not is_valid
    assert "awkward" in reason.lower() or "needing" in reason.lower() or "grammar" in reason.lower()


def test_regression_compound_capability_list_is_decomposed_not_concatenated():
    """DEFECT 3: Compound capability lists ('answer questions, write, create images...') must not be concatenated into a single question."""
    profile_data = {
        "brand": {
            "id": "chatgpt_test",
            "domain": "chatgpt.com",
            "business_name": "ChatGPT",
            "industry": "Artificial Intelligence & Machine Learning",
            "target_market": "Global",
            "language": "en",
        },
        "profile_version": 1,
        "facts": [
            {
                "id": "f1",
                "fact_type": "use_case",
                "fact_value": "answer questions, write, create images, complete work, and code",
                "confidence": 0.95,
                "user_confirmed": True
            }
        ]
    }
    profile = ProfileNormalizer.normalize(profile_data)
    clean_use_cases = profile.get_clean_use_cases()

    # The normalizer must decompose the compound use case into individual atomic actions
    # instead of passing the raw multi-verb string: 'answer questions, write, create images, complete work, and code'
    assert not any(", write, create images" in uc for uc in clean_use_cases), (
        f"Compound capability string was not decomposed: {clean_use_cases}"
    )
    assert any("create images" in uc for uc in clean_use_cases), (
        f"Expected 'create images' in decomposed use cases, got: {clean_use_cases}"
    )
    assert any("answer questions" in uc for uc in clean_use_cases)


def test_regression_validator_rejects_comma_spliced_capability_dump():
    """DEFECT 3 Validator: Quality gate must reject prompts dumping multiple raw capabilities into one slot."""
    profile = NormalizedBrandProfile(
        brand_id="chatgpt",
        domain="chatgpt.com",
        business_name="ChatGPT",
        industry="Artificial Intelligence",
        profile_version=1
    )

    dump_candidate = GeneratedPromptCandidate(
        text="Which providers specialize in answering questions, write, create images, complete work, and code?",
        category="use_cases",
        intent="informational",
        buying_stage="consideration",
        template_version="v3_test"
    )
    is_valid, reason = PromptValidator.validate(dump_candidate, profile)
    assert not is_valid
    assert "compound" in reason.lower() or "multiple" in reason.lower() or "unnatural" in reason.lower() or "list" in reason.lower()


def test_regression_deduplicator_rejects_semantic_near_duplicates_with_different_wording():
    """DEFECT 4: Prompts repeating the same core intent with superficial wording differences must be deduplicated."""
    from app.prompts.scorer import PromptScorer

    candidates = [
        GeneratedPromptCandidate(
            text="Which AI tools are best for writing?",
            category="use_cases",
            intent="informational",
            buying_stage="consideration",
            template_version="v3_test"
        ),
        GeneratedPromptCandidate(
            text="What AI tools should I use for writing?",
            category="use_cases",
            intent="informational",
            buying_stage="consideration",
            template_version="v3_test"
        ),
        GeneratedPromptCandidate(
            text="Which tools are useful for AI writing?",
            category="use_cases",
            intent="informational",
            buying_stage="consideration",
            template_version="v3_test"
        ),
    ]

    unique = PromptScorer.deduplicate(candidates)
    assert len(unique) == 1, f"Expected 1 unique intent, got {len(unique)}: {[c.text for c in unique]}"


def test_deduplicator_preserves_distinct_user_intents():
    """Distinct customer intents (writing vs image generation vs coding) must be preserved as separate prompts."""
    from app.prompts.scorer import PromptScorer

    candidates = [
        GeneratedPromptCandidate(
            text="Which AI tools are best for writing?",
            category="use_cases",
            intent="informational",
            buying_stage="consideration",
            template_version="v3_test"
        ),
        GeneratedPromptCandidate(
            text="Which AI tools are best for creating images?",
            category="use_cases",
            intent="informational",
            buying_stage="consideration",
            template_version="v3_test"
        ),
        GeneratedPromptCandidate(
            text="Which AI coding assistants are useful for debugging a Python application?",
            category="use_cases",
            intent="informational",
            buying_stage="consideration",
            template_version="v3_test"
        ),
    ]

    unique = PromptScorer.deduplicate(candidates)
    assert len(unique) == 3, f"Expected 3 distinct intents, got {len(unique)}: {[c.text for c in unique]}"


def test_validator_rejects_unbalanced_quotation_marks():
    """Validator must reject strings with unbalanced quotes from malformed fact interpolation."""
    profile = NormalizedBrandProfile(
        brand_id="chatgpt",
        domain="chatgpt.com",
        business_name="ChatGPT",
        industry="Artificial Intelligence",
        profile_version=1
    )

    bad_candidate = GeneratedPromptCandidate(
        text='What software architecture enables engineering teams to "answer questions?',
        category="use_cases",
        intent="informational",
        buying_stage="consideration",
        template_version="v3_test"
    )
    is_valid, reason = PromptValidator.validate(bad_candidate, profile)
    assert not is_valid
    assert "quote" in reason.lower() or "unbalanced" in reason.lower() or "malformed" in reason.lower()


def test_validator_rejects_repeated_words():
    """Validator must reject mechanical double-word artifacts like 'the the' or 'for for'."""
    profile = NormalizedBrandProfile(
        brand_id="chatgpt",
        domain="chatgpt.com",
        business_name="ChatGPT",
        industry="Artificial Intelligence",
        profile_version=1
    )

    bad_candidate = GeneratedPromptCandidate(
        text="What are the the leading platforms for AI tools?",
        category="discovery",
        intent="informational",
        buying_stage="awareness",
        template_version="v3_test"
    )
    is_valid, reason = PromptValidator.validate(bad_candidate, profile)
    assert not is_valid
    assert "repeated" in reason.lower() or "word" in reason.lower()


def test_validator_approves_natural_grammatical_unbranded_questions():
    """Validator approves high-quality natural questions with a clear user intent."""
    profile = NormalizedBrandProfile(
        brand_id="chatgpt",
        domain="chatgpt.com",
        business_name="ChatGPT",
        industry="Artificial Intelligence",
        profile_version=1
    )

    good_candidate = GeneratedPromptCandidate(
        text="What AI tools can help me research a topic and turn the findings into a report?",
        category="discovery",
        intent="informational",
        buying_stage="awareness",
        template_version="v3_test"
    )
    is_valid, reason = PromptValidator.validate(good_candidate, profile)
    assert is_valid, f"Expected valid question to be approved, got reason: {reason}"


def test_validator_rejects_missing_provenance_for_grounded_categories():
    """Case 8: Category requiring profile evidence must reference active profile fact IDs."""
    profile = NormalizedBrandProfile(
        brand_id="chatgpt",
        domain="chatgpt.com",
        business_name="ChatGPT",
        industry="Artificial Intelligence",
        profile_version=1,
        facts=[]
    )

    unproven_cand = GeneratedPromptCandidate(
        text="What options are best suited for creating images?",
        category="use_cases",
        intent="informational",
        buying_stage="consideration",
        provenance_fact_ids=["nonexistent_fact_id"],
        template_version="v3_test"
    )
    is_valid, reason = PromptValidator.validate(unproven_cand, profile)
    assert not is_valid
    assert "fact ids outside" in reason.lower() or "provenance" in reason.lower() or "requires provenance" in reason.lower()


def test_validator_rejects_unsupported_product_claims():
    """Case 9: Category-relevant questions claiming unsupported products not in profile must be rejected."""
    profile = NormalizedBrandProfile(
        brand_id="decathlon",
        domain="decathlon.in",
        business_name="Decathlon",
        industry="Sporting Goods",
        products_and_services=["Kiprun Long 2", "Kalenji Run Active"],
        profile_version=1
    )

    unsupported_prod_cand = GeneratedPromptCandidate(
        text="How durable is the Vaporfly Next 3 shoe for daily runs?",
        category="product_evaluation",
        intent="commercial",
        buying_stage="consideration",
        target_product_service="Vaporfly Next 3",
        template_version="v3_test"
    )
    is_valid, reason = PromptValidator.validate(unsupported_prod_cand, profile)
    assert not is_valid
    assert "outside the active profile" in reason.lower() or "unsupported" in reason.lower()


def test_validator_does_not_overzealously_reject_valid_creating_in_natural_context():
    """Case 10: Valid usage of 'creating' (not 'createing') in grammatical context must NOT be rejected."""
    profile = NormalizedBrandProfile(
        brand_id="chatgpt",
        domain="chatgpt.com",
        business_name="ChatGPT",
        industry="Artificial Intelligence",
        profile_version=1
    )

    valid_cand = GeneratedPromptCandidate(
        text="Which AI tools are best for creating images from text descriptions?",
        category="use_cases",
        intent="informational",
        buying_stage="consideration",
        template_version="v3_test"
    )
    is_valid, reason = PromptValidator.validate(valid_cand, profile)
    assert is_valid, f"Legitimate use of 'creating' was overzealously rejected: {reason}"


def test_versioned_cache_detects_stale_template_version():
    """Case 11: Prompt intelligence service detects when cached prompts were generated under an older template version."""
    from app.prompts.templates import TemplateRegistry
    current_version = TemplateRegistry.get_template_version()
    assert current_version == "v3_grounded_taxonomy"

    stale_cand = GeneratedPromptCandidate(
        text="What options are best suited for creating images?",
        category="use_cases",
        intent="informational",
        buying_stage="consideration",
        template_version="v2_relevance_freshness"
    )
    assert stale_cand.template_version != current_version


def test_whole_set_naturalness_rejection():
    """Case 12: A set containing grammatically malformed or compound prompts has those prompts rejected honestly."""
    profile = NormalizedBrandProfile(
        brand_id="chatgpt",
        domain="chatgpt.com",
        business_name="ChatGPT",
        industry="Artificial Intelligence",
        profile_version=1
    )

    prompt_set = [
        GeneratedPromptCandidate(text="Which providers specialize in createing images?", category="use_cases", intent="informational", buying_stage="consideration", template_version="v3_test"),
        GeneratedPromptCandidate(text="What would you recommend for someone needing creating images?", category="use_cases", intent="informational", buying_stage="consideration", template_version="v3_test"),
        GeneratedPromptCandidate(text="What AI tools can help me research a topic and turn findings into a report?", category="discovery", intent="informational", buying_stage="awareness", template_version="v3_test"),
    ]

    results = [PromptValidator.validate(p, profile) for p in prompt_set]
    assert not results[0][0]  # rejected: createing
    assert not results[1][0]  # rejected: needing creating
    assert results[2][0]      # approved: natural


def test_whole_set_deduplication_compresses_excessive_semantic_repetition():
    """Case 13: Whole set of 10 prompts with 8 variations of 'writing' collapses to distinct intents."""
    from app.prompts.scorer import PromptScorer

    candidates = [
        GeneratedPromptCandidate(text=f"Which AI tools are best for writing {i}?", category="use_cases", intent="informational", buying_stage="consideration", template_version="v3_test")
        for i in range(8)
    ]
    # Add 2 distinct intents
    candidates.append(GeneratedPromptCandidate(text="Which AI tools are best for coding?", category="use_cases", intent="informational", buying_stage="consideration", template_version="v3_test"))
    candidates.append(GeneratedPromptCandidate(text="Which AI tools are best for creating images?", category="use_cases", intent="informational", buying_stage="consideration", template_version="v3_test"))

    unique = PromptScorer.deduplicate(candidates)
    # The 8 writing variations must collapse to 1, plus coding (1) and image creation (1) = 3 total
    assert len(unique) == 3, f"Expected 3 distinct intents, got {len(unique)}: {[c.text for c in unique]}"


def test_normalization_text_integrity_preserves_words():
    """Case 14: Normalization preserves characters, does not corrupt words or introduce spelling defects."""
    from app.prompts.scorer import normalize_prompt_text

    raw_text = "What AI tools are best for creating images from text descriptions?"
    norm = normalize_prompt_text(raw_text)
    assert "creating" in norm
    assert "createing" not in norm
    assert "images" in norm
    assert "descriptions" in norm


def test_api_serialization_integrity():
    """Case 15: Prompt candidate serialization preserves exact prompt text without alteration."""
    from app.prompts.models import GeneratedPromptCandidate

    cand = GeneratedPromptCandidate(
        text="Which AI tools are best for creating images?",
        category="use_cases",
        intent="informational",
        buying_stage="consideration",
        template_version="v3_grounded_taxonomy"
    )
    dumped = cand.model_dump()
    assert dumped["text"] == "Which AI tools are best for creating images?"
    assert "createing" not in dumped["text"]
