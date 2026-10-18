import sys
sys.path.insert(0, ".")
from app.db.models import CrawledPage
from app.extractor.fact_synthesizer import FactSynthesizer

page = CrawledPage(
    id="test-p1",
    brand_id="test-saas",
    requested_url="https://example.com/pricing",
    final_url="https://example.com/pricing",
    http_status=200,
    page_type="pricing",
    extracted_text="Starter: $20 / month.\nTeam Tier: $15 / user / month.\nEnterprise: $1,200 / year.",
    content_hash="test"
)

synth = FactSynthesizer("test-saas", user_business_name="Example")
facts = synth.synthesize_facts([page])
pricing_facts = [f for f in facts if f.fact_type == "pricing"]
for f in pricing_facts:
    val = f.fact_value
    print("Plan:", val.get("plan_name"), "Basis:", val.get("billing_basis"), "Snippet:", repr(f.evidence_snippet))
