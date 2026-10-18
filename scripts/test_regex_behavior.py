import re
import sys
sys.stdout.reconfigure(encoding='utf-8')

PRICING_TIER_REGEX = re.compile(r"\b(Free|Starter|Basic|Standard|Plus|Pro|Professional|Premium|Growth|Business|Enterprise|Team|Personal|Developer|Core)\b", re.I)
PRICE_CURRENCY_REGEX = re.compile(r"(\$|€|£|₹)\s?(\d+(?:,\d{3})*(?:\.\d+)?)\s?(?:/\s?(?:mo|month|yr|year|user|seat))?", re.I)

snippet = "Enterprise Invoicing options BYOK Limits Learn more → Free No Standard $25,000 of list price inference / month with no fees, 5% fee after Business $25,000 of list price inference / month with no fees, 5% fee after Enterprise"

for pm in PRICE_CURRENCY_REGEX.finditer(snippet):
    before_snippet = snippet[max(0, pm.start() - 40):pm.start()]
    tiers = list(PRICING_TIER_REGEX.finditer(before_snippet))
    print("Match:", pm.group(0), "Start:", pm.start())
    print("Before snippet:", repr(before_snippet))
    print("Tiers found:", [t.group(0) for t in tiers])
    if tiers:
        print("Selected tier:", tiers[-1].group(0))
