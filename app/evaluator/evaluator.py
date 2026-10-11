"""Deterministic Visibility Evaluator for Engine 3.

Evaluates raw AI model responses across structured visibility dimensions:
1. Brand mention & verbatim context snippet
2. Recommendation or endorsement status
3. Competitor mentions
4. Comparative positioning
5. Verbatim citation and source URLs (strictly evidence-based)
6. Visibility rank in listed recommendations
"""
import re
from typing import Optional, List, Dict, Any, Tuple
from urllib.parse import urlparse
from pydantic import BaseModel, Field


class EvaluationResult(BaseModel):
    """Structured evaluation of a single AI model response."""
    brand_mentioned: bool = False
    mention_context: Optional[str] = None
    recommendation_status: str = "unknown"  # recommended, neutral_mention, not_recommended, not_mentioned, unknown
    competitor_mentions: List[str] = Field(default_factory=list)
    comparative_position: str = "unknown"   # leader, recommended_alternative, contender, mentioned_only, unfavorable, not_mentioned, unknown
    citations: List[str] = Field(default_factory=list)
    sentiment_score: Optional[float] = None # -1.0 to 1.0
    visibility_rank: Optional[int] = None   # 1-indexed list position
    evaluation_reasoning: str = ""


# Common industry competitors lookup by domain/name tokens for accurate recognition
COMMON_INDUSTRY_COMPETITORS: Dict[str, List[str]] = {
    "linear": ["Jira", "Asana", "Monday.com", "GitHub Issues", "ClickUp", "Shortcut", "Trello"],
    "vercel": ["Netlify", "Cloudflare Pages", "AWS Amplify", "Render", "Fly.io", "Heroku"],
    "nike": ["Adidas", "Under Armour", "Puma", "New Balance", "Asics", "Brooks", "Hoka", "Lululemon"],
    "webflow": ["Framer", "WordPress", "Squarespace", "Wix", "Shopify", "Webstudio"],
    "tavily": ["Perplexity", "Exa", "Bing Search API", "Google Search API", "SerpAPI", "Brave Search"],
    "hubspot": ["Salesforce", "ActiveCampaign", "Zoho CRM", "Pipedrive", "Marketo", "Mailchimp"],
    "dev": ["Medium", "Hashnode", "Substack", "Hacker News", "Reddit", "Stack Overflow"],
}

# Positive endorsement regex patterns
POSITIVE_RECOMMENDATION_PATTERNS = [
    r"\btop\s+(?:choice|pick|recommendation|option|platform|tool)\b",
    r"\bhighly\s+recommend(?:ed)?\b",
    r"\bwe\s+recommend\b",
    r"\bstrongly\s+recommend\b",
    r"\bbest\s+(?:choice|option|solution|for|fit|platform|tool|pick)\b",
    r"\bstands\s+out\s+as\b",
    r"\bis\s+the\s+leading\b",
    r"\bpremier\s+(?:choice|platform|tool|solution)\b",
    r"\bideal\s+for\b",
    r"\bgreat\s+(?:choice|option|solution|fit)\b",
    r"\branked\s+#?1\b",
    r"\bnumber\s+one\b",
]

# Negative recommendation patterns
NEGATIVE_RECOMMENDATION_PATTERNS = [
    r"\bdo\s+not\s+recommend\b",
    r"\bnot\s+recommended\b",
    r"\bavoid\b",
    r"\bfalls\s+short\b",
    r"\blacks\s+(?:essential|critical|key|modern)\b",
    r"\boutdated\b",
    r"\binferior\b",
    r"\blagging\s+behind\b",
    r"\bsteep\s+learning\s+curve\s+with\s+poor\b",
    r"\bexpensive\s+with\s+limited\b",
]


class VisibilityResponseEvaluator:
    """Evaluates raw model text against target brand and profile evidence."""

    @classmethod
    def evaluate(
        cls,
        response_text: str,
        brand_name: str,
        brand_domain: str,
        known_competitors: Optional[List[str]] = None,
        provider_metadata: Optional[Dict[str, Any]] = None
    ) -> EvaluationResult:
        """Deterministically parse and evaluate model response."""
        res = EvaluationResult()

        if not response_text or not response_text.strip():
            res.brand_mentioned = False
            res.recommendation_status = "not_mentioned"
            res.comparative_position = "not_mentioned"
            res.evaluation_reasoning = "Empty or missing response from AI model provider."
            return res

        text = response_text
        clean_text = text.replace("**", "").replace("*", "").replace("`", "")

        # 1. Target Brand Mention Check
        name_clean = brand_name.strip()
        domain_clean = brand_domain.split(":")[0].replace("www.", "").strip()
        domain_host = domain_clean.split(".")[0]

        # Regex for word-boundary brand mention
        escaped_name = re.escape(name_clean)
        escaped_domain = re.escape(domain_clean)
        escaped_host = re.escape(domain_host) if len(domain_host) >= 4 else r"(?!)"

        brand_pattern = re.compile(
            rf"\b({escaped_name}|{escaped_domain}|{escaped_host})\b",
            re.IGNORECASE
        )
        match = brand_pattern.search(clean_text)

        if match:
            res.brand_mentioned = True
            # Extract verbatim mention context sentence (or up to 250 characters surrounding the match)
            start_pos = max(0, match.start() - 60)
            end_pos = min(len(clean_text), match.end() + 140)
            snippet = clean_text[start_pos:end_pos].strip()

            # Clean snippet boundary to sentence breaks if possible
            if start_pos > 0 and not snippet.startswith((".", "!", "?")):
                snippet = "..." + snippet
            if end_pos < len(clean_text) and not snippet.endswith((".", "!", "?")):
                snippet = snippet + "..."
            res.mention_context = snippet
        else:
            res.brand_mentioned = False
            res.mention_context = None
            res.recommendation_status = "not_mentioned"
            res.comparative_position = "not_mentioned"

        # 2. Competitor Mentions Extraction
        detected_competitors: List[str] = []
        target_brand_lower = name_clean.lower()

        # Build candidate competitor list from known inputs + domain mapping
        candidates = set(known_competitors or [])
        for key, comp_list in COMMON_INDUSTRY_COMPETITORS.items():
            if key in target_brand_lower or key in domain_clean.lower():
                candidates.update(comp_list)

        # Detect competitors in text using word boundaries
        for comp in candidates:
            if comp.lower() == target_brand_lower or comp.lower() == domain_host.lower():
                continue
            comp_pattern = re.compile(rf"\b{re.escape(comp)}\b", re.IGNORECASE)
            if comp_pattern.search(clean_text) and comp not in detected_competitors:
                detected_competitors.append(comp)

        # Also extract structured list items that might be named competitors
        list_items = re.findall(r"(?:^|\n)\s*(?:\d+\.|\*|\-)\s+([A-Za-z0-9\.\-\s]{2,30}?)(?:—|–|-|:|\s{2,}|\n)", text)
        for item in list_items:
            item_clean = item.strip().replace("**", "")
            if item_clean.lower() != target_brand_lower and 2 <= len(item_clean) <= 25:
                # Disallow generic words
                if not any(g in item_clean.lower() for g in ("option", "feature", "summary", "conclusion", "pricing", "alternative", "step", "reason")):
                    if item_clean not in detected_competitors and item_clean.lower() not in [c.lower() for c in detected_competitors]:
                        detected_competitors.append(item_clean)

        res.competitor_mentions = detected_competitors[:10]

        # 3. Recommendation & Endorsement Analysis
        if res.brand_mentioned:
            context_to_check = (res.mention_context or clean_text).lower()
            full_lower = clean_text.lower()

            is_positive = any(re.search(pat, context_to_check) for pat in POSITIVE_RECOMMENDATION_PATTERNS)
            is_negative = any(re.search(pat, context_to_check) for pat in NEGATIVE_RECOMMENDATION_PATTERNS)

            if is_positive and not is_negative:
                res.recommendation_status = "recommended"
                res.sentiment_score = 0.85
            elif is_negative:
                res.recommendation_status = "not_recommended"
                res.sentiment_score = -0.75
            else:
                # Check if mentioned favorably elsewhere in full text
                if any(re.search(pat, full_lower) for pat in POSITIVE_RECOMMENDATION_PATTERNS):
                    res.recommendation_status = "recommended"
                    res.sentiment_score = 0.60
                elif any(w in context_to_check for w in ("also", "another", "such as", "alternative", "including")):
                    res.recommendation_status = "neutral_mention"
                    res.sentiment_score = 0.15
                else:
                    res.recommendation_status = "neutral_mention"
                    res.sentiment_score = 0.0

            # 4. Visibility Rank and Comparative Position
            rank = cls._detect_list_rank(text, name_clean, domain_clean)
            res.visibility_rank = rank

            if rank == 1 or "ranked #1" in context_to_check or "industry leader" in context_to_check:
                res.comparative_position = "leader"
            elif "alternative" in context_to_check:
                res.comparative_position = "recommended_alternative"
            elif rank and rank > 1:
                res.comparative_position = "contender"
            elif res.recommendation_status == "recommended":
                res.comparative_position = "leader"
            elif res.recommendation_status == "not_recommended":
                res.comparative_position = "unfavorable"
            else:
                res.comparative_position = "mentioned_only"

            res.evaluation_reasoning = (
                f"Brand '{name_clean}' identified in response text. "
                f"Recommendation status evaluated as '{res.recommendation_status}' "
                f"(rank {rank if rank else 'N/A'}, comparative position '{res.comparative_position}')."
            )
        else:
            res.sentiment_score = 0.0
            res.evaluation_reasoning = f"Brand '{name_clean}' was not mentioned in the AI model response."

        # 5. Extract Citations & Source URLs (Strictly evidence-backed)
        extracted_urls = set()

        # URLs in provider metadata (e.g. Google Gemini groundingMetadata)
        if provider_metadata:
            for g_url in provider_metadata.get("grounding_citations", []):
                if isinstance(g_url, str) and g_url.startswith("http"):
                    extracted_urls.add(g_url.strip())

        # Markdown links: [Title](https://...)
        md_links = re.findall(r"\[([^\]]+)\]\((https?://[^\)]+)\)", text)
        for _, link in md_links:
            clean_link = link.strip().rstrip(".,;:")
            extracted_urls.add(clean_link)

        # Plain URLs in text
        plain_urls = re.findall(r"(?:https?://[^\s\)\],>]+)", text)
        for p_url in plain_urls:
            clean_url = p_url.strip().rstrip(".,;:")
            # Basic sanity check
            try:
                parsed = urlparse(clean_url)
                if parsed.scheme in ("http", "https") and parsed.netloc:
                    extracted_urls.add(clean_url)
            except Exception:
                pass

        res.citations = sorted(list(extracted_urls))

        return res

    @staticmethod
    def _detect_list_rank(text: str, brand_name: str, domain: str) -> Optional[int]:
        """Detect 1-indexed position if options/tools are presented as an ordered list."""
        b_lower = brand_name.lower()
        d_lower = domain.lower().split(".")[0]

        # Match lines like "1. **Linear**", "1) Linear", "1. Linear —"
        lines = text.split("\n")
        current_rank = 1
        for line in lines:
            line_strip = line.strip()
            num_match = re.match(r"^(\d+)[\.\)]\s*(.+)", line_strip)
            if num_match:
                item_num = int(num_match.group(1))
                item_content = num_match.group(2).lower()
                if b_lower in item_content or d_lower in item_content:
                    return item_num
                current_rank = item_num + 1

        return None
