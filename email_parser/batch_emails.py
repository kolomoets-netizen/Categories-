#!/usr/bin/env python3
"""Batch-crawl partner sites for emails (parallel)."""

from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from email_parser.crawler import EmailCrawler

SITES_FILE = Path("data/1c/partner_sites.txt")
OUT_JSON = Path("data/1c/partner_emails.json")
OUT_CSV = Path("data/1c/partner_emails.csv")
OUT_TXT = Path("data/1c/partner_emails.txt")
PROGRESS = Path("data/1c/partner_emails_progress.json")

WORKERS = 24
MAX_PAGES = 3
TIMEOUT = 12.0
DELAY = 0.05


def crawl_one(url: str) -> dict:
    crawler = EmailCrawler(timeout=TIMEOUT, delay=DELAY, max_pages=MAX_PAGES)
    result = crawler.crawl_site(url)
    return {
        "input": result.input,
        "base_url": result.base_url,
        "emails": result.emails,
        "partner_emails": result.partner_emails,
        "error": result.error,
        "pages_crawled": len(result.pages),
        "page_errors": [p.error for p in result.pages if p.error],
    }


def main() -> None:
    sites = [
        line.strip()
        for line in SITES_FILE.read_text(encoding="utf-8").splitlines()
        if line.strip() and not line.startswith("#")
    ]
    print(f"Sites to crawl: {len(sites)}", flush=True)

    done: dict[str, dict] = {}
    if PROGRESS.exists():
        try:
            for row in json.loads(PROGRESS.read_text(encoding="utf-8")):
                done[row["input"]] = row
            print(f"Resuming with {len(done)} already done", flush=True)
        except Exception:
            done = {}

    pending = [s for s in sites if s not in done]
    print(f"Pending: {len(pending)}", flush=True)

    started = time.time()
    finished = 0

    def save_progress() -> None:
        rows = [done[s] for s in sites if s in done]
        PROGRESS.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {pool.submit(crawl_one, url): url for url in pending}
        for fut in as_completed(futures):
            url = futures[fut]
            finished += 1
            try:
                row = fut.result()
            except Exception as exc:
                row = {
                    "input": url,
                    "base_url": "",
                    "emails": [],
                    "partner_emails": [],
                    "error": str(exc),
                    "pages_crawled": 0,
                    "page_errors": [],
                }
            done[url] = row
            if finished % 25 == 0 or finished == len(pending):
                save_progress()
                with_email = sum(1 for r in done.values() if r.get("emails"))
                elapsed = time.time() - started
                rate = finished / elapsed if elapsed else 0
                print(
                    f"[{finished}/{len(pending)}] "
                    f"with_email={with_email}/{len(done)} "
                    f"{rate:.1f} sites/s",
                    flush=True,
                )

    rows = [done[s] for s in sites if s in done]
    OUT_JSON.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")

    # Flat unique emails
    all_emails: list[str] = []
    seen: set[str] = set()
    for row in rows:
        for email in row.get("partner_emails") or row.get("emails") or []:
            if email not in seen:
                seen.add(email)
                all_emails.append(email)
    OUT_TXT.write_text("\n".join(all_emails) + ("\n" if all_emails else ""), encoding="utf-8")

    import csv

    with OUT_CSV.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["site", "email", "is_partner_domain", "error"],
        )
        writer.writeheader()
        for row in rows:
            emails = row.get("emails") or []
            if not emails:
                writer.writerow(
                    {
                        "site": row["input"],
                        "email": "",
                        "is_partner_domain": "",
                        "error": row.get("error") or "",
                    }
                )
                continue
            partner = set(row.get("partner_emails") or [])
            for email in emails:
                writer.writerow(
                    {
                        "site": row["input"],
                        "email": email,
                        "is_partner_domain": "yes" if email in partner else "no",
                        "error": row.get("error") or "",
                    }
                )

    with_email = sum(1 for r in rows if r.get("emails"))
    print(
        f"\nDone. sites={len(rows)} with_email={with_email} "
        f"unique_emails={len(all_emails)}",
        flush=True,
    )
    print(f"JSON: {OUT_JSON}")
    print(f"CSV:  {OUT_CSV}")
    print(f"TXT:  {OUT_TXT}")


if __name__ == "__main__":
    main()
