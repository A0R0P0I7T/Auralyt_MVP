import sqlite3
import json
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

con = sqlite3.connect('auralyt.db')
cur = con.cursor()

rows = cur.execute('''
    SELECT id, brand_id, fact_type, fact_value, source_url, evidence_snippet, extraction_method 
    FROM brand_facts 
    WHERE fact_value LIKE '%25000%'
''').fetchall()

for r in rows:
    f_id, b_id, f_type, f_val_raw, url, snippet, method = r
    val = json.loads(f_val_raw)
    print("FACT ID:", f_id)
    print("METHOD:", method)
    print("URL:", url)
    print("VALUE:", json.dumps(val, indent=2))
    print("SNIPPET:", snippet)
    print("=" * 60)
