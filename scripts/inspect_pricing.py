import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

def main():
    conn = sqlite3.connect("auralyt.db")
    c = conn.cursor()
    c.execute("SELECT id, brand_id, source_url, fact_value, evidence_snippet FROM brand_facts WHERE source_url LIKE '%openrouter.ai/pricing%'")
    rows = c.fetchall()
    print(f"Total facts for openrouter.ai/pricing: {len(rows)}")
    for r in rows:
        fid, bid, surl, val_raw, snippet = r
        val = json.loads(val_raw) if isinstance(val_raw, str) else val_raw
        print("=" * 80)
        print(f"ID: {fid} | Plan: {val.get('plan_name')} | Amount: {val.get('amount')} | Type: {val.get('pricing_type')} | Billing: {val.get('billing_basis')} | Display: {val.get('formatted_display')}")
        print(f"Evidence: {snippet}")

if __name__ == "__main__":
    main()
