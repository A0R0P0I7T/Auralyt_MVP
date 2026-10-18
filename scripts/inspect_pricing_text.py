import sqlite3
import sys

sys.stdout.reconfigure(encoding='utf-8')

def main():
    conn = sqlite3.connect("auralyt.db")
    c = conn.cursor()
    c.execute("SELECT extracted_text FROM crawled_pages WHERE id = 'cd98c3fb-708b-4110-814b-64524d889d02'")
    row = c.fetchone()
    if row:
        lines = row[0].split("\n")
        for i, l in enumerate(lines):
            if "25,000" in l:
                start = max(0, i - 10)
                end = min(len(lines), i + 10)
                print(f"--- Context around line {i} ---")
                for j in range(start, end):
                    print(f"{j:3d}: {lines[j]}")

if __name__ == "__main__":
    main()
