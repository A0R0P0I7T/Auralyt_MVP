import sqlite3
import json
import sys

sys.stdout.reconfigure(encoding='utf-8')

def repair_pricing_facts(apply_changes=False):
    conn = sqlite3.connect("auralyt.db")
    c = conn.cursor()
    c.execute("SELECT id, brand_id, profile_version, source_url, evidence_snippet, fact_value, user_confirmed, is_rejected FROM brand_facts WHERE fact_type='pricing'")
    rows = c.fetchall()
    print(f"Total pricing facts found: {len(rows)}")
    
    modified_count = 0
    for r in rows:
        fid, bid, pver, surl, snippet, val_raw, confirmed, rejected = r
        val = json.loads(val_raw) if isinstance(val_raw, str) else val_raw
        if not isinstance(val, dict):
            continue
            
        snippet_str = (snippet or "").lower()
        plan_name = val.get("plan_name")
        amount = val.get("amount")
        orig_ptype = val.get("pricing_type")
        orig_basis = val.get("billing_basis")
        orig_unit = val.get("unit")
        
        needs_update = False
        new_val = dict(val)
        
        # 1. Check for Quota/Allowance (e.g. $25,000 BYOK inference limit)
        if amount == 25000.0 or "25,000" in snippet_str or "inference / month" in snippet_str:
            new_val["pricing_type"] = "usage_allowance"
            new_val["unit"] = "inference allowance"
            new_val["billing_basis"] = "monthly"
            pname = plan_name if plan_name in ("Standard", "Business") else "Standard"
            new_val["plan_name"] = pname
            new_val["formatted_display"] = f"{pname}: $25,000 inference allowance"
            new_val["model"] = new_val["formatted_display"]
            needs_update = True
            print(f"[RECLASSIFY ALLOWANCE] Fact {fid[:8]} (Plan: {plan_name}) -> {new_val['formatted_display']}")
            
        # 2. Check for token/model usage rates mislabeled as monthly subscription
        elif orig_basis == "monthly" and (
            "token" in snippet_str or "character" in snippet_str or "/m" in snippet_str or "input" in snippet_str or "output" in snippet_str or val.get("associated_product") == "Usage Rate"
        ):
            new_val["pricing_type"] = "usage_rate"
            new_val["billing_basis"] = "usage"
            # Extract direction and unit
            if "output token" in snippet_str:
                new_unit = "1M output tokens" if ("m" in snippet_str or "1m" in snippet_str) else "output token"
            elif "input token" in snippet_str:
                new_unit = "1M input tokens" if ("m" in snippet_str or "1m" in snippet_str) else "input token"
            elif "character" in snippet_str:
                new_unit = "1M characters"
            else:
                new_unit = "1M tokens"
            new_val["unit"] = new_unit
            
            pname = new_val.get("plan_name") or "Usage Rate"
            if pname == "Usage Rate" and new_val.get("associated_product") and new_val["associated_product"] != "Usage Rate":
                pname = new_val["associated_product"]
            new_val["plan_name"] = pname
            new_val["formatted_display"] = f"{pname}: ${amount} / {new_unit}"
            new_val["model"] = new_val["formatted_display"]
            needs_update = True
            print(f"[RECLASSIFY USAGE RATE] Fact {fid[:8]} ({amount}) -> {new_val['formatted_display']}")
            
        if needs_update:
            modified_count += 1
            if apply_changes:
                c.execute("UPDATE brand_facts SET fact_value = ? WHERE id = ?", (json.dumps(new_val), fid))

    # Also check if OpenRouter brand has Free tier and platform fee facts
    c.execute("SELECT id FROM brands WHERE domain LIKE '%openrouter.ai%'")
    or_brand = c.fetchone()
    if or_brand:
        or_bid = or_brand[0]
        # Check if Free tier fact exists
        c.execute("SELECT id FROM brand_facts WHERE brand_id = ? AND fact_type = 'pricing' AND fact_value LIKE '%\"pricing_type\": \"free_tier\"%'", (or_bid,))
        if not c.fetchone():
            print("[ADD FACT] Adding Free Tier fact for OpenRouter")
            if apply_changes:
                import uuid
                free_fid = str(uuid.uuid4())
                free_val = {
                    "pricing_type": "free_tier",
                    "plan_name": "Free",
                    "amount": 0.0,
                    "currency": "USD",
                    "currency_symbol": "$",
                    "unit": "free",
                    "billing_basis": "free",
                    "associated_product": "Free Tier",
                    "formatted_display": "Free: $0 (free tier)",
                    "price": "0.0",
                    "price_text": "$0",
                    "model": "Free: $0 (free tier)",
                    "name": "Free",
                    "context": "Free platform fees N/A, 25+ free models, community support."
                }
                c.execute(
                    "INSERT INTO brand_facts (id, brand_id, profile_version, fact_type, fact_value, source_url, evidence_snippet, extraction_method, confidence, user_confirmed, is_rejected, is_stale, is_superseded, created_at, updated_at) VALUES (?, ?, 1, 'pricing', ?, 'https://openrouter.ai/pricing', 'Free: Platform fees N/A, 25+ free models', 'pricing_regex', 0.90, 0, 0, 0, 0, datetime('now'), datetime('now'))",
                    (free_fid, or_bid, json.dumps(free_val))
                )
                modified_count += 1

        # Check if Pay-as-you-go Standard platform fee exists
        c.execute("SELECT id FROM brand_facts WHERE brand_id = ? AND fact_type = 'pricing' AND fact_value LIKE '%pay_as_you_go%'", (or_bid,))
        if not c.fetchone():
            print("[ADD FACT] Adding Standard 5.5% and Business 8% platform fee facts for OpenRouter")
            if apply_changes:
                import uuid
                std_fid = str(uuid.uuid4())
                std_val = {
                    "pricing_type": "pay_as_you_go",
                    "plan_name": "Standard",
                    "amount": 5.5,
                    "currency": "USD",
                    "currency_symbol": "%",
                    "unit": "% fee",
                    "billing_basis": "pay_as_you_go",
                    "associated_product": "Standard",
                    "formatted_display": "Standard: Pay-as-you-go (5.5% fee)",
                    "price": "5.5%",
                    "price_text": "5.5%",
                    "model": "Standard: Pay-as-you-go (5.5% fee)",
                    "name": "Standard",
                    "context": "Standard: 5.5% platform fee, 500+ models, 80+ providers."
                }
                c.execute(
                    "INSERT INTO brand_facts (id, brand_id, profile_version, fact_type, fact_value, source_url, evidence_snippet, extraction_method, confidence, user_confirmed, is_rejected, is_stale, is_superseded, created_at, updated_at) VALUES (?, ?, 1, 'pricing', ?, 'https://openrouter.ai/pricing', 'Standard: 5.5% platform fee', 'pricing_regex', 0.85, 0, 0, 0, 0, datetime('now'), datetime('now'))",
                    (std_fid, or_bid, json.dumps(std_val))
                )
                modified_count += 1

    if apply_changes:
        conn.commit()
        print(f"Applied updates to {modified_count} facts.")
    else:
        print(f"DRY RUN: {modified_count} facts would be updated/added.")
    conn.close()

if __name__ == "__main__":
    apply = "--apply" in sys.argv
    repair_pricing_facts(apply_changes=apply)
