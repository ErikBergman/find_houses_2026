from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .common import Listing, parse_area_m2, parse_price_sek


def parse_lansfast(url: str, html: str) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    found: dict[str, Listing] = {}

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
