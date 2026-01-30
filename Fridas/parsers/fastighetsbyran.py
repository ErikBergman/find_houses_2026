from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .common import Listing, parse_area_m2, parse_price_sek


def parse_fastighetsbyran(url: str, html: str) -> list[Listing]:
    """
    Fastighetsbyrån pages tend to include listing rows as text in the HTML.
    Heuristic: anchor links containing 'objekt' or 'objektID' and nearby text contains area.
    """
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, Listing] = {}

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
        found[abs_url] = Listing(
            site="fastighetsbyran",
            title=text,
            url=abs_url,
            area_m2=area,
            price=price,
        )

    return list(found.values())
