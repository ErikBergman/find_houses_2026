from __future__ import annotations

import json
import re
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .common import Listing, parse_area_m2, parse_price_sek


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


def parse_erikolsson(url: str, html: str) -> list[Listing]:
    """
    Prefer Next.js embedded JSON (stable), fall back to DOM scraping if missing.
    Produces Listing(site,title,url,area_m2,price).
    """
    # 1) Try Next.js JSON
    data = extract_next_data(html)
    if data:
        found: dict[str, Listing] = {}

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
            parts: list[str] = []
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

    # 2) Fallback: DOM heuristic
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, Listing] = {}

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
