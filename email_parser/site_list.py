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
    "User-Agent": (
        "PartnerSiteListParser/1.0 (+https://localhost; partner catalog crawler)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru,en;q=0.8",
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

SKIP_SCHEMES = ("mailto:", "tel:", "javascript:", "#", "data:")
SKIP_EXTENSIONS = (
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp",
    ".css", ".js", ".zip", ".rar", ".doc", ".docx", ".xls", ".xlsx",
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
        timeout: float = 15.0,
        delay: float = 0.5,
        max_pages: int = 100,
        link_selector: str | None = None,
        next_selector: str | None = None,
        page_param: str | None = None,
        external_only: bool = True,
        same_path_prefix: bool = True,
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
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def fetch(self, url: str) -> tuple[int | None, str, str | None]:
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            ctype = (resp.headers.get("Content-Type") or "").lower()
            if ctype and "html" not in ctype and "text" not in ctype and "xml" not in ctype:
                return resp.status_code, "", f"unsupported content-type: {ctype}"
            return resp.status_code, resp.text[:2_000_000], None
        except requests.RequestException as exc:
            return None, "", str(exc)

    def normalize_site(self, href: str, base_url: str) -> str | None:
        href = (href or "").strip()
        if not href or href.lower().startswith(SKIP_SCHEMES):
            return None
        absolute = urldefrag(urljoin(base_url, href))[0]
        parsed = urlparse(absolute)
        if parsed.scheme not in ("http", "https"):
            return None
        path_l = parsed.path.lower()
        if any(path_l.endswith(ext) for ext in SKIP_EXTENSIONS):
            return None
        # Prefer origin (scheme + host) for partner site lists
        host = (parsed.hostname or "").lower()
        if not host:
            return None
        return f"{parsed.scheme}://{host}"

    def extract_sites(self, html: str, page_url: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        base_host = (urlparse(page_url).hostname or "").lower()
        found: list[str] = []
        seen: set[str] = set()

        if self.link_selector:
            anchors = soup.select(self.link_selector)
        else:
            anchors = soup.find_all("a", href=True)

        for a in anchors:
            href = a.get("href")
            if not href:
                continue
            site = self.normalize_site(href, page_url)
            if not site:
                continue
            host = urlparse(site).hostname or ""
            if self.external_only and (host == base_host or host.endswith("." + base_host)):
                continue
            if site not in seen:
                seen.add(site)
                found.append(site)
        return found

    def find_next_url(self, html: str, page_url: str, page_index: int) -> str | None:
        soup = BeautifulSoup(html, "lxml")

        # 1) Explicit CSS selector
        if self.next_selector:
            node = soup.select_one(self.next_selector)
            if node is not None:
                href = node.get("href") or (node.find("a", href=True) or {}).get("href")
                if href:
                    return urldefrag(urljoin(page_url, href))[0]

        # 2) Query param pagination: ?page=2 / ?p=2
        if self.page_param:
            return self._next_by_param(page_url, self.page_param, page_index)

        # 3) rel="next"
        rel_next = soup.find("a", rel=lambda v: v and "next" in v)
        if rel_next and rel_next.get("href"):
            return urldefrag(urljoin(page_url, rel_next["href"]))[0]

        # 4) Text / aria-label hints
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

        # 5) Auto-detect common page params already present in URL
        parsed = urlparse(page_url)
        qs = parse_qs(parsed.query)
        for key in ("page", "p", "pagina", "paged", "offset", "start"):
            if key in qs:
                return self._next_by_param(page_url, key, page_index)

        # 6) Path style /page/2/ or /page-2
        path_next = self._next_by_path(page_url, page_index)
        if path_next:
            return path_next

        # 7) Numbered pagination: link whose text is current+1
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
        qs[param] = [str(current + 1)]
        # flatten query
        flat = []
        for k, values in qs.items():
            for v in values:
                flat.append((k, v))
        new_query = urlencode(flat)
        return urlunparse(parsed._replace(query=new_query))

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
        for key in ("page", "p", "pagina", "paged"):
            if key in qs and qs[key]:
                try:
                    return int(qs[key][0])
                except ValueError:
                    pass
        match = re.search(r"/page[/-]?(\d+)", parsed.path)
        if match:
            return int(match.group(1))
        return page_index

    def crawl(self, start_url: str) -> ListingResult:
        start_url = start_url.strip()
        if "://" not in start_url:
            start_url = "https://" + start_url

        result = ListingResult(start_url=start_url)
        seen_pages: set[str] = set()
        seen_sites: set[str] = set()
        url = start_url
        empty_streak = 0

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
                if error or status in (404, 410):
                    break
                empty_streak += 1
                if empty_streak >= 2:
                    break
                # still try next if param mode
                nxt = self.find_next_url("", url, page_index) if self.page_param else None
                if not nxt:
                    break
                page.next_url = nxt
                url = nxt
                continue

            sites = self.extract_sites(html, url)
            page.sites = sites
            for site in sites:
                if site not in seen_sites:
                    seen_sites.add(site)
                    result.sites.append(site)

            if not sites:
                empty_streak += 1
            else:
                empty_streak = 0

            next_url = self.find_next_url(html, url, page_index)
            page.next_url = next_url
            result.pages.append(page)

            if not next_url or next_url in seen_pages:
                break
            if empty_streak >= 3 and not self.page_param:
                break
            # Safety: stop if next leaves listing path too far (optional)
            if self.same_path_prefix:
                start_path = urlparse(start_url).path.rstrip("/")
                next_path = urlparse(next_url).path.rstrip("/")
                if start_path and not (
                    next_path == start_path
                    or next_path.startswith(start_path + "/")
                    or re.search(r"/page[/-]?\d+", next_path)
                ):
                    # allow query-param pagination on same path
                    if urlparse(next_url).path.rstrip("/") != start_path:
                        break
            url = next_url

        return result


def write_sites_txt(path: str, sites: Iterable[str]) -> None:
    with open(path, "w", encoding="utf-8") as f:
        for site in sites:
            f.write(site + "\n")
