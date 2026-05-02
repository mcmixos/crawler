import pytest

from crawler import SitemapParser


_NS_DECL = 'xmlns="http://www.sitemaps.org/schemas/sitemap/0.9"'


def make_fetcher(mapping: dict):
    """Returns a fetcher that maps URL -> text (or None)."""
    calls = []

    async def fetcher(url):
        calls.append(url)
        return mapping.get(url)

    fetcher.calls = calls
    return fetcher


async def test_simple_urlset_returns_locs():
    sitemap = f"""<?xml version='1.0'?>
<urlset {_NS_DECL}>
  <url><loc>https://example.com/a</loc></url>
  <url><loc>https://example.com/b</loc></url>
</urlset>"""
    parser = SitemapParser(make_fetcher({"https://example.com/sitemap.xml": sitemap}))
    urls = await parser.fetch_sitemap("https://example.com/sitemap.xml")
    assert urls == ["https://example.com/a", "https://example.com/b"]


async def test_sitemap_index_recurses():
    index = f"""<?xml version='1.0'?>
<sitemapindex {_NS_DECL}>
  <sitemap><loc>https://example.com/s1.xml</loc></sitemap>
  <sitemap><loc>https://example.com/s2.xml</loc></sitemap>
</sitemapindex>"""
    s1 = f"""<?xml version='1.0'?>
<urlset {_NS_DECL}>
  <url><loc>https://example.com/page1</loc></url>
</urlset>"""
    s2 = f"""<?xml version='1.0'?>
<urlset {_NS_DECL}>
  <url><loc>https://example.com/page2</loc></url>
</urlset>"""
    parser = SitemapParser(make_fetcher({
        "https://example.com/index.xml": index,
        "https://example.com/s1.xml": s1,
        "https://example.com/s2.xml": s2,
    }))
    urls = await parser.fetch_sitemap("https://example.com/index.xml")
    assert sorted(urls) == [
        "https://example.com/page1",
        "https://example.com/page2",
    ]


async def test_handles_fetch_failure():
    parser = SitemapParser(make_fetcher({}))
    urls = await parser.fetch_sitemap("https://example.com/missing.xml")
    assert urls == []


async def test_handles_invalid_xml():
    parser = SitemapParser(make_fetcher({"https://example.com/s.xml": "not xml at all"}))
    urls = await parser.fetch_sitemap("https://example.com/s.xml")
    assert urls == []


async def test_no_recursion_on_repeated_url():
    sitemap = f"""<?xml version='1.0'?>
<urlset {_NS_DECL}>
  <url><loc>https://example.com/a</loc></url>
</urlset>"""
    fetcher = make_fetcher({"https://example.com/s.xml": sitemap})
    parser = SitemapParser(fetcher)
    urls1 = await parser.fetch_sitemap("https://example.com/s.xml")
    urls2 = await parser.fetch_sitemap("https://example.com/s.xml")
    assert urls1 == ["https://example.com/a"]
    assert urls2 == ["https://example.com/a"]


async def test_skips_urls_without_loc():
    sitemap = f"""<?xml version='1.0'?>
<urlset {_NS_DECL}>
  <url><loc>https://example.com/a</loc></url>
  <url></url>
</urlset>"""
    parser = SitemapParser(make_fetcher({"https://example.com/s.xml": sitemap}))
    urls = await parser.fetch_sitemap("https://example.com/s.xml")
    assert urls == ["https://example.com/a"]


async def test_unrecognized_root_returns_empty():
    sitemap = "<?xml version='1.0'?><html><body>not a sitemap</body></html>"
    parser = SitemapParser(make_fetcher({"https://example.com/s.xml": sitemap}))
    urls = await parser.fetch_sitemap("https://example.com/s.xml")
    assert urls == []


async def test_recursion_depth_limit():
    """A self-referencing sitemap index should not loop forever."""
    chain = {}
    for i in range(10):
        chain[f"https://example.com/s{i}.xml"] = f"""<?xml version='1.0'?>
<sitemapindex {_NS_DECL}>
  <sitemap><loc>https://example.com/s{i + 1}.xml</loc></sitemap>
</sitemapindex>"""
    parser = SitemapParser(make_fetcher(chain))
    urls = await parser.fetch_sitemap("https://example.com/s0.xml")
    assert urls == []
