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

from app.core.brand_identity import registrable_domain, registrable_label


class EvaluationResult(BaseModel):
    """Structured evaluation of a single AI model response."""
    brand_mentioned: bool = False
    mention_context: Optional[str] = None
    mention_confidence: str = "high"       # high, uncertain, rejected_homonym
    recommendation_status: str = "unknown"  # recommended, neutral_mention, not_recommended, not_mentioned, unknown
    competitor_mentions: List[str] = Field(default_factory=list)
    comparative_position: str = "unknown"   # leader, recommended_alternative, contender, mentioned_only, unfavorable, not_mentioned, unknown
    citations: List[str] = Field(default_factory=list)
    provider_citations: List[str] = Field(default_factory=list)
    response_citations: List[str] = Field(default_factory=list)
    target_brand_citations: List[str] = Field(default_factory=list)  # Verified URLs strictly belonging to target brand domain
    competitor_citations: List[str] = Field(default_factory=list)    # Third-party / competitor domain URLs
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
    "openrouter": ["Together AI", "Groq", "Fireworks AI", "AWS Bedrock", "LiteLLM", "DeepInfra", "Anyscale"],
    "aurora": ["LangChain", "CrewAI", "AutoGen", "Semantic Kernel"],
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
    r"\bleads\s+(?:the|in)\b",
    r"\bmarket\s+leader\b",
    r"\b(?:highest|top)[-\s]rated\b",
    r"\bpremier\s+(?:choice|platform|tool|solution|option)\b",
    r"\bideal\s+for\b",
    r"\bgreat\s+(?:choice|option|solution|fit)\b",
    r"\branked\s+#?1\b",
    r"\bnumber\s+one\b",
]

# Negative recommendation patterns
NEGATIVE_RECOMMENDATION_PATTERNS = [
    r"\b(?:do\s+not|don\'t|would\s+not|wouldn\'t|never|cannot)\s+(?:recommend|choose|suggest)\b",
    r"\bnot\s+recommended\b",
    r"\bnot\s+(?:the\s+)?(?:best|top|ideal|leading|first)\s+(?:choice|option|pick|solution|tool|platform)\b",
    r"\bnot\s+(?:designed|suited|suitable|intended|built)\s+for\b",
    r"\bdoes\s+not\s+support\b",
    r"\bavoid\b",
    r"\bfalls\s+short\b",
    r"\blacks\s+(?:essential|critical|key|modern)\b",
    r"\boutdated\b",
    r"\binferior\b",
    r"\blagging\s+behind\b",
    r"\bdrawbacks?\b",
    r"\bsteep\s+learning\s+curve\s+with\s+poor\b",
    r"\bexpensive\s+with\s+limited\b",
]


# Context-sensitive dictionary-word brand disambiguation (DEF-E3-02)
COMMON_DICTIONARY_BRAND_NAMES: Dict[str, Dict[str, Any]] = {
    "linear": {
        "negative_collocations": [
            r"\blinear\s+(?:regression|algebra|equation|equations|programming|model|models|combination|combinations|transformation|transformations|interpolation|relationship|relationships|scaling|workflow|workflows|fashion|momentum|curve|curves|time|feet|foot|meter|meters|inch|inches|filter|filters)\b",
            r"\b(?:simple|multiple|generalized|piecewise|non-?|sub-?)\s+linear\b",
        ],
        "positive_context": [
            r"\b(?:app|software|tool|tools|platform|platforms|issue|issues|tracker|tracking|ticket|tickets|kanban|sprint|sprints|backlog|developer|developers|engineering|velocity|project\s+management|jira|asana|shortcut|trello)\b"
        ]
    },
    "scale": {
        "negative_collocations": [
            r"\bscale\s+(?:up|down|out|in|to|of|large|small|economic)\b",
            r"\b(?:at|to|on\s+a|large|small|time|gray|grayscale|economies\s+of)\s+scale\b",
        ],
        "positive_context": [
            r"\b(?:ai|data|annotation|labeling|rlhf|model|models|training|synthetic|dataset|datasets|api|platform|software)\b"
        ]
    },
    "base": {
        "negative_collocations": [
            r"\bbase\s+(?:model|models|rate|rates|price|prices|case|cases|salary|salaries|class|classes|station|stations)\b",
            r"\b(?:data|code|knowledge|user|customer)\s*base\b",
        ],
        "positive_context": [
            r"\b(?:coinbase|ethereum|l2|layer\s*2|crypto|blockchain|protocol|smart\s+contract)\b"
        ]
    },
    "target": {
        "negative_collocations": [
            r"\btarget\s+(?:audience|audiences|market|markets|user|users|group|groups|demographic|demographics|customer|customers|language|languages|price|goal|goals)\b",
            r"\b(?:on|hit\s+the|meet\s+the)\s+target\b",
        ],
        "positive_context": [
            r"\b(?:store|stores|retail|retailer|shopping|redcard|walmart|amazon)\b"
        ]
    },
    "box": {
        "negative_collocations": [
            r"\b(?:in\s+a|out\s+of\s+the|dialog|checkbox|text|search|inbox|black|white|shadow)\s*box\b",
            r"\bbox\s+(?:office|plot|plots|score|scores)\b",
        ],
        "positive_context": [
            r"\b(?:cloud|storage|files|content|dropbox|onedrive|sharepoint|enterprise)\b"
        ]
    }
}


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
        if not name_clean:
            res.evaluation_reasoning = "Target brand identity is missing; mention classification is unavailable."
            res.recommendation_status = "unknown"
            res.comparative_position = "unknown"
            return res
        parsed_domain = urlparse(brand_domain if "://" in brand_domain else f"https://{brand_domain}")
        domain_clean = (parsed_domain.hostname or brand_domain).replace("www.", "").strip().lower()
        root_domain = registrable_domain(domain_clean)
        domain_host = registrable_label(domain_clean)
        # Names shorter than 3 characters (e.g. "In") are ordinary words; only the domain identifies the brand.
        name_usable = len(name_clean) >= 3

        # Regex for word-boundary brand mention
        escaped_name = re.escape(name_clean) if name_usable else r"(?!)"
        escaped_domain = re.escape(root_domain)
        escaped_host = re.escape(domain_host) if len(domain_host) >= 4 else r"(?!)"

        # Check domain presence directly (domain mention is always unambiguous)
        domain_pattern = re.compile(rf"\b{escaped_domain}\b", re.IGNORECASE)
        domain_match = domain_pattern.search(clean_text)

        # Check name presence
        name_pattern = re.compile(rf"\b{escaped_name}\b", re.IGNORECASE)
        name_matches = list(name_pattern.finditer(clean_text))

        is_dict_word = name_clean.lower() in COMMON_DICTIONARY_BRAND_NAMES
        mention_valid = False
        valid_match = None

        if domain_match:
            mention_valid = True
            valid_match = domain_match
            res.mention_confidence = "high"
        elif name_matches:
            if is_dict_word:
                dict_cfg = COMMON_DICTIONARY_BRAND_NAMES[name_clean.lower()]
                neg_pats = dict_cfg.get("negative_collocations", [])
                pos_pats = dict_cfg.get("positive_context", [])
                has_text_software_context = any(re.search(p, clean_text, re.IGNORECASE) for p in pos_pats)

                valid_name_matches = []
                for nm in name_matches:
                    start_ctx = max(0, nm.start() - 60)
                    end_ctx = min(len(clean_text), nm.end() + 60)
                    window = clean_text[start_ctx:end_ctx].lower()

                    is_neg = any(re.search(pat, window) for pat in neg_pats)
                    if is_neg:
                        continue

                    # If word is lowercase in mixed-case text and no positive context, skip
                    matched_str = nm.group(0)
                    if matched_str.islower() and not has_text_software_context:
                        continue

                    valid_name_matches.append(nm)

                if valid_name_matches:
                    mention_valid = True
                    valid_match = valid_name_matches[0]
                    res.mention_confidence = "high" if has_text_software_context else "uncertain"
                else:
                    res.mention_confidence = "rejected_homonym"
                    res.brand_mentioned = False
                    res.recommendation_status = "not_mentioned"
                    res.comparative_position = "not_mentioned"
                    res.evaluation_reasoning = f"The term '{name_clean}' was detected only as a common dictionary homonym or technical term; target brand not mentioned."
            else:
                mention_valid = True
                valid_match = name_matches[0]
                res.mention_confidence = "high"
        elif len(domain_host) >= 4:
            host_pattern = re.compile(rf"\b{escaped_host}\b", re.IGNORECASE)
            host_match = host_pattern.search(clean_text)
            if host_match and not is_dict_word:
                mention_valid = True
                valid_match = host_match
                res.mention_confidence = "high"

        if mention_valid and valid_match:
            res.brand_mentioned = True
            start_pos = max(0, valid_match.start() - 60)
            end_pos = min(len(clean_text), valid_match.end() + 140)
            snippet = clean_text[start_pos:end_pos].strip()

            if start_pos > 0 and not snippet.startswith((".", "!", "?")):
                snippet = "..." + snippet
            if end_pos < len(clean_text) and not snippet.endswith((".", "!", "?")):
                snippet = snippet + "..."
            res.mention_context = snippet
        elif res.mention_confidence != "rejected_homonym":
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

        # Detect competitors in text using word boundaries, strictly filtering out target brand & variants
        for comp in candidates:
            c_low = comp.lower()
            if (c_low == target_brand_lower or
                (name_usable and (target_brand_lower in c_low or c_low in target_brand_lower)) or
                domain_host.lower() in c_low):
                continue
            comp_pattern = re.compile(rf"\b{re.escape(comp)}\b", re.IGNORECASE)
            if comp_pattern.search(clean_text) and comp not in detected_competitors:
                detected_competitors.append(comp)

        # Also extract structured list items that might be named competitors
        list_items = re.findall(r"(?:^|\n)\s*(?:\d+[\.\)]|\*|\-)\s+([A-Za-z0-9\.\-\s]{2,30}?)(?:—|–|-|:|\s{2,}|\n)", text)
        for item in list_items:
            item_clean = item.strip().replace("**", "")
            i_low = item_clean.lower()
            if (i_low == target_brand_lower or
                (name_usable and target_brand_lower in i_low) or
                domain_host.lower() in i_low):
                continue
            if 2 <= len(item_clean) <= 25:
                # Disallow generic words
                if not any(g in i_low for g in ("option", "feature", "summary", "conclusion", "pricing", "alternative", "step", "reason", "overview", "introduction")):
                    if item_clean not in detected_competitors and i_low not in [c.lower() for c in detected_competitors]:
                        detected_competitors.append(item_clean)

        res.competitor_mentions = detected_competitors[:10]

        # 3. Recommendation & Endorsement Analysis (Clause-Level Attribution)
        if res.brand_mentioned:
            rank = cls._detect_list_rank(text, name_clean, root_domain)
            res.visibility_rank = rank

            # Break text into lines and sentences
            sentences = []
            for line in text.split("\n"):
                line_str = line.strip()
                if not line_str:
                    continue
                sents = re.split(r"(?<=[.!?])\s+", line_str)
                sentences.extend(sents)

            brand_sentences = [s for s in sentences if re.search(rf"\b({escaped_name}|{escaped_domain})\b", s, re.IGNORECASE)]

            has_negative = False
            has_positive = False
            comparative_dispreferred = False

            # Check comparative preference expressions across the entire text
            # e.g., "prefer [Competitor] over [Brand]", "recommend [Competitor] instead of [Brand]"
            for comp in detected_competitors:
                pref_pattern = re.compile(
                    rf"\b(?:prefer|recommend|choose)\s+{re.escape(comp)}\s+(?:over|instead\s+of|rather\s+than)\s+{re.escape(name_clean)}\b",
                    re.IGNORECASE
                )
                if pref_pattern.search(clean_text):
                    comparative_dispreferred = True
                    break

            for sent in brand_sentences:
                sent_clean = sent.replace("**", "").replace("*", "")
                sent_lower = sent_clean.lower()

                if any(re.search(pat, sent_lower) for pat in NEGATIVE_RECOMMENDATION_PATTERNS):
                    has_negative = True

                # Split sentence into clauses to prevent attributing competitor endorsements to brand
                # Clause splitters: commas, semicolons, dashes, and contrastive markers
                clauses = [c.strip() for c in re.split(r"[,;—–]|\b(?:while|although|whereas|however|but|yet|despite|in contrast)\b", sent_clean, flags=re.IGNORECASE) if c.strip()]
                if not clauses:
                    clauses = [sent_clean]

                for clause in clauses:
                    c_lower = clause.lower()
                    has_brand_in_clause = bool(re.search(rf"\b({escaped_name}|{escaped_domain})\b", c_lower, re.IGNORECASE))
                    has_comp_in_clause = any(bool(re.search(rf"\b{re.escape(c.lower())}\b", c_lower)) for c in detected_competitors)

                    # Check for positive recommendation patterns in this clause
                    for pat in POSITIVE_RECOMMENDATION_PATTERNS:
                        m = re.search(pat, c_lower)
                        if m:
                            if has_comp_in_clause and not has_brand_in_clause:
                                # Endorsement strictly belongs to competitor clause
                                continue
                            elif has_comp_in_clause and has_brand_in_clause:
                                # Both in clause: check who is the subject of the superlative
                                pat_end = m.end()
                                after_pat = c_lower[pat_end:]
                                before_pat = c_lower[:m.start()]
                                comp_is_subject = any(
                                    re.search(rf"\b{re.escape(c.lower())}\b", before_pat) or
                                    re.search(rf"\b{re.escape(c.lower())}\b", after_pat)
                                    for c in detected_competitors
                                )
                                brand_is_subject = bool(re.search(rf"\b{escaped_name.lower()}\b", before_pat) or re.search(rf"\b{escaped_name.lower()}\b", after_pat))
                                if comp_is_subject and not brand_is_subject:
                                    continue
                                has_positive = True
                            elif has_brand_in_clause:
                                has_positive = True

            # If brand is ranked #1 in an ordered list without negative remarks
            if rank == 1 and not has_negative:
                has_positive = True

            # If brand was dispreferred in comparison
            if comparative_dispreferred:
                has_positive = False

            context_to_check = (res.mention_context or clean_text).lower()

            if has_negative:
                res.recommendation_status = "not_recommended"
                res.sentiment_score = -0.75
                res.comparative_position = "unfavorable"
            elif has_positive:
                res.recommendation_status = "recommended"
                res.sentiment_score = 0.85
                if rank == 1 or "ranked #1" in context_to_check or "industry leader" in context_to_check or "market leader" in context_to_check:
                    res.comparative_position = "leader"
                elif "alternative" in context_to_check:
                    res.comparative_position = "recommended_alternative"
                else:
                    res.comparative_position = "leader"
            else:
                res.recommendation_status = "neutral_mention"
                res.sentiment_score = 0.0
                if rank and rank > 1:
                    res.comparative_position = "contender"
                elif comparative_dispreferred:
                    res.comparative_position = "contender"
                elif detected_competitors and any(re.search(pat, clean_text.lower()) for pat in POSITIVE_RECOMMENDATION_PATTERNS):
                    # Competitor is recommended while target brand is merely mentioned
                    res.comparative_position = "contender"
                elif "alternative" in context_to_check:
                    res.comparative_position = "contender"
                else:
                    res.comparative_position = "mentioned_only"

            res.evaluation_reasoning = (
                f"Brand '{name_clean}' identified in response text. "
                f"Recommendation status evaluated as '{res.recommendation_status}' "
                f"(rank {rank if rank else 'N/A'}, comparative position '{res.comparative_position}')."
            )
        elif res.mention_confidence != "rejected_homonym":
            res.sentiment_score = 0.0
            res.recommendation_status = "not_mentioned"
            res.comparative_position = "not_mentioned"
            res.evaluation_reasoning = f"Brand '{name_clean}' was not mentioned in the AI model response."

        # 4. Extract Citations & Source URLs (Strictly evidence-backed & validated)
        extracted_urls = set()

        def _clean_and_validate_url(candidate_url: str) -> Optional[str]:
            if not candidate_url or not isinstance(candidate_url, str):
                return None
            url = candidate_url.strip().rstrip(".,;:)'\"]>")
            if not (url.startswith("http://") or url.startswith("https://")):
                return None
            try:
                parsed = urlparse(url)
                if parsed.scheme in ("http", "https") and parsed.netloc:
                    if "." in parsed.netloc or parsed.netloc.lower() == "localhost":
                        return url
            except Exception:
                pass
            return None

        provider_citations = set()
        if provider_metadata:
            for g_url in provider_metadata.get("grounding_citations", []):
                valid_u = _clean_and_validate_url(g_url)
                if valid_u:
                    provider_citations.add(valid_u)

        # Markdown links: [Title](https://...)
        md_links = re.findall(r"\[([^\]]+)\]\((https?://[^\)]+)\)", text)
        for _, link in md_links:
            valid_u = _clean_and_validate_url(link)
            if valid_u:
                extracted_urls.add(valid_u)

        # Plain URLs in text
        plain_urls = re.findall(r"(?:https?://[^\s\)\],>]+)", text)
        for p_url in plain_urls:
            valid_u = _clean_and_validate_url(p_url)
            if valid_u:
                extracted_urls.add(valid_u)

        all_citations = sorted(provider_citations | extracted_urls)
        res.provider_citations = sorted(provider_citations)
        res.response_citations = sorted(extracted_urls)
        res.citations = all_citations

        # Isolate target brand domain citations from competitor/third-party citations (DEF-E3-01)
        target_citations = []
        competitor_citations = []
        for u in all_citations:
            try:
                u_parsed = urlparse(u)
                u_host = (u_parsed.netloc or "").split(":")[0].strip().rstrip(".").lower()
                target_host = root_domain.strip().rstrip(".").lower()
                if u_host == target_host or u_host.endswith("." + target_host):
                    target_citations.append(u)
                else:
                    competitor_citations.append(u)
            except Exception:
                competitor_citations.append(u)

        res.target_brand_citations = sorted(target_citations)
        res.competitor_citations = sorted(competitor_citations)

        return res

    @staticmethod
    def _detect_list_rank(text: str, brand_name: str, domain: str) -> Optional[int]:
        """Detect 1-indexed position if options/tools are presented as an ordered list."""
        b_lower = brand_name.lower()
        d_lower = domain.lower().split(".")[0]
        alternatives = [re.escape(d_lower)]
        if len(b_lower) >= 3:
            alternatives.insert(0, re.escape(b_lower))
        title_pattern = re.compile(rf"\b({'|'.join(alternatives)})\b")

        lines = text.split("\n")
        for line in lines:
            line_strip = line.strip()
            num_match = re.match(r"^(\d+)[\.\)]\s*(.+)", line_strip)
            if num_match:
                item_num = int(num_match.group(1))
                item_content = num_match.group(2)
                # Subject/heading of the list item: before '—', '–', '-', ':', or inside '**...**'
                bold_match = re.match(r"^\*\*([^*]+)\*\*", item_content)
                if bold_match:
                    title = bold_match.group(1).lower()
                else:
                    title = re.split(r"[—–\:\-]", item_content)[0].lower()

                # Brand must be in the title/subject of the item, not just mentioned in comparison text
                brand_in_title = bool(title_pattern.search(title))
                if brand_in_title:
                    return item_num

        return None
