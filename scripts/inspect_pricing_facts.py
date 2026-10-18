import sqlite3
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

con = sqlite3.connect('auralyt.db')
cur = con.cursor()

# Get brands
brands = {r[0]: r[1] for r in cur.execute('SELECT id, business_name FROM brands').fetchall()}

rows = cur.execute('''
    SELECT id, brand_id, fact_type, fact_value, source_url, evidence_snippet, extraction_method, confidence, user_confirmed, is_rejected 
    FROM brand_facts 
    WHERE fact_type = 'pricing' AND brand_id = '5c785452-feea-4038-9a29-eea7b6252ec0'
''').fetchall()

print(f"Total pricing facts found: {len(rows)}")

for r in rows:
    f_id, b_id, f_type, f_val_raw, url, snippet, method, conf, conf_by_user, rej = r
    try:
        val = json.loads(f_val_raw)
    except:
        val = f_val_raw
    b_name = brands.get(b_id, b_id)
    print(f"Brand: {b_name} | FactID: {f_id} | Method: {method} | Confirmed: {conf_by_user} | Rejected: {rej}")
    print(f"  Value: {val}")
    print(f"  URL: {url}")
    print(f"  Snippet: {snippet[:120]}")
    print("-" * 60)
