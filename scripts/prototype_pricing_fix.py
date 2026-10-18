import re
import sys
import sqlite3
import json

sys.stdout.reconfigure(encoding='utf-8')

PRICING_TIER_REGEX = re.compile(r"\b(Free|Starter|Basic|Standard|Plus|Pro|Professional|Premium|Growth|Business|Enterprise|Team|Personal|Developer|Core)\b", re.I)
PRICE_CURRENCY_REGEX = re.compile(r"(\$|€|£|₹)\s?(\d+(?:,\d{3})*(?:\.\d+)?)\s?(?:/\s?(?:mo|month|yr|year|user|seat))?", re.I)

# Allowance / Quota / Limit indicators that must NEVER be classified as subscription plan prices
ALLOWANCE_INDICATORS = (
    "of list price inference", "list price inference", "with no fees", "allowance",
    "byok limit", "byok limits", "spend limit", "credit limit", "included credit",
    "included credits", "free credit", "free credits", "usage limit", "monthly allowance",
    "free requests", "free tier allowance", "inference / month with no fees",
    "inference / month", "tokens / month with no fees", "requests / month with no fees"
)

# Detailed usage unit regex
USAGE_UNIT_REGEX = re.compile(
    r"(?:/\s*(?:m\b|million|k\b|thousand|1m|1k|1,000|token|tokens|input\s*tokens?|output\s*tokens?|credit|credits|request|requests|query|queries|gb|character|characters|image|images|sec|second|hour)|"
    r"per\s+(?:m\b|million|k\b|thousand|1m|1k|1,000|token|tokens|input\s*tokens?|output\s*tokens?|credit|credits|request|requests|query|queries|gb|character|characters|image|images|sec|second|hour))",
    re.I
)

def extract_pricing_prototype(page_type, text):
    results = []
    seen_plans = set()
    price_matches = list(PRICE_CURRENCY_REGEX.finditer(text))
    
    for pm in price_matches:
        p_text = pm.group(0).strip()
        curr_sym = pm.group(1)
        num_str = pm.group(2)
        try:
            num_val = float(num_str.replace(",", ""))
        except ValueError:
            continue
            
        after_match = text[pm.end():pm.end() + 35].lower()
        if re.match(r"^\s*(?:\.\d+)?\s*(?:million|billion|trillion|m\b|b\b|k\b|arr\b|series\b|valuation\b|funding\b|revenue\b|round\b|raised\b|prize|prizes|fine|fines|penalty|auction|saved|savings|seed)", after_match):
            continue
            
        snippet_start = max(0, pm.start() - 70)
        snippet_end = min(len(text), pm.end() + 70)
        snippet = text[snippet_start:snippet_end].replace("\n", " ").strip()
        snippet_lower = snippet.lower()
        
        # Reject funding, fines, prize pools
        if any(bad in snippet_lower for bad in (
            "in prizes", "in prize", "prize pool", "seed round", "series a", "series b",
            "series c", "raised $", "raised a $", "invest $", "invests $", "fines of",
            "facing fines", "charity auction", "in fines", "costs by $", "save up to",
            "saved $", "discount of"
        )):
            continue
            
        # Detect Quotas, Allowances, or Spend Limits
        is_allowance = any(k in snippet_lower for k in ALLOWANCE_INDICATORS)
        
        # Identify usage unit
        has_usage_unit = bool(USAGE_UNIT_REGEX.search(snippet_lower)) or bool(USAGE_UNIT_REGEX.search(after_match))
        
        # Identify recurring unit
        has_recurring_unit = bool(re.search(r"(?:/\s*(?:mo|month|yr|year|user|seat|member)|per\s+(?:month|year|user|seat|member)|billed\s+(?:annually|monthly))", snippet_lower))
        
        has_package_term = any(
            k in snippet_lower for k in ("package", "flat rate", "flat fee", "one-time", "starting rate", "costs $", "price:")
        )
        
        # Tier name
        plan_name = None
        before_snippet = text[max(0, pm.start() - 40):pm.start()]
        tier_matches_before = list(PRICING_TIER_REGEX.finditer(before_snippet))
        if tier_matches_before:
            plan_name = tier_matches_before[-1].group(0).capitalize()
        else:
            after_snippet = text[pm.end():min(len(text), pm.end() + 40)]
            tier_m_after = PRICING_TIER_REGEX.search(after_snippet)
            if tier_m_after:
                plan_name = tier_m_after.group(0).capitalize()
                
        # Model / product candidate in snippet
        model_name = None
        if has_usage_unit:
            model_match = re.search(r"\b([A-Za-z0-9\.\-]+(?:\s+[A-Za-z0-9\.\-]+){0,3})\s*[:\-–—]\s*" + re.escape(p_text), snippet)
            if not model_match:
                # Try before price e.g. "Anthropic: Claude Haiku 5.5 ... $0.05"
                prefix_match = re.search(r"\b([A-Z][a-zA-Z0-9\.\-]+:\s+[A-Z][a-zA-Z0-9\.\-]+(?:\s+[A-Za-z0-9\.\-]+){0,2})", snippet)
                if prefix_match:
                    cand = prefix_match.group(1).strip()
                    if 3 <= len(cand) <= 40:
                        model_name = cand
            else:
                cand_model = model_match.group(1).strip()
                if 3 <= len(cand_model) <= 40 and not any(k in cand_model.lower() for k in ("price", "pricing", "cost", "from", "starting")):
                    model_name = cand_model

        # Strictly reject context-free numbers
        if not plan_name and not model_name and not has_usage_unit and not has_recurring_unit and not has_package_term and page_type != "pricing":
            continue

        # Classify semantics
        if is_allowance:
            # Quotas/allowances must NEVER be classified as subscription plans!
            pricing_type = "usage_allowance"
            billing_basis = "monthly" if "month" in snippet_lower else "unspecified"
            unit_str = "inference allowance" if "inference" in snippet_lower else "credits allowance"
            effective_name = plan_name or "Usage Allowance"
            formatted_display = f"{effective_name}: {curr_sym}{num_val:,.0f} {unit_str}"
        elif has_usage_unit:
            pricing_type = "usage_rate"
            billing_basis = "usage"
            if "input token" in snippet_lower or "input token" in after_match:
                unit_str = "1M input tokens" if ("m" in snippet_lower or "1m" in snippet_lower) else "token"
            elif "output token" in snippet_lower or "output token" in after_match:
                unit_str = "1M output tokens" if ("m" in snippet_lower or "1m" in snippet_lower) else "token"
            elif "character" in snippet_lower or "character" in after_match:
                unit_str = "1M characters" if ("m" in snippet_lower or "1m" in snippet_lower) else "character"
            elif "1m" in snippet_lower or "/m" in snippet_lower or "/m" in after_match or "million" in snippet_lower:
                unit_str = "1M tokens"
            elif "1k" in snippet_lower or "/k" in snippet_lower or "/k" in after_match or "thousand" in snippet_lower or "1,000" in snippet_lower:
                unit_str = "1K tokens"
            elif "request" in snippet_lower or "request" in after_match:
                unit_str = "request"
            elif "query" in snippet_lower or "query" in after_match:
                unit_str = "query"
            elif "credit" in snippet_lower or "credit" in after_match:
                unit_str = "credit"
            elif "image" in snippet_lower or "image" in after_match:
                unit_str = "image"
            elif "gb" in snippet_lower or "gb" in after_match:
                unit_str = "GB"
            else:
                unit_str = "token"
            effective_name = model_name or plan_name or "Usage Rate"
            formatted_display = f"{effective_name}: {curr_sym}{num_val} / {unit_str}"
        elif any(u in p_text.lower() or u in snippet_lower for u in ("/yr", "/year", "annually", "per year", "billed annually")):
            pricing_type = "subscription_plan"
            billing_basis = "annually"
            unit_str = "year"
            effective_name = plan_name or "Subscription"
            formatted_display = f"{effective_name}: {curr_sym}{num_val:.2f} / {unit_str}".replace(".00 /", " /")
        elif any(u in p_text.lower() or u in snippet_lower for u in ("/user", "/seat", "/member", "per user", "per seat")):
            pricing_type = "subscription_plan"
            billing_basis = "per_user_monthly"
            unit_str = "user/month"
            effective_name = plan_name or "Team Plan"
            formatted_display = f"{effective_name}: {curr_sym}{num_val:.2f} / {unit_str}".replace(".00 /", " /")
        elif has_recurring_unit or "per month" in snippet_lower or "/mo" in snippet_lower or "/month" in snippet_lower or "billed monthly" in snippet_lower:
            pricing_type = "subscription_plan"
            billing_basis = "monthly"
            unit_str = "month"
            effective_name = plan_name or "Monthly Plan"
            formatted_display = f"{effective_name}: {curr_sym}{num_val:.2f} / {unit_str}".replace(".00 /", " /")
        elif has_package_term or "one-time" in snippet_lower or "flat rate" in snippet_lower:
            pricing_type = "one_time"
            billing_basis = "one_time"
            unit_str = "package"
            effective_name = plan_name or "Package"
            formatted_display = f"{effective_name}: {curr_sym}{num_val:.2f}".replace(".00", "")
        else:
            pricing_type = "subscription_plan" if page_type == "pricing" and plan_name else "unverified"
            billing_basis = "unspecified"
            unit_str = "unspecified"
            effective_name = plan_name or "Pricing"
            formatted_display = f"{effective_name}: {curr_sym}{num_val}"

        # Distinct deduplication key
        plan_key = (effective_name.lower(), round(num_val, 4), billing_basis, unit_str, pricing_type)
        if plan_key in seen_plans:
            continue
        seen_plans.add(plan_key)

        curr_code = "USD" if curr_sym == "$" else ("EUR" if curr_sym == "€" else ("GBP" if curr_sym == "£" else ("INR" if curr_sym == "₹" else "USD")))

        results.append({
            "plan_name": effective_name,
            "amount": num_val,
            "currency": curr_code,
            "unit": unit_str,
            "billing_basis": billing_basis,
            "pricing_type": pricing_type,
            "formatted_display": formatted_display,
            "price": str(num_val),
            "evidence": snippet
        })
    return results

def main():
    conn = sqlite3.connect("auralyt.db")
    c = conn.cursor()
    # Test openrouter pricing page
    c.execute("SELECT extracted_text, page_type FROM crawled_pages WHERE id = 'cd98c3fb-708b-4110-814b-64524d889d02'")
    row = c.fetchone()
    if row:
        print("=== PRICING PAGE RESULTS ===")
        res = extract_pricing_prototype(row[1], row[0])
        for r in res:
            print(f"[{r['pricing_type'].upper()}] {r['formatted_display']} (billing: {r['billing_basis']}, unit: {r['unit']})")
            print(f"Evidence: {r['evidence']}")
            print()
            
    # Test models page
    c.execute("SELECT extracted_text, page_type FROM crawled_pages WHERE id = 'c55b0582-9d00-42b1-b265-af86cf946f12'")
    row = c.fetchone()
    if row:
        print("=== MODELS PAGE RESULTS ===")
        res = extract_pricing_prototype(row[1], row[0])
        for r in res[:10]:
            print(f"[{r['pricing_type'].upper()}] {r['formatted_display']} (billing: {r['billing_basis']}, unit: {r['unit']})")
            print(f"Evidence: {r['evidence']}")
            print()

if __name__ == "__main__":
    main()
