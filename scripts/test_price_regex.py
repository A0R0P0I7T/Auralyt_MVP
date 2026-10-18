import re

PRICE_CURRENCY_REGEX = re.compile(r"(\$|€|£|₹)\s?(\d+(?:,\d{3})*(?:\.\d+)?)\s*(?:/\s*(?:month|mo|year|yr|user|seat))?", re.I)

text = "Starter: $20 / month.\nTeam Tier: $15 / user / month.\nEnterprise: $1,200 / year."

for pm in PRICE_CURRENCY_REGEX.finditer(text):
    line_start = text.rfind("\n", 0, pm.start())
    line_start = 0 if line_start == -1 else line_start + 1
    line_end = text.find("\n", pm.end())
    line_end = len(text) if line_end == -1 else line_end
    line_snippet = text[line_start:line_end].strip()
    
    p_text = pm.group(0)
    print("Match:", repr(p_text), "Line snippet:", repr(line_snippet))
    
    ls_lower = line_snippet.lower()
    is_per_user = bool(re.search(r"(?:/\s*(?:user|seat|member)|per\s+(?:user|seat|member))", ls_lower))
    is_annual = bool(re.search(r"(?:/\s*(?:yr|year)|per\s+year|annually|billed\s+annually)", ls_lower))
    is_monthly = bool(re.search(r"(?:/\s*(?:mo|month)|per\s+month|monthly|billed\s+monthly)", ls_lower))
    
    if is_per_user:
        basis = "per_user_monthly"
    elif is_annual:
        basis = "annually"
    elif is_monthly:
        basis = "monthly"
    else:
        basis = "unspecified"
    print("  -> Basis:", basis)
