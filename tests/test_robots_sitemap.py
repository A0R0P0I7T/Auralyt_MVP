import pytest
from app.crawler.robots import RobotsPolicy
from app.crawler.sitemap import score_url_priority


def test_robots_policy_parsing():
    robots_text = """
User-agent: *
Disallow: /admin/
Disallow: /private/
Crawl-delay: 2.5
Sitemap: https://example.com/sitemap.xml
Sitemap: https://example.com/sitemap_products.xml
"""
    policy = RobotsPolicy("https://example.com")
    policy._parse_content("https://example.com/robots.txt", robots_text)

    assert policy.crawl_delay == 2.5
    assert len(policy.sitemaps) == 2
    assert "https://example.com/sitemap.xml" in policy.sitemaps
    assert policy.is_allowed("https://example.com/about")
    assert not policy.is_allowed("https://example.com/admin/settings")
    assert not policy.is_allowed("https://example.com/private/data")


def test_sitemap_priority_scoring():
    assert score_url_priority("https://example.com/pricing") == 1
    assert score_url_priority("https://example.com/product/features") == 1
    assert score_url_priority("https://example.com/about-us") == 1
    assert score_url_priority("https://example.com/blog/2026/01/news-update-post-123") == 2
