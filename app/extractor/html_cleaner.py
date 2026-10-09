"""HTML text and structure cleaner.
Removes boilerplates, scripts, navigation, footers, and cookie banners
while preserving meaningful headings, lists, and paragraphs.
"""
import hashlib
import re
from typing import Tuple, List
from bs4 import BeautifulSoup, Comment
import markdownify


BOILERPLATE_TAGS = [
    "script", "style", "noscript", "svg", "iframe", "video", "audio",
    "canvas", "map", "object", "embed", "applet"
]

BOILERPLATE_SELECTORS = [
    "header", "footer", "nav",
    "[role='navigation']", "[role='banner']", "[role='contentinfo']",
    "#cookie-banner", ".cookie-banner", "#cookie-notice", ".cookie-notice",
    "#cookie-consent", ".cookie-consent", ".consent-modal", "#consent-banner",
    ".gdpr-banner", "#gdpr-modal", ".footer-links", ".nav-menu", ".sidebar-nav"
]


def clean_html_and_extract_text(html: str) -> Tuple[str, str, str]:
    """
    Cleans raw HTML and extracts:
    1. Clean readable text
    2. Markdown formatted text
    3. Content SHA256 hash

    Returns:
        (plain_text, markdown_text, content_hash)
    """
    if not html:
        return "", "", hashlib.sha256(b"").hexdigest()

    # Bound maximum HTML length passed to parser to prevent parser memory exhaustion
    max_html_chars = 5 * 1024 * 1024
    if len(html) > max_html_chars:
        html = html[:max_html_chars]

    content_hash = hashlib.sha256(html.encode("utf-8", errors="ignore")).hexdigest()

    soup = BeautifulSoup(html, "lxml")

    # Remove all HTML comments
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    # Remove script, style, noscript tags
    for tag_name in BOILERPLATE_TAGS:
        for tag in soup.find_all(tag_name):
            tag.decompose()

    # Remove obvious navigation/footer/cookie banner elements
    for selector in BOILERPLATE_SELECTORS:
        try:
            for el in soup.select(selector):
                el.decompose()
        except Exception:
            pass

    # Extract clean text from body or entire soup
    target = soup.body if soup.body else soup

    # Get Markdown text using markdownify with stripped whitespace
    try:
        clean_html_str = str(target)
        md_text = markdownify.markdownify(
            clean_html_str,
            heading_style="ATX",
            strip=["a", "img"],
            bullets="-"
        )
        # Collapse excessive newlines
        md_text = re.sub(r"\n{3,}", "\n\n", md_text).strip()
    except Exception:
        md_text = ""

    # Get plain readable text
    raw_text = target.get_text(separator="\n", strip=True)
    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    plain_text = "\n".join(lines)

    return plain_text, md_text, content_hash
