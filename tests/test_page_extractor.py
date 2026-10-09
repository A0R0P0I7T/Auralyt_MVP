import pytest
from app.extractor.page_extractor import extract_page_content
from app.extractor.html_cleaner import clean_html_and_extract_text


SAMPLE_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>Acme AI — Generative Visibility Engine</title>
  <meta name="description" content="Acme AI helps modern brands measure and boost their presence across AI search answers.">
  <link rel="canonical" href="https://acme.ai/">
  <meta property="og:title" content="Acme AI Platform">
  <script type="application/ld+json">
  {
    "@context": "https://schema.org",
    "@type": "Organization",
    "name": "Acme AI Inc.",
    "description": "Leading AI search visibility platform for enterprises.",
    "url": "https://acme.ai"
  }
  </script>
</head>
<body>
  <header>
    <nav><a href="/home">Home</a> <a href="/features">Features</a></nav>
  </header>
  <div class="cookie-banner">Please accept all cookies.</div>
  <main>
    <h1>The Leading AI Visibility Platform</h1>
    <h2>Key Capabilities</h2>
    <p>Acme monitors brand citations across ChatGPT, Perplexity, and Gemini.</p>
    <ul>
      <li>Real-time prompt intelligence</li>
      <li>Competitor share of voice tracking</li>
      <li>Automated gap recommendations</li>
    </ul>
    <a href="/pricing">View Pricing Plans</a>
    <a href="https://twitter.com/acmeai">Follow us on Twitter</a>
  </main>
  <footer>
    <p>&copy; 2026 Acme AI. All rights reserved.</p>
  </footer>
</body>
</html>
"""


def test_clean_html_strips_boilerplate():
    plain, md, chash = clean_html_and_extract_text(SAMPLE_HTML)
    assert "cookie-banner" not in plain.lower()
    assert "Please accept all cookies" not in plain
    assert "The Leading AI Visibility Platform" in plain
    assert "Real-time prompt intelligence" in plain
    assert len(chash) == 64


def test_extract_page_content_structured_data():
    res = extract_page_content(
        html=SAMPLE_HTML,
        requested_url="https://acme.ai",
        final_url="https://acme.ai/",
        http_status=200,
        base_domain="acme.ai"
    )

    assert res["title"] == "Acme AI — Generative Visibility Engine"
    assert "Acme AI helps modern brands" in res["meta_description"]
    assert res["canonical_url"] == "https://acme.ai/"
    assert res["headings"]["h1"] == ["The Leading AI Visibility Platform"]
    assert res["headings"]["h2"] == ["Key Capabilities"]
    assert res["language"] == "en"
    assert res["page_type"] == "homepage"

    # Links
    assert "https://acme.ai/pricing" in res["internal_links"]
    assert "https://twitter.com/acmeai" in res["external_links"]

    # Structured Data
    assert len(res["structured_data"]) == 1
    org = res["structured_data"][0]
    assert org["@type"] == "Organization"
    assert org["name"] == "Acme AI Inc."
