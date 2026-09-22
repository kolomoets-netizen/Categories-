#!/usr/bin/env python3
"""CLI: partner site list + email parsers."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from . import __version__
from .crawler import EmailCrawler
from .site_list import SiteListParser, write_sites_txt


def load_inputs(args: argparse.Namespace) -> list[str]:
    values: list[str] = []
    if getattr(args, "url", None):
        values.extend(args.url)
    if getattr(args, "file", None):
        text = Path(args.file).read_text(encoding="utf-8")
        values.extend(line.strip() for line in text.splitlines())
    if not values and not sys.stdin.isatty():
        values.extend(line.strip() for line in sys.stdin)
    seen: set[str] = set()
    unique: list[str] = []
    for v in values:
        if not v or v.startswith("#"):
            continue
        key = v.lower()
        if key not in seen:
            seen.add(key)
            unique.append(v)
    return unique


def write_json(path: Path, results: list) -> None:
    payload = []
    for r in results:
        payload.append(
            {
                "input": r.input,
                "base_url": r.base_url,
                "emails": r.emails,
                "partner_emails": r.partner_emails,
                "error": r.error,
                "pages": [
                    {
                        "url": p.url,
                        "status": p.status,
                        "emails": p.emails,
                        "error": p.error,
                    }
                    for p in r.pages
                ],
            }
        )
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def write_csv(path: Path, results: list) -> None:
    with path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["site", "email", "is_partner_domain", "found_on", "error"],
        )
        writer.writeheader()
        for r in results:
            if r.error and not r.emails:
                writer.writerow(
                    {
                        "site": r.input,
                        "email": "",
                        "is_partner_domain": "",
                        "found_on": "",
                        "error": r.error,
                    }
                )
                continue
            page_map: dict[str, list[str]] = {}
            for page in r.pages:
                for email in page.emails:
                    page_map.setdefault(email, []).append(page.url)
            for email in r.emails:
                writer.writerow(
                    {
                        "site": r.input,
                        "email": email,
                        "is_partner_domain": "yes" if email in r.partner_emails else "no",
                        "found_on": "; ".join(page_map.get(email, [])[:5]),
                        "error": r.error or "",
                    }
                )


def print_email_summary(results: list) -> None:
    total_emails = 0
    for r in results:
        print(f"\n=== {r.input} ===")
        if r.error and not r.emails:
            print(f"  ERROR: {r.error}")
            continue
        emails = r.partner_emails or r.emails
        if not emails:
            print("  emails: (not found)")
        else:
            for email in emails:
                mark = "*" if email in r.partner_emails else " "
                print(f"  {mark} {email}")
        total_emails += len(r.emails)
        print(f"  pages crawled: {len(r.pages)}, unique emails: {len(r.emails)}")
    print(f"\nSites: {len(results)}, emails found: {total_emails}")
    print("(* = matches site domain)")


def cmd_emails(args: argparse.Namespace) -> int:
    inputs = load_inputs(args)
    if not inputs:
        print("Provide --url, --file, or pipe URLs via stdin.", file=sys.stderr)
        return 2

    crawler = EmailCrawler(
        timeout=args.timeout,
        delay=args.delay,
        max_pages=args.max_pages,
    )
    results = crawler.crawl_many(inputs)

    if args.all_emails:
        for r in results:
            r.partner_emails = list(r.emails)

    print_email_summary(results)

    if args.output:
        write_json(Path(args.output), results)
        print(f"JSON saved: {args.output}")
    if args.csv_path:
        write_csv(Path(args.csv_path), results)
        print(f"CSV saved: {args.csv_path}")
    return 0


def cmd_sites(args: argparse.Namespace) -> int:
    if not args.url:
        print("Provide --url of the paginated listing page.", file=sys.stderr)
        return 2

    parser = SiteListParser(
        timeout=args.timeout,
        delay=args.delay,
        max_pages=args.max_pages,
        link_selector=args.link_selector,
        next_selector=args.next_selector,
        page_param=args.page_param,
        external_only=not args.include_internal,
    )
    result = parser.crawl(args.url)

    print(f"Start: {result.start_url}")
    print(f"Pages crawled: {len(result.pages)}")
    for page in result.pages:
        status = page.status if page.status is not None else "-"
        print(f"  [{status}] {page.url} -> {len(page.sites)} sites", end="")
        if page.next_url:
            print(f" | next: {page.next_url}")
        else:
            print()
        if page.error:
            print(f"    error: {page.error}")

    print(f"\nUnique sites: {len(result.sites)}")
    for site in result.sites[:30]:
        print(f"  {site}")
    if len(result.sites) > 30:
        print(f"  ... +{len(result.sites) - 30} more")

    out_txt = args.output or "partner_sites.txt"
    write_sites_txt(out_txt, result.sites)
    print(f"\nSaved: {out_txt}")

    if args.json:
        payload = {
            "start_url": result.start_url,
            "sites": result.sites,
            "pages": [
                {
                    "url": p.url,
                    "status": p.status,
                    "sites_count": len(p.sites),
                    "sites": p.sites,
                    "next_url": p.next_url,
                    "error": p.error,
                }
                for p in result.pages
            ],
        }
        Path(args.json).write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        print(f"JSON saved: {args.json}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="email-parser",
        description="Parse partner website lists and email addresses.",
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    sub = p.add_subparsers(dest="command")

    # emails
    e = sub.add_parser("emails", help="Extract emails from partner websites")
    e.add_argument("-u", "--url", action="append", help="Partner URL or domain")
    e.add_argument("-f", "--file", help="File with one URL/domain per line")
    e.add_argument("-o", "--output", help="JSON report path")
    e.add_argument("--csv", dest="csv_path", help="CSV report path")
    e.add_argument("--max-pages", type=int, default=8)
    e.add_argument("--delay", type=float, default=0.4)
    e.add_argument("--timeout", type=float, default=15.0)
    e.add_argument("--all-emails", action="store_true")
    e.set_defaults(func=cmd_emails)

    # sites (paginated listing)
    s = sub.add_parser("sites", help="Collect website links from a paginated page")
    s.add_argument("-u", "--url", required=True, help="Listing page URL (with pagination)")
    s.add_argument("-o", "--output", help="Output txt with sites (default: partner_sites.txt)")
    s.add_argument("--json", help="Optional JSON report path")
    s.add_argument("--max-pages", type=int, default=100, help="Max listing pages to crawl")
    s.add_argument("--delay", type=float, default=0.5)
    s.add_argument("--timeout", type=float, default=15.0)
    s.add_argument(
        "--link-selector",
        help='CSS selector for site links, e.g. "a.partner-link" or ".card a[href]"',
    )
    s.add_argument(
        "--next-selector",
        help='CSS selector for "next page" control, e.g. "a.next" or ".pagination .next a"',
    )
    s.add_argument(
        "--page-param",
        help='Force query pagination param, e.g. "page" for ?page=2',
    )
    s.add_argument(
        "--include-internal",
        action="store_true",
        help="Also keep links to the same domain as the listing",
    )
    s.set_defaults(func=cmd_sites)

    return p


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser()

    # Backward compatible: old flags without subcommand => emails
    if argv and argv[0] not in ("emails", "sites", "-h", "--help", "--version") and not argv[0].startswith("-"):
        # positional unknown — show help
        pass
    if argv and argv[0] not in ("emails", "sites", "-h", "--help", "--version"):
        argv = ["emails", *argv]

    args = parser.parse_args(argv)
    if not getattr(args, "command", None):
        parser.print_help()
        return 2
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
