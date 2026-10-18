import sqlite3
import sys

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

con = sqlite3.connect('auralyt.db')
cur = con.cursor()

row = cur.execute('''
    SELECT final_url, page_type, extracted_text 
    FROM crawled_pages 
    WHERE final_url LIKE '%openrouter.ai/pricing%'
''').fetchone()

if row:
    print("URL:", row[0])
    print("Page Type:", row[1])
    print("Text length:", len(row[2]) if row[2] else 0)
    print("Extracted Text:")
    print(row[2])
else:
    print("No page found for openrouter.ai/pricing")
