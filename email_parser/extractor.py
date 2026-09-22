"""Extract email addresses from HTML and plain text."""

from __future__ import annotations

import re
from html import unescape
from urllib.parse import unquote, urlparse

# Practical email pattern (avoids matching file extensions like name.js)
EMAIL_RE = re.compile(
    r"""
    (?<![A-Za-z0-9._%+\-])
    ([A-Za-z0-9](?:[A-Za-z0-9._%+\-]{0,62}[A-Za-z0-9])?)
    @
    ([A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?
      (?:\.[A-Za-z0-9](?:[A-Za-z0-9\-]{0,61}[A-Za-z0-9])?)+)
    (?![A-Za-z0-9._%+\-])
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Obfuscations with explicit separators only:
# info [at] company [dot] com, info(at)company(dot)com, info at company dot com
OBFUSCATED_RE = re.compile(
    r"""
    ([A-Za-z0-9][A-Za-z0-9._%+\-]{0,63})
    \s*
    (?:
        \( \s* at \s* \)
      | \[ \s* at \s* \]
      | \{ \s* at \s* \}
      | (?<![A-Za-z]) at (?![A-Za-z])
    )
    \s*
    ([A-Za-z0-9][A-Za-z0-9\-]* (?:\.[A-Za-z0-9\-]+)* )
    \s*
    (?:
        \( \s* (?:dot|\.) \s* \)
      | \[ \s* (?:dot|\.) \s* \]
      | \{ \s* (?:dot|\.) \s* \}
      | (?<![A-Za-z]) dot (?![A-Za-z])
    )
    \s*
    ([A-Za-z]{2,24})
    """,
    re.VERBOSE | re.IGNORECASE,
)

# Valid public TLDs we accept (keeps JS false-positives out)
COMMON_TLDS = {
    "com", "ru", "net", "org", "io", "co", "info", "biz", "me", "cc", "tv",
    "pro", "su", "ua", "by", "kz", "uz", "am", "ge", "kg", "tj", "md",
    "uk", "de", "fr", "it", "es", "pl", "cz", "sk", "nl", "be", "at", "ch",
    "se", "no", "fi", "dk", "pt", "gr", "tr", "il", "ae", "sa", "in", "cn",
    "jp", "kr", "sg", "hk", "au", "nz", "ca", "us", "br", "mx", "ar",
    "online", "site", "store", "shop", "tech", "app", "dev", "xyz", "club",
    "moscow", "spb", "рус", "рф",
}

MAILTO_RE = re.compile(r"mailto:([^?\"'\s>]+)", re.IGNORECASE)

# Common false positives from assets / trackers
BLOCKED_DOMAINS = {
    "example.com",
    "example.org",
    "example.net",
    "domain.com",
    "email.com",
    "sentry.io",
    "wixpress.com",
    "squarespace.com",
    "schema.org",
    "w3.org",
    "googleapis.com",
    "gstatic.com",
    "cloudflare.com",
    "jquery.com",
    "github.com",
    "githubusercontent.com",
}

BLOCKED_LOCALS = {
    "noreply",
    "no-reply",
    "donotreply",
    "do-not-reply",
    "mailer-daemon",
    "postmaster",
}

BLOCKED_TLDS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".css", ".js", ".json"}


def normalize_email(raw: str) -> str | None:
    email = unescape(unquote(raw)).strip().lower()
    email = email.replace(" ", "")
    email = re.sub(r"^mailto:", "", email, flags=re.IGNORECASE)
    email = email.split("?")[0].rstrip(".,;:)>]}'\"")
    if not EMAIL_RE.fullmatch(email):
        return None

    local, domain = email.split("@", 1)
    if local in BLOCKED_LOCALS:
        return None
    if domain in BLOCKED_DOMAINS:
        return None
    if any(domain.endswith(ext) for ext in BLOCKED_TLDS):
        return None
    if domain.count(".") < 1:
        return None
    # Reject JS-like locals / domains
    if any(ch in local for ch in "()[]{}"):
        return None
    if re.search(r"\.(js|css|map|min|php|asp|html?)$", domain):
        return None
    tld = domain.rsplit(".", 1)[-1].lower()
    if tld not in COMMON_TLDS and len(tld) > 6:
        return None
    if tld not in COMMON_TLDS and not re.fullmatch(r"[a-z]{2,6}", tld):
        return None
    # Heuristic: too many dots in local usually means JS path
    if local.count(".") >= 2:
        return None
    return email


def deobfuscate(text: str) -> list[str]:
    found: list[str] = []
    for match in OBFUSCATED_RE.finditer(text):
        candidate = f"{match.group(1)}@{match.group(2)}.{match.group(3)}"
        email = normalize_email(candidate)
        if email:
            found.append(email)
    return found


def _strip_scripts_and_styles(html: str) -> str:
    """Remove script/style bodies so JS identifiers are not parsed as emails."""
    html = re.sub(r"(?is)<script[^>]*>.*?</script>", " ", html)
    html = re.sub(r"(?is)<style[^>]*>.*?</style>", " ", html)
    html = re.sub(r"(?is)<!--.*?-->", " ", html)
    return html


def extract_emails(html_or_text: str) -> list[str]:
    """Return unique normalized emails found in page content."""
    text = unescape(html_or_text or "")
    text = _strip_scripts_and_styles(text)
    # Soft-decode common HTML entities used for @ and .
    text = (
        text.replace("&#64;", "@")
        .replace("&#x40;", "@")
        .replace("&64;", "@")
        .replace("&#46;", ".")
        .replace("&dot;", ".")
    )

    found: list[str] = []
    seen: set[str] = set()

    def add(raw: str) -> None:
        email = normalize_email(raw)
        if email and email not in seen:
            seen.add(email)
            found.append(email)

    for match in MAILTO_RE.finditer(text):
        add(match.group(1))

    for match in EMAIL_RE.finditer(text):
        add(match.group(0))

    for email in deobfuscate(text):
        if email not in seen:
            seen.add(email)
            found.append(email)

    return found


def same_registrable_hint(email: str, page_url: str) -> bool:
    """True if email domain loosely matches the site domain (partner contact)."""
    try:
        host = urlparse(page_url).hostname or ""
    except Exception:
        return False
    host = host.lower().removeprefix("www.")
    domain = email.split("@", 1)[1]
    return domain == host or host.endswith("." + domain)
