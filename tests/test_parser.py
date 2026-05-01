import pytest
from bs4 import BeautifulSoup

from crawler import HTMLParser


@pytest.fixture
def parser():
    return HTMLParser()


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "lxml")


async def test_parse_html_returns_full_structure(parser):
    html = (
        "<html><head><title>Title</title>"
        "<meta name='description' content='desc'>"
        "<meta name='keywords' content='a, b'></head>"
        "<body><a href='/x'>link</a> hello</body></html>"
    )
    result = await parser.parse_html(html, "https://example.com")
    assert result["url"] == "https://example.com"
    assert result["title"] == "Title"
    assert "hello" in result["text"]
    assert "https://example.com/x" in result["links"]
    assert result["metadata"] == {
        "title": "Title",
        "description": "desc",
        "keywords": "a, b",
    }


async def test_parse_html_handles_empty_html(parser):
    result = await parser.parse_html("", "https://example.com")
    assert result["url"] == "https://example.com"
    assert result["title"] is None
    assert result["text"] == ""
    assert result["links"] == []
    assert result["metadata"] == {
        "title": None,
        "description": None,
        "keywords": None,
    }


async def test_parse_html_handles_malformed_html(parser):
    html = "<html><body><a href='/x'>broken<div></span></html>"
    result = await parser.parse_html(html, "https://example.com")
    assert result["url"] == "https://example.com"
    assert isinstance(result["links"], list)
    assert isinstance(result["text"], str)
    assert "https://example.com/x" in result["links"]


def test_extract_links_resolves_relative(parser):
    soup = make_soup("<a href='/foo'>x</a><a href='bar'>y</a>")
    links = parser.extract_links(soup, "https://example.com/sub/page")
    assert "https://example.com/foo" in links
    assert "https://example.com/sub/bar" in links


def test_extract_links_keeps_absolute(parser):
    soup = make_soup("<a href='https://other.com/page'>x</a>")
    assert parser.extract_links(soup, "https://example.com") == ["https://other.com/page"]


def test_extract_links_filters_invalid_schemes(parser):
    html = (
        "<a href='javascript:void(0)'>1</a>"
        "<a href='mailto:a@b.c'>2</a>"
        "<a href='tel:+123'>3</a>"
        "<a href='#anchor'>4</a>"
        "<a href=''>5</a>"
        "<a href='https://example.com/ok'>6</a>"
    )
    soup = make_soup(html)
    assert parser.extract_links(soup, "https://example.com") == ["https://example.com/ok"]


def test_extract_links_dedupes(parser):
    soup = make_soup("<a href='/a'>1</a><a href='/a'>2</a>")
    assert parser.extract_links(soup, "https://example.com") == ["https://example.com/a"]


def test_extract_links_same_domain_only(parser):
    soup = make_soup("<a href='/x'>1</a><a href='https://other.com/y'>2</a>")
    links = parser.extract_links(soup, "https://example.com", same_domain_only=True)
    assert links == ["https://example.com/x"]


def test_extract_text_ignores_script_and_style(parser):
    html = (
        "<html><head><style>body{color:red}</style></head>"
        "<body>visible<script>alert(1)</script>"
        "<noscript>fallback</noscript> more text</body></html>"
    )
    soup = make_soup(html)
    text = parser.extract_text(soup)
    assert "visible" in text
    assert "more text" in text
    assert "alert" not in text
    assert "color:red" not in text
    assert "fallback" not in text


def test_extract_text_with_selector(parser):
    soup = make_soup("<div class='main'>main content</div><p>other</p>")
    assert parser.extract_text(soup, ".main") == "main content"


def test_extract_text_selector_no_match(parser):
    soup = make_soup("<p>text</p>")
    assert parser.extract_text(soup, ".missing") == ""


def test_extract_metadata_full(parser):
    html = (
        "<head><title>T</title>"
        "<meta name='description' content='D'>"
        "<meta name='keywords' content='k1, k2'></head>"
    )
    soup = make_soup(html)
    assert parser.extract_metadata(soup) == {
        "title": "T",
        "description": "D",
        "keywords": "k1, k2",
    }


def test_extract_metadata_missing_fields(parser):
    soup = make_soup("<head></head>")
    assert parser.extract_metadata(soup) == {
        "title": None,
        "description": None,
        "keywords": None,
    }


def test_extract_metadata_empty_content(parser):
    html = "<head><title>  </title><meta name='description' content='  '></head>"
    soup = make_soup(html)
    result = parser.extract_metadata(soup)
    assert result["title"] is None
    assert result["description"] is None


def test_extract_images_resolves_relative(parser):
    html = "<img src='/img.png' alt='pic'><img src='https://cdn.com/x.jpg'>"
    soup = make_soup(html)
    images = parser.extract_images(soup, "https://example.com/p")
    assert {"src": "https://example.com/img.png", "alt": "pic"} in images
    assert {"src": "https://cdn.com/x.jpg", "alt": ""} in images


def test_extract_images_skips_no_src(parser):
    soup = make_soup("<img alt='no src'><img src=''>")
    assert parser.extract_images(soup, "https://example.com") == []


def test_extract_headings_all_levels(parser):
    html = "<h1>A</h1><h2>B</h2><h2>B2</h2><h3>C</h3><h4>ignored</h4>"
    soup = make_soup(html)
    assert parser.extract_headings(soup) == {
        "h1": ["A"],
        "h2": ["B", "B2"],
        "h3": ["C"],
    }


def test_extract_headings_empty(parser):
    soup = make_soup("<p>nothing</p>")
    assert parser.extract_headings(soup) == {"h1": [], "h2": [], "h3": []}


def test_extract_tables_simple(parser):
    html = (
        "<table><tr><th>h1</th><th>h2</th></tr>"
        "<tr><td>a</td><td>b</td></tr></table>"
    )
    soup = make_soup(html)
    assert parser.extract_tables(soup) == [[["h1", "h2"], ["a", "b"]]]


def test_extract_tables_skips_empty(parser):
    soup = make_soup("<table></table>")
    assert parser.extract_tables(soup) == []


def test_extract_lists_ul_and_ol(parser):
    html = "<ul><li>a</li><li>b</li></ul><ol><li>1</li><li>2</li></ol>"
    soup = make_soup(html)
    assert parser.extract_lists(soup) == [
        {"type": "ul", "items": ["a", "b"]},
        {"type": "ol", "items": ["1", "2"]},
    ]


def test_extract_lists_skips_empty(parser):
    soup = make_soup("<ul></ul>")
    assert parser.extract_lists(soup) == []
