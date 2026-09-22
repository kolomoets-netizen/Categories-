"""Collect website links from a paginated listing page."""

from __future__ import annotations

import re
import time
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import parse_qs, urlencode, urljoin, urlparse, urldefrag, urlunparse

import requests
from bs4 import BeautifulSoup

DEFAULT_HEADERS = {
    # Browser UA: some catalogs (e.g. 1c.ru) are heavy / picky with bots.
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru,en;q=0.9",
}

NEXT_TEXT = (
    "next",
    "следующ",
    "дальше",
    "вперёд",
    "вперед",
    "›",
    "»",
    ">",
    "→",
)

PAGE_PARAMS = (
    "page",
    "p",
    "pagina",
    "paged",
    "offset",
    "start",
    "pageNumber_inp",  # 1c.ru franchise list
    "pageNumber",
    "pagenum",
)

SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "#", "data:")
SKIP_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".css", ".js", ".zip", ".rar", ".doc", ".docx", ".xls", ".xlsx",
)

# Nav / ecosystem links on 1c.ru that are not franchise partner sites
DEFAULT_BLOCKED_HOSTS = {
    "buh.ru",
    "1csoft.ru",
    "www.1c-interes.ru",
    "1c-interes.ru",
    "www.softclub.ru",
    "softclub.ru",
    "v8.1c.ru",
    "its.1c.ru",
    "consulting.1c.ru",
    "dist.1c.ru",
    "solutions.1c.ru",
    "online.1c.ru",
    "edu.1c.ru",
}

# Partner URLs in HTML / JS map balloons (1c.ru embeds them as text)
URL_IN_HTML_RE = re.compile(
    r"""
    (?:
        <small>\s*(https?://[^<]+?)\s*</small>
      | Сайт:\s*<a\s+href=(["']?)(https?://[^\s\"'<>\\]+)
      | href=["'](https?://[^"']+)["'][^>]*>\s*<small>
      | href=(https?://[^\s\"'<>\\]+)[^>]*>\s*https?://
    )
    """,
    re.IGNORECASE | re.VERBOSE,
)


@dataclass
class ListingPage:
    url: str
    status: int | None
    sites: list[str] = field(default_factory=list)
    next_url: str | None = None
    error: str | None = None


@dataclass
class ListingResult:
    start_url: str
    sites: list[str] = field(default_factory=list)
    pages: list[ListingPage] = field(default_factory=list)
    error: str | None = None


class SiteListParser:
    def __init__(
        self,
        timeout: float = 45.0,
        delay: float = 0.8,
        max_pages: int = 100,
        link_selector: str | None = None,
        next_selector: str | None = None,
        page_param: str | None = None,
        external_only: bool = True,
        same_path_prefix: bool = True,
        url_text_only: bool = False,
        blocked_hosts: set[str] | None = None,
        max_html_bytes: int = 8_000_000,
        session: requests.Session | None = None,
    ) -> None:
        self.timeout = timeout
        self.delay = delay
        self.max_pages = max_pages
        self.link_selector = link_selector
        self.next_selector = next_selector
        self.page_param = page_param
        self.external_only = external_only
        self.same_path_prefix = same_path_prefix
        self.url_text_only = url_text_only
        self.blocked_hosts = {h.lower() for h in (blocked_hosts or DEFAULT_BLOCKED_HOSTS)}
        self.max_html_bytes = max_html_bytes
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch(self, url: str) -> tuple[int | None, str, str | None]:
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if ctype and "html" not in ctype and "text" not in ctype and "xml" not in ctype:
                return resp.status_code, "", f"unsupported content-type: {ctype}"
            # Keep enough of huge catalog pages (1c.ru ~2.5MB+)
            return resp.status_code, resp.text[: self.max_html_bytes], None
        except requests.RequestException as exc:
            return None, "", str(exc)

    def normalize_site(self, href: str, base_url: str = "") -> str | None:
        href = (href or "").strip().rstrip("\\")
        href = href.replace('\\"', "").replace("\\'", "")
        if not href or href.lower().startswith(SKIP_SCHEMES):
            return None
        if "://" not in href and base_url:
            absolute = urldefrag(urljoin(base_url, href))[0]
        else:
            absolute = urldefrag(href)[0]
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            return None
        path_l = parsed.path.lower()
        if any(path_l.endswith(ext) for ext in SKIP_EXTENSIONS):
            return None
        host = (parsed.hostname or "").lower()
        if not host:
            return None
        if host in self.blocked_hosts:
            return None
        # Prefer https origin
        scheme = "https" if parsed.scheme in ("http", "https") else parsed.scheme
        return f"https://{host}"

    def _add_site(self, found: list[str], seen: set[str], raw: str, base_url: str, base_host: str) -> None:
        site = self.normalize_site(raw, base_url)
        if not site:
            return
        host = urlparse(site).hostname or ""
        if self.external_only and (host == base_host or host.endswith("." + base_host)):
            return
        if site not in seen:
            seen.add(site)
            found.append(site)

    def extract_sites(self, html: str, page_url: str) -> list[str]:
        base_host = (urlparse(page_url).hostname or "").lower()
        found: list[str] = []
        seen: set[str] = set()

        # 1) Regex: works for JS-embedded map HTML on 1c.ru and similar catalogs
        for match in URL_IN_HTML_RE.finditer(html):
            raw = next((g for g in match.groups() if g and g.startswith("http")), None)
            if raw:
                self._add_site(found, seen, raw, page_url, base_host)

        # Also catch plain <small>http://...</small>
        for match in re.finditer(r"<small>\s*(https?://[^<]+?)\s*</small>", html, re.I):
            self._add_site(found, seen, match.group(1), page_url, base_host)

        # 2) DOM anchors (normal sites)
        soup = BeautifulSoup(html, "lxml")
        if self.link_selector:
            anchors = soup.select(self.link_selector)
        else:
            anchors = soup.find_all("a", href=True)

        for a in anchors:
            href = a.get("href") or ""
            text = a.get_text(" ", strip=True)
            if self.url_text_only and not (
                text.startswith("http://") or text.startswith("https://") or "://" in text
            ):
                # still allow href if it looks like external homepage
                if not href.startswith("http"):
                    continue
            self._add_site(found, seen, href, page_url, base_host)
            if text.startswith("http://") or text.startswith("https://"):
                self._add_site(found, seen, text, page_url, base_host)

        return found

    def find_next_url(self, html: str, page_url: str, page_index: int) -> str | None:
        soup = BeautifulSoup(html or "", "lxml")

        if self.next_selector:
            node = soup.select_one(self.next_selector)
            if node is not None:
                href = node.get("href") or (node.find("a", href=True) or {}).get("href")
                if href:
                    return urldefrag(urljoin(page_url, href))[0]

        if self.page_param:
            return self._next_by_param(page_url, self.page_param, page_index)

        rel_next = soup.find("a", rel=lambda v: v and "next" in v)
        if rel_next and rel_next.get("href"):
            return urldefrag(urljoin(page_url, rel_next["href"]))[0]

        for a in soup.find_all("a", href=True):
            label = " ".join(
                filter(
                    None,
                    [
                        a.get_text(" ", strip=True),
                        a.get("aria-label"),
                        a.get("title"),
                        " ".join(a.get("class") or []),
                    ],
                )
            ).lower()
            if any(h in label for h in NEXT_TEXT):
                candidate = urldefrag(urljoin(page_url, a["href"]))[0]
                if candidate != page_url:
                    return candidate

        parsed = urlparse(page_url)
        qs = parse_qs(parsed.query)
        for key in PAGE_PARAMS:
            if key in qs:
                return self._next_by_param(page_url, key, page_index)

        # Hidden form field pageNumber_inp (1c.ru)
        if html:
            m = re.search(
                r'name=["\']pageNumber_inp["\'][^>]*value=["\']?(\d+)',
                html,
                re.I,
            ) or re.search(
                r'value=["\']?(\d+)["\']?[^>]*name=["\']pageNumber_inp["\']',
                html,
                re.I,
            )
            if m or "pageNumber_inp" in html:
                return self._next_by_param(page_url, "pageNumber_inp", page_index)

        path_next = self._next_by_path(page_url, page_index)
        if path_next:
            return path_next

        current = self._guess_current_page(page_url, page_index)
        for a in soup.find_all("a", href=True):
            text = a.get_text(" ", strip=True)
            if text.isdigit() and int(text) == current + 1:
                return urldefrag(urljoin(page_url, a["href"]))[0]

        return None

    def _next_by_param(self, page_url: str, param: str, page_index: int) -> str:
        parsed = urlparse(page_url)
        qs = parse_qs(parsed.query, keep_blank_values=True)
        current = page_index
        if param in qs and qs[param]:
            try:
                current = int(qs[param][0])
            except ValueError:
                current = page_index
        elif param == "pageNumber_inp":
            # URL may omit the param on first page
            current = page_index
        qs[param] = [str(current + 1)]
        flat = []
        for k, values in qs.items():
            for v in values:
                flat.append((k, v))
        return urlunparse(parsed._replace(query=urlencode(flat)))

    def _next_by_path(self, page_url: str, page_index: int) -> str | None:
        parsed = urlparse(page_url)
        patterns = [
            (r"/page/(\d+)/?", lambda n: f"/page/{n}/"),
            (r"/page-(\d+)/?", lambda n: f"/page-{n}/"),
            (r"/p/(\d+)/?", lambda n: f"/p/{n}/"),
        ]
        for pattern, builder in patterns:
            match = re.search(pattern, parsed.path)
            if match:
                n = int(match.group(1)) + 1
                new_path = re.sub(pattern, builder(n).rstrip("/") + "/", parsed.path, count=1)
                return urlunparse(parsed._replace(path=new_path))
        return None

    def _guess_current_page(self, page_url: str, page_index: int) -> int:
        parsed = urlparse(page_url)
        qs = parse_qs(parsed.query)
        for key in PAGE_PARAMS:
            if key in qs and qs[key]:
                try:
                    return int(qs[key][0])
                except ValueError:
                    pass
        match = re.search(r"/page[/-]?(\d+)", parsed.path)
        if match:
            return int(match.group(1))
        return page_index

    def _requested_page(self, url: str, fallback: int) -> int:
        qs = parse_qs(urlparse(url).query)
        for key in PAGE_PARAMS:
            if key in qs and qs[key]:
                try:
                    return int(qs[key][0])
                except ValueError:
                    pass
        return fallback

    def crawl(self, start_url: str) -> ListingResult:
        start_url = start_url.strip()
        if "://" not in start_url:
            start_url = "https://" + start_url
        # Drop hash
        start_url = urldefrag(start_url)[0]

        # Ensure 1c-style first page has pageNumber_inp
        if "franch-citylist.jsp" in start_url and "pageNumber_inp" not in start_url:
            sep = "&" if "?" in start_url else "?"
            start_url = f"{start_url}{sep}pageNumber_inp=1"
            if self.page_param is None:
                self.page_param = "pageNumber_inp"

        result = ListingResult(start_url=start_url)
        seen_pages: set[str] = set()
        seen_sites: set[str] = set()
        first_page_signature: frozenset[str] | None = None
        url = start_url

        for page_index in range(1, self.max_pages + 1):
            if url in seen_pages:
                break
            seen_pages.add(url)

            if page_index > 1 and self.delay:
                time.sleep(self.delay)

            status, html, error = self.fetch(url)
            page = ListingPage(url=url, status=status, error=error)
            if not html:
                result.pages.append(page)
                break

            sites = self.extract_sites(html, url)
            page.sites = sites
            sig = frozenset(sites)

            requested = self._requested_page(url, page_index)
            # 1c.ru resets invalid/high pageNumber_inp back to page 1
            if page_index > 1 and first_page_signature is not None and sig == first_page_signature:
                page.error = "page content repeated (likely end of pagination)"
                result.pages.append(page)
                break
            if page_index == 1:
                first_page_signature = sig

            for site in sites:
                if site not in seen_sites:
                    seen_sites.add(site)
                    result.sites.append(site)

            next_url = self.find_next_url(html, url, requested)
            page.next_url = next_url
            result.pages.append(page)

            if not next_url or next_url in seen_pages:
                break
            if not sites and page_index > 1:
                break
            url = next_url

        return result


def write_sites_txt(path: str, sites: Iterable[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for site in sites:
            f.write(site + "\n")
