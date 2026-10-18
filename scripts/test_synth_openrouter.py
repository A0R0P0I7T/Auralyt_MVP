import sys
import sqlite3
import json
sys.path.insert(0, ".")
from app.db.models import CrawledPage
from app.extractor.fact_synthesizer import FactSynthesizer

sys.stdout.reconfigure(encoding='utf-8')

def main():
    conn = sqlite3.connect("auralyt.db")
    c = conn.cursor()
    c.execute("SELECT id, brand_id, final_url, page_type, extracted_text, structured_data FROM crawled_pages WHERE final_url LIKE '%openrouter.ai/models%'")
    rows = c.fetchall()
    print(f"Found {len(rows)} models pages")
    for row in rows:
        pid, bid, furl, ptype, text, sdata = row
        print(f"\nTesting page: {furl} ({pid})")
        page = CrawledPage(
            id=pid,
            brand_id=bid,
            requested_url=furl,
            final_url=furl,
            http_status=200,
            page_type=ptype,
            extracted_text=text,
            structured_data=json.loads(sdata) if sdata else [],
            content_hash="test"
        )
        synth = FactSynthesizer(brand_id=bid, user_business_name="OpenRouter")
        facts = synth.synthesize_facts([page])
        pricing_facts = [f for f in facts if f.fact_type == "pricing"]
        print(f"Extracted {len(pricing_facts)} pricing facts:")
        for pf in pricing_facts[:10]:
            val = pf.fact_value
            print(f"Plan: {val.get('plan_name')} | Amount: {val.get('amount')} | Type: {val.get('pricing_type')} | Unit: {val.get('unit')} | Billing: {val.get('billing_basis')} | Display: {val.get('formatted_display')}")
            print(f"Evidence: {pf.evidence_snippet}")
            print("-" * 50)

if __name__ == "__main__":
    main()
