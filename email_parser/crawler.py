"""Fetch partner websites and collect pages likely to contain emails."""

from __future__ import annotations

import time
from collections import deque
from dataclasses import dataclass, field
from typing import Iterable
from urllib.parse import urljoin, urlparse, urldefrag

import requests
from bs4 import BeautifulSoup

from .extractor import extract_emails, same_registrable_hint

DEFAULT_HEADERS = {
    "User-Agent": (
        "PartnerEmailParser/1.0 (+https://localhost; contact research; "
        "respectful crawler)"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ru,en;q=0.8",
}

CONTACT_HINTS = (
    "contact",
    "contacts",
    "kontakt",
    "kontakty",
    "контакты",
    "контакт",
    "about",
    "o-nas",
    "о-нас",
    "о компании",
    "company",
    "support",
    "помо",
    "связ",
    "feedback",
    "обратн",
    "impressum",
    "rekvizit",
    "реквизит",
)


@dataclass
class PageResult:
    url: str
    status: int | None
    emails: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class SiteResult:
    input: str
    base_url: str
    emails: list[str] = field(default_factory=list)
    partner_emails: list[str] = field(default_factory=list)
    pages: list[PageResult] = field(default_factory=list)
    error: str | None = None


class EmailCrawler:
    def __init__(
        self,
        timeout: float = 15.0,
        delay: float = 0.4,
        max_pages: int = 8,
        session: requests.Session | None = None,
    ) -> None:
        self.timeout = timeout
        self.delay = delay
        self.max_pages = max_pages
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def normalize_start_url(self, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("empty url")
        if "://" not in value:
            value = "https://" + value
        parsed = urlparse(value)
        if not parsed.netloc:
            raise ValueError(f"invalid url: {value}")
        # Prefer site root if path is empty-ish
        if parsed.path in ("", "/"):
            return f"{parsed.scheme}://{parsed.netloc}/"
        return value

    def fetch(self, url: str) -> tuple[int | None, str, str | None]:
        try:
            resp = self.session.get(url, timeout=self.timeout, allow_redirects=True)
            content_type = (resp.headers.get("Content-Type") or "").lower()
            if "html" not in content_type and "text" not in content_type and content_type:
                return resp.status_code, "", f"unsupported content-type: {content_type}"
            # Limit huge pages
            text = resp.text[:1_500_000]
            return resp.status_code, text, None
        except requests.RequestException as exc:
            return None, "", str(exc)

    def discover_links(self, base_url: str, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        base_host = (urlparse(base_url).hostname or "").lower()
        scored: list[tuple[int, str]] = []
        seen: set[str] = set()

        for a in soup.find_all("a", href=True):
            href = a["href"].strip()
            if href.startswith(("mailto:", "tel:", "javascript:", "#")):
                continue
            absolute = urldefrag(urljoin(base_url, href))[0]
            parsed = urlparse(absolute)
            if parsed.scheme not in ("http", "https"):
                continue
            host = (parsed.hostname or "").lower()
            if host != base_host and not host.endswith("." + base_host):
                continue
            if absolute in seen:
                continue
            seen.add(absolute)

            label = f"{a.get_text(' ', strip=True)} {parsed.path} {href}".lower()
            score = 0
            for hint in CONTACT_HINTS:
                if hint in label:
                    score += 10
            if any(x in parsed.path.lower() for x in ("/contact", "/kontak", "/about", "/o-nas")):
                score += 5
            if score > 0:
                scored.append((score, absolute))

        scored.sort(key=lambda x: (-x[0], x[1]))
        return [url for _, url in scored]

    def crawl_site(self, input_value: str) -> SiteResult:
        try:
            start = self.normalize_start_url(input_value)
        except ValueError as exc:
            return SiteResult(input=input_value, base_url="", error=str(exc))

        result = SiteResult(input=input_value, base_url=start)
        queue: deque[str] = deque([start])
        visited: set[str] = set()
        all_emails: list[str] = []
        seen_emails: set[str] = set()

        while queue and len(visited) < self.max_pages:
            url = queue.popleft()
            if url in visited:
                continue
            visited.add(url)

            if self.delay and len(visited) > 1:
                time.sleep(self.delay)

            status, html, error = self.fetch(url)
            page = PageResult(url=url, status=status, error=error)
            if html:
                emails = extract_emails(html)
                page.emails = emails
                for email in emails:
                    if email not in seen_emails:
                        seen_emails.add(email)
                        all_emails.append(email)
                if url == start or len(visited) == 1:
                    for link in self.discover_links(start, html):
                        if link not in visited and link not in queue:
                            queue.append(link)
            result.pages.append(page)

        result.emails = all_emails
        result.partner_emails = [
            e for e in all_emails if same_registrable_hint(e, start)
        ]
        return result

    def crawl_many(self, inputs: Iterable[str]) -> list[SiteResult]:
        results: list[SiteResult] = []
        for value in inputs:
            value = value.strip()
            if not value or value.startswith("#"):
                continue
            results.append(self.crawl_site(value))
        return results
