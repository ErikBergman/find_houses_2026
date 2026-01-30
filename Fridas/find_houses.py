#!/usr/bin/env python3
from __future__ import annotations

import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse, urljoin
import json

import requests
from bs4 import BeautifulSoup

APP_DIR = Path(__file__).resolve().parent
USER_AGENT = "Mozilla/5.0 (compatible; HouseFinder/0.2)"
TIMEOUT_S = 25
SLEEP_BETWEEN_REQUESTS_S = 1.0

# Matches both "101 kvm" and "101 m²" (and decimals with comma/dot)
# AREA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:kvm|m²)", re.IGNORECASE)
# AREA_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*(?:kvm|m²|m&#178;|m\s*<sup>\s*2\s*</sup>)",re.IGNORECASE)
# 1) First handle "170 + 100" (pick 170)
AREA_PLUS_RE = re.compile(r"(\d+(?:[.,]\d+)?)\s*\+\s*\d+(?:[.,]\d+)?")

# 2) Then handle normal "170 kvm" / "170 m²" / entities
AREA_RE = re.compile(
    r"(\d+(?:[.,]\d+)?)\s*(?:kvm|m²|m&#178;|m\s*<sup>\s*2\s*</sup>)",
    re.IGNORECASE,)
# PRICE_RE = re.compile(r"(\d{1,3}(?:\s?\d{3})*)\s*(?:kr|:-)", re.IGNORECASE)
PRICE_RE = re.compile(r"(\d{1,3}(?:[ \u00A0]?\d{3})*)\s*(?:kr|:-)", re.IGNORECASE)

@dataclass(frozen=True)
class Listing:
    site: str
    title: str
    url: str
    area_m2: float | None
    price: int | None


def fetch_html_requests(url):
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


def fetch_html_playwright(url):
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


# def parse_area_m2(text):
#     m = AREA_RE.search(text)
#     if not m:
#         return None
#     raw = m.group(1).replace(",", ".")
#     try:
#         return float(raw)
#     except ValueError:
#         return None


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



# def parse_price_sek(text: str) -> int | None:
#     m = PRICE_RE.search(text)
#     if not m:
#         return None
#     digits_only = m.group(1).replace(" ", "")
#     return int(digits_only)

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

def filter_listings(listings,keyword, min_area_m2):
    kw = keyword.casefold()
    out = []
    for li in listings:
        if kw not in li.title.casefold():
            continue
        if li.area_m2 is None or li.area_m2 <= min_area_m2:
            continue
        out.append(li)
    return out


def parse_fastighetsbyran(url, html):
    """
    Fastighetsbyrån pages tend to include listing rows as text in the HTML.  [oai_citation:2‡Fastighetsbyrån](https://www.fastighetsbyran.com/sv/sverige/till-salu?utm_source=chatgpt.com)
    Heuristic: anchor links containing 'objekt' or 'objektID' and nearby text contains area.
    """
    soup = BeautifulSoup(html, "html.parser")
    found = {} # {url:listing}

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not href:
            continue

        text = " ".join(a.get_text(" ", strip=True).split())
        if not text:
            continue

        if "/objekt/" not in href and "objektID" not in href:
            continue

        abs_url = urljoin(url, href)
        area = parse_area_m2(text)
        price = parse_price_sek(text)
        found[abs_url] = Listing(site="fastighetsbyran", title=text, url=abs_url, area_m2=area, price=price)

    return list(found.values())


# def parse_erikolsson(url, html):
#     """
#     Erik Olsson search pages may be JS-rendered. When rendered, listings typically link to /homes/<id or slug>.
#     We take the surrounding card text (parent element) to catch area text.
#     """
#     soup = BeautifulSoup(html, "html.parser")
#     found = {} # {url:listing}

#     # Grab any link that looks like a home detail page
#     for a in soup.select('a[href^="/homes"]'):
#         href = a.get("href", "")
#         abs_url = urljoin(url, href)

#         # Use nearby text: the anchor + its parent container
#         a_text = " ".join(a.get_text(" ", strip=True).split())
#         parent_text = ""
#         if a.parent:
#             parent_text = " ".join(a.parent.get_text(" ", strip=True).split())

#         combined = (parent_text if len(parent_text) > len(a_text) else a_text).strip()
#         if not combined:
#             continue

#         area = parse_area_m2(combined)
#         price = parse_price_sek(combined)
#         found[abs_url] = Listing(site="erikolsson", title=combined, url=abs_url, area_m2=area, price=price)

#     return list(found.values())


# def parse_erikolsson(url, html):
#     soup = BeautifulSoup(html, "html.parser")
#     found = {}

#     # Grab any link that looks like a home detail page
#     for a in soup.select('a[href^="/homes"]'):
#         href = a.get("href", "")
#         if not href:
#             continue

#         abs_url = urljoin(url, href)


#         # Skip obvious non-listing links (top nav etc.)
#         # Listing links usually go to something like /homes/<id> or /homes/<slug>
#         if href.rstrip("/").lower() == "/homes":
#             continue

#         # Start with the anchor text
#         a_text = " ".join(a.get_text(" ", strip=True).split())

#         # Now climb upwards and find a container that looks like a listing card
#         best_text = ""
#         node = a
#         for _ in range(8):  # climb up to 8 levels
#             node = node.parent
#             if node is None:
#                 break

#             text = " ".join(node.get_text(" ", strip=True).split())
#             if not text:
#                 continue

#             # Heuristic: listing cards tend to include price and/or area
#             # We accept text that contains at least one hard signal:
#             # - "kr" (price)
#             # - "m²" or "kvm" (area)
#             # And also contains something beyond menu items
#             has_price = "kr" in text.lower()
#             has_area = ("m²" in text) or ("kvm" in text.lower()) or ("m&#178;" in text.lower())

#             if has_price or has_area:
#                 best_text = text
#                 break

#         combined = best_text or a_text
#         if not combined:
#             continue

#         area = parse_area_m2(combined)
#         price = parse_price_sek(combined)

#         # Extra filter: if it still looks like pure navigation, skip it
#         nav_words = {"våra bostäder", "våra mäklare", "våra områden", "vår tjänst"}
#         if any(w in combined.casefold() for w in nav_words) and price is None and area is None:
#             continue

#         found[abs_url] = Listing(
#             site="erikolsson",
#             title=combined,
#             url=abs_url,
#             area_m2=area,
#             price=price,
#         )

#     return list(found.values())



def extract_next_data(html: str) -> dict | None:
    """
    Erik Olsson runs Next.js. Many pages embed data in:
      <script id="__NEXT_DATA__" type="application/json"> ... </script>
    This returns that JSON as a dict if present.
    """
    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def walk_dicts(obj):
    """
    Yield every dict nested inside obj (which can be dict/list/scalar).
    """
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from walk_dicts(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from walk_dicts(it)


def parse_erikolsson(url, html):
    """
    Prefer Next.js embedded JSON (stable), fall back to DOM scraping if missing.
    Produces Listing(site,title,url,area_m2,price) like your other parser.
    """
    # 1) Try Next.js JSON
    data = extract_next_data(html)
    if data:
        found = {}

        for d in walk_dicts(data):
            # Look for something that clearly links to a home details page
            rel = d.get("url") or d.get("path") or d.get("href")
            if not isinstance(rel, str) or "/homes" not in rel:
                continue

            if rel.rstrip("/").lower() == "/homes":
                continue

            abs_url = urljoin("https://www.erikolsson.se", rel)

            # Build a text blob from nearby string fields to parse area/price from
            # (keeps it generic so it survives site changes)
            parts = []
            for k, v in d.items():
                if isinstance(v, str) and v.strip():
                    parts.append(v.strip())

            combined = " | ".join(parts[:12])  # limit so it doesn’t explode
            if not combined:
                continue

            area = None
            price = None

            # Prefer numeric fields if they exist
            for k in ("livingArea", "area", "boarea"):
                v = d.get(k)
                if isinstance(v, (int, float)) and v > 0:
                    area = float(v)
                    break

            for k in ("price", "askingPrice"):
                v = d.get(k)
                if isinstance(v, int) and v > 0:
                    price = v
                    break

            # Otherwise parse from combined text
            if area is None:
                area = parse_area_m2(combined)
            if price is None:
                price = parse_price_sek(combined)

            # Title: pick something human friendly if possible
            title = ""
            for key in ("address", "street", "title", "headline", "name"):
                v = d.get(key)
                if isinstance(v, str) and v.strip():
                    title = v.strip()
                    break
            if not title:
                title = combined

            found[abs_url] = Listing(
                site="erikolsson",
                title=title,
                url=abs_url,
                area_m2=area,
                price=price,
            )

        return list(found.values())

    # 2) Fallback: DOM heuristic (what you already had, slightly tightened)
    soup = BeautifulSoup(html, "html.parser")
    found = {}

    for a in soup.select('a[href^="/homes"]'):
        href = a.get("href", "")
        if not href or href.rstrip("/").lower() == "/homes":
            continue

        abs_url = urljoin(url, href)

        # climb to find a container that looks like a listing (price/area present)
        best_text = ""
        node = a
        for _ in range(10):
            node = node.parent
            if node is None:
                break
            text = " ".join(node.get_text(" ", strip=True).split())
            if not text:
                continue
            if ("kr" in text.lower()) or ("m²" in text) or ("kvm" in text.lower()) or ("m&#178;" in text.lower()):
                best_text = text
                break


        combined = best_text or " ".join(a.get_text(" ", strip=True).split())
        if not combined:
            continue

        if "Våra bostäder" in combined:
            continue

        area = parse_area_m2(combined)
        price = parse_price_sek(combined)

        found[abs_url] = Listing(
            site="erikolsson",
            title=combined,
            url=abs_url,
            area_m2=area,
            price=price,
        )

    return list(found.values())


def parse_lansfast(url, html):
    soup = BeautifulSoup(html, "html.parser")
    found = {}

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not href:
            continue

        href_l = href.lower()

        # Only keep actual listing links
        if "/villa/" not in href_l and "/bostadsratt/" not in href_l:
            continue

        abs_url = urljoin(url, href)

        # Get a larger text blob than the anchor itself
        best_text = ""
        node = a
        for _ in range(12):
            node = node.parent
            if node is None:
                break
            text = " ".join(node.get_text(" ", strip=True).split())
            if not text:
                continue

            # stop when we reached something that looks like a listing card
            if ("kr" in text.lower()) or ("m²" in text) or ("kvm" in text.lower()) or ("m&#178;" in text.lower()):
                best_text = text
                break

        combined = best_text or " ".join(a.get_text(" ", strip=True).split())
        area = parse_area_m2(combined)
        price = parse_price_sek(combined)

        found[abs_url] = Listing(
            site="lansfast",
            title=combined,
            url=abs_url,
            area_m2=area,
            price=price,
        )

    return list(found.values())


def parse_jsonld_listings(html: str):
    soup = BeautifulSoup(html, "html.parser")
    objs = []
    for tag in soup.select('script[type="application/ld+json"]'):
        raw = (tag.string or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if isinstance(data, list):
            objs.extend(data)
        else:
            objs.append(data)
    return objs

def parse_svenskfast(url, html):
    found = {}

    for obj in parse_jsonld_listings(html):
        if not isinstance(obj, dict):
            continue

        # JSON-LD sometimes wraps things inside @graph
        graph = obj.get("@graph")
        if isinstance(graph, list):
            candidates = graph
        else:
            candidates = [obj]

        for d in candidates:
            if not isinstance(d, dict):
                continue

            rel = d.get("url")
            if not isinstance(rel, str):
                continue

            abs_url = urljoin(url, rel)

            # Try to build a readable title
            name = d.get("name") if isinstance(d.get("name"), str) else ""
            address = d.get("address")
            if isinstance(address, dict):
                street = address.get("streetAddress") if isinstance(address.get("streetAddress"), str) else ""
                locality = address.get("addressLocality") if isinstance(address.get("addressLocality"), str) else ""
                title = " ".join(x for x in [street, locality] if x).strip() or name
            else:
                title = name or abs_url

            # Price and area might appear in different keys
            price = None
            if isinstance(d.get("price"), (int, float, str)):
                price = parse_price_sek(str(d.get("price")))

            area = None
            floor = d.get("floorSize")
            if isinstance(floor, dict) and isinstance(floor.get("value"), (int, float, str)):
                area = parse_area_m2(str(floor.get("value")))
            if area is None:
                area = parse_area_m2(json.dumps(d, ensure_ascii=False))

            found[abs_url] = Listing(
                site="svenskfast",
                title=title,
                url=abs_url,
                area_m2=area,
                price=price,
            )

    return list(found.values())



def scrape_one(url):
    """
    Returns (listings, warning_message)
    """
    host = urlparse(url).netloc.lower()

    if "fastighetsbyran.com" in host:
        html = fetch_html_requests(url)
        return parse_fastighetsbyran(url, html), None

    if "svenskfast.se" in host:
        html = fetch_html_requests(url)
        return parse_svenskfast(url, html), None

    if "erikolsson.se" in host:

        html = fetch_html_playwright(url)
        if html is None:
            return [], (
                "Skipping erikolsson.se because Playwright is not installed. "
                "Install with: pip install playwright && playwright install chromium"
            )
        return parse_erikolsson(url, html), None

    if "lansfast.se" in host:
        html = fetch_html_playwright(url)
        if html is None:
            return [], "Skipping lansfast.se because Playwright is not installed."
        return parse_lansfast(url, html), None

    return [], f"Skipping unknown domain: {host}"


def read_urls(path):
    urls = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def main():
    webpages_path = APP_DIR / "webpages.txt"
    out_path = APP_DIR / "houses.txt"

    keyword = "Nöbbelöv"
    min_area = 10.0

    if webpages_path.exists():
        urls = read_urls(webpages_path)
    else:
        urls = [
        #bjurfors.se, skandiamaklarna.se, 
        "https://www.svenskfast.se/bostad/skane/lund/lund/",
        "https://www.lansfast.se/till-salu/?areaIds=CMOMRADE4SBR97JRHG5JT9HI&areaNames=N%C3%B6bbel%C3%B6v",
            "https://www.fastighetsbyran.com/sv/sverige/till-salu/skane-lan/lunds-kommun",
            "https://www.erikolsson.se/homes?areaIds=267&city=Lund&label=area%3A267%3AN%C3%B6bbel%C3%B6v",
        ]

    all_lines = []
    for url in urls:
        all_lines.append(f"\n#######\n####### Source: {url} \n")
        try:
            listings, warning = scrape_one(url)
            if warning:
                all_lines.append(warning)
                all_lines.append("")
                continue

            matches = filter_listings(listings, keyword=keyword, min_area_m2=min_area)

            if not matches:
                all_lines.append(f"(No matches for {keyword} with area > {min_area} m²)")
            else:
                for m in sorted(matches, key=lambda x: x.area_m2 or 0, reverse=True):
                    area_str = f"{m.area_m2:.1f} m²" if m.area_m2 is not None else "area ?"
                    all_lines.append(f"{area_str} | {m.price} | {m.title} | {m.url}\n")

        except Exception as e:
            all_lines.append(f"ERROR: {type(e).__name__}: {e}")

        all_lines.append("")
        time.sleep(SLEEP_BETWEEN_REQUESTS_S)

    out_path.write_text("\n".join(all_lines), encoding="utf-8")
    print(f"Wrote {out_path.resolve()}")


if __name__ == "__main__":
    main()
