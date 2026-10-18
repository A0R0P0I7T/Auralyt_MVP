import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

def main():
    conn = sqlite3.connect("auralyt.db")
    c = conn.cursor()
    c.execute("SELECT id, brand_id, source_url, fact_value, evidence_snippet FROM brand_facts WHERE fact_type='pricing'")
    rows = c.fetchall()
    by_domain = {}
    for r in rows:
        fid, bid, surl, val_raw, snippet = r
        val = json.loads(val_raw) if isinstance(val_raw, str) else val_raw
        domain = surl.split("/")[2] if "://" in str(surl) else "other"
        by_domain.setdefault(domain, []).append((fid, val, snippet, surl))
    
    for dom, facts in by_domain.items():
        print(f"\nDOMAIN: {dom} ({len(facts)} pricing facts)")
        for fid, val, snip, surl in facts[:10]:
            print(f"  [{fid[:8]}] Plan: {val.get('plan_name')} | Amount: {val.get('amount')} | Type: {val.get('pricing_type')} | Billing: {val.get('billing_basis')} | Display: {val.get('formatted_display')}")

if __name__ == "__main__":
    main()
