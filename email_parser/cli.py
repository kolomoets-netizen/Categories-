#!/usr/bin/env python3
"""CLI: parse email addresses from partner websites."""

from __future__ import annotations

import argparse
import csv
import json
import sys
from pathlib import Path

from . import __version__
from .crawler import EmailCrawler


def load_inputs(args: argparse.Namespace) -> list[str]:
    values: list[str] = []
    if args.url:
        values.extend(args.url)
    if args.file:
        text = Path(args.file).read_text(encoding="utf-8")
        values.extend(line.strip() for line in text.splitlines())
    if not values and not sys.stdin.isatty():
        values.extend(line.strip() for line in sys.stdin)
    # dedupe preserving order
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


def print_summary(results: list) -> None:
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


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="email-parser",
        description="Parse email addresses from partner websites.",
    )
    p.add_argument("-u", "--url", action="append", help="Partner URL or domain (repeatable)")
    p.add_argument("-f", "--file", help="Text file with one URL/domain per line")
    p.add_argument("-o", "--output", help="Write JSON report to this path")
    p.add_argument("--csv", dest="csv_path", help="Write CSV report to this path")
    p.add_argument("--max-pages", type=int, default=8, help="Max pages per site (default: 8)")
    p.add_argument("--delay", type=float, default=0.4, help="Delay between requests, sec")
    p.add_argument("--timeout", type=float, default=15.0, help="HTTP timeout, sec")
    p.add_argument("--all-emails", action="store_true", help="Show all emails, not only partner-domain")
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    inputs = load_inputs(args)
    if not inputs:
        build_parser().print_help()
        print("\nProvide --url, --file, or pipe URLs via stdin.", file=sys.stderr)
        return 2

    crawler = EmailCrawler(
        timeout=args.timeout,
        delay=args.delay,
        max_pages=args.max_pages,
    )
    results = crawler.crawl_many(inputs)

    if args.all_emails:
        for r in results:
            # force summary to list all
            r.partner_emails = list(r.emails)

    print_summary(results)

    if args.output:
        write_json(Path(args.output), results)
        print(f"JSON saved: {args.output}")
    if args.csv_path:
        write_csv(Path(args.csv_path), results)
        print(f"CSV saved: {args.csv_path}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
