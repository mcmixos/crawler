import asyncio
import logging
from typing import Optional
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

_VALID_SCHEMES = {"http", "https"}
_TEXT_NOISE_TAGS = ("script", "style", "noscript")


class HTMLParser:
    """HTML parser that extracts structured data from web pages."""

    async def parse_html(self, html: str, url: str) -> dict:
        """Parse HTML and return {url, title, text, links, metadata}."""
        try:
            soup = await asyncio.to_thread(BeautifulSoup, html, "lxml")
        except Exception as exc:
            logger.error("Failed to parse HTML for %s: %s", url, exc)
            return self._empty_result(url)

        metadata = self.extract_metadata(soup)
        return {
            "url": url,
            "title": metadata.get("title"),
            "text": self.extract_text(soup),
            "links": self.extract_links(soup, url),
            "metadata": metadata,
        }

    def extract_links(
        self,
        soup: BeautifulSoup,
        base_url: str,
        same_domain_only: bool = False,
    ) -> list[str]:
        try:
            base_host = urlparse(base_url).netloc.lower()
            seen: set[str] = set()
            links: list[str] = []
            for tag in soup.find_all("a", href=True):
                href = (tag.get("href") or "").strip()
                if not href or href.startswith("#"):
                    continue
                absolute = urljoin(base_url, href)
                parsed = urlparse(absolute)
                if parsed.scheme not in _VALID_SCHEMES or not parsed.netloc:
                    continue
                if same_domain_only and parsed.netloc.lower() != base_host:
                    continue
                if absolute in seen:
                    continue
                seen.add(absolute)
                links.append(absolute)
            return links
        except Exception as exc:
            logger.warning("extract_links failed for %s: %s", base_url, exc)
            return []

    def extract_text(
        self,
        soup: BeautifulSoup,
        selector: Optional[str] = None,
    ) -> str:
        """Extract visible text. Mutates soup: removes <script>/<style>/<noscript> tags."""
        try:
            if selector is not None:
                target = soup.select_one(selector)
                if target is None:
                    return ""
            else:
                target = soup
            for tag in target.find_all(_TEXT_NOISE_TAGS):
                tag.decompose()
            return target.get_text(separator=" ", strip=True)
        except Exception as exc:
            logger.warning("extract_text failed: %s", exc)
            return ""

    def extract_metadata(self, soup: BeautifulSoup) -> dict:
        try:
            title_tag = soup.find("title")
            title = title_tag.get_text(strip=True) if title_tag else None
            return {
                "title": title or None,
                "description": self._meta_content(soup, "description"),
                "keywords": self._meta_content(soup, "keywords"),
            }
        except Exception as exc:
            logger.warning("extract_metadata failed: %s", exc)
            return {"title": None, "description": None, "keywords": None}

    def extract_images(
        self,
        soup: BeautifulSoup,
        base_url: str,
    ) -> list[dict]:
        try:
            images: list[dict] = []
            for img in soup.find_all("img"):
                src = (img.get("src") or "").strip()
                if not src:
                    continue
                absolute = urljoin(base_url, src)
                scheme = urlparse(absolute).scheme
                if scheme not in _VALID_SCHEMES and scheme != "data":
                    continue
                images.append({
                    "src": absolute,
                    "alt": (img.get("alt") or "").strip(),
                })
            return images
        except Exception as exc:
            logger.warning("extract_images failed for %s: %s", base_url, exc)
            return []

    def extract_headings(self, soup: BeautifulSoup) -> dict[str, list[str]]:
        try:
            return {
                level: [
                    tag.get_text(separator=" ", strip=True)
                    for tag in soup.find_all(level)
                ]
                for level in ("h1", "h2", "h3")
            }
        except Exception as exc:
            logger.warning("extract_headings failed: %s", exc)
            return {"h1": [], "h2": [], "h3": []}

    def extract_tables(self, soup: BeautifulSoup) -> list[list[list[str]]]:
        try:
            tables: list[list[list[str]]] = []
            for table in soup.find_all("table"):
                rows: list[list[str]] = []
                for tr in table.find_all("tr"):
                    cells = [
                        cell.get_text(separator=" ", strip=True)
                        for cell in tr.find_all(("td", "th"))
                    ]
                    if cells:
                        rows.append(cells)
                if rows:
                    tables.append(rows)
            return tables
        except Exception as exc:
            logger.warning("extract_tables failed: %s", exc)
            return []

    def extract_lists(self, soup: BeautifulSoup) -> list[dict]:
        try:
            result: list[dict] = []
            for tag in soup.find_all(("ul", "ol")):
                items = [
                    li.get_text(separator=" ", strip=True)
                    for li in tag.find_all("li", recursive=False)
                ]
                if items:
                    result.append({"type": tag.name, "items": items})
            return result
        except Exception as exc:
            logger.warning("extract_lists failed: %s", exc)
            return []

    @staticmethod
    def _meta_content(soup: BeautifulSoup, name: str) -> Optional[str]:
        tag = soup.find("meta", attrs={"name": name})
        if tag is None:
            return None
        content = tag.get("content")
        if content is None:
            return None
        return content.strip() or None

    @staticmethod
    def _empty_result(url: str) -> dict:
        return {
            "url": url,
            "title": None,
            "text": "",
            "links": [],
            "metadata": {"title": None, "description": None, "keywords": None},
        }
