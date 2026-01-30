#!/usr/bin/env python3
from __future__ import annotations

import re
from dataclasses import dataclass

import requests

USER_AGENT = "Mozilla/5.0 (compatible; HouseFinder/0.2)"
TIMEOUT_S = 25

# Matches both "101 kvm" and "101 m²" (and decimals with comma/dot)
# 1) First handle "170 + 100" (pick 170)
AREA_PLUS_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*\+\s*\d+(?:[.,]\d+)?")

# 2) Then handle normal "170 kvm" / "170 m²" / entities
AREA_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:kvm|m²|m&#178;|m\s*<sup>\s*2\s*</sup>)",
    re.IGNORECASE,
)
PRICE_RE = re.compile(r"(\d{1,3}(?:[ \u00A0]?\d{3})*)\s*(?:kr|:-)", re.IGNORECASE)


@dataclass(frozen=True)
class Listing:
    site: str
    title: str
    url: str
    area_m2: float | None
    price: int | None


def fetch_html_requests(url: str) -> str:
    r = requests.get(
        url,
        headers={
            "User-Agent": USER_AGENT,
            "Accept-Language": "sv-SE,sv;q=0.9,en;q=0.8",
        },
        timeout=TIMEOUT_S,
    )
    r.raise_for_status()
    return r.text


def fetch_html_playwright(url: str) -> str | None:
    """
    Returns rendered HTML using Playwright, or None if Playwright is not available.
    """
    try:
        from playwright.sync_api import sync_playwright  # type: ignore
    except Exception:
        return None

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page(
            user_agent=USER_AGENT,
            locale="sv-SE",
        )
        page.goto(url, wait_until="networkidle", timeout=TIMEOUT_S * 1000)
        html = page.content()
        browser.close()
        return html


def parse_area_m2(text: str) -> float | None:
    # Prefer the "A + B" style and pick A
    m = AREA_PLUS_RE.search(text)
    if m:
        raw = m.group(1).replace(",", ".")
        try:
            return float(raw)
        except ValueError:
            pass

    # Fall back to "A kvm" / "A m²"
    m = AREA_RE.search(text)
    if not m:
        return None
    raw = m.group(1).replace(",", ".")
    try:
        return float(raw)
    except ValueError:
        return None


def parse_price_sek(text: str) -> int | None:
    # Find every "number ... kr" (handles spaces and NBSP)
    matches = list(PRICE_RE.finditer(text))
    if not matches:
        return None

    candidates: list[int] = []
    lower = text.lower()

    for m in matches:
        # Look at the characters right after this "kr" to detect "kr / mån"
        after = lower[m.end(): m.end() + 12]  # small window after the match

        if re.match(r"\s*(?:/|\s+per\s+)\s*mån", after):
            continue  # skip monthly fee like "5 587 kr / mån"

        digits_only = m.group(1).replace(" ", "").replace("\u00A0", "")
        try:
            candidates.append(int(digits_only))
        except ValueError:
            continue

    if not candidates:
        return None

    # Sale price is usually the biggest number on the card
    return max(candidates)
