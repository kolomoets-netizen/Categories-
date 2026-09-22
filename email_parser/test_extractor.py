#!/usr/bin/env python3
"""Unit tests for email extraction (no network)."""

from email_parser.extractor import extract_emails, normalize_email


def test_plain_email():
    assert extract_emails("Пишите на sales@partner.ru") == ["sales@partner.ru"]


def test_mailto():
    html = '<a href="mailto:Info@Partner.RU?subject=Hi">mail</a>'
    assert extract_emails(html) == ["info@partner.ru"]


def test_obfuscated():
    text = "contact us: support [at] company [dot] com"
    assert "support@company.com" in extract_emails(text)
    # must not treat JS identifiers as emails
    assert extract_emails("window.location.protocol navigator.userAgent") == []


def test_strips_script_noise():
    html = "<script>var x = window.location.hostname;</script>hi sales@shop.ru"
    assert extract_emails(html) == ["sales@shop.ru"]


def test_html_entity():
    html = "help&#64;shop.example.org"
    assert extract_emails(html) == ["help@shop.example.org"]


def test_filters_noreply_and_assets():
    assert normalize_email("noreply@partner.ru") is None
    assert normalize_email("file@cdn.com.png") is None
    assert "noreply@x.com" not in extract_emails("noreply@x.com sales@x.com")


def test_dedupe():
    text = "a@b.co A@B.CO mailto:a@b.co"
    assert extract_emails(text) == ["a@b.co"]


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_") and callable(fn):
            fn()
            print(f"OK {name}")
    print("all passed")
