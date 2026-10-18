import sys
import sqlite3
import re

sys.stdout.reconfigure(encoding='utf-8')

def main():
    conn = sqlite3.connect("auralyt.db")
    c = conn.cursor()
    c.execute("SELECT extracted_text, page_type FROM crawled_pages WHERE id = 'cd98c3fb-708b-4110-814b-64524d889d02'")
    row = c.fetchone()
    text = row[0]
    idx2 = text.find("Platform fees", 200)
    print("Found Platform fees #2 at:", idx2)
    if idx2 != -1:
        print("Slice #2:")
        print(text[idx2:idx2+250])

if __name__ == "__main__":
    main()
