from __future__ import annotations

import json
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .common import Listing, parse_area_m2, parse_price_sek


def parse_jsonld_listings(html: str) -> list[dict]:
    soup = BeautifulSoup(html, "html.parser")
    objs: list[dict] = []
    for tag in soup.select('script[type="application/ld+json"]'):
        raw = (tag.string or "").strip()
        if not raw:
            continue
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            continue

        if isinstance(data, list):
            objs.extend([d for d in data if isinstance(d, dict)])
        elif isinstance(data, dict):
            objs.append(data)
    return objs


def parse_svenskfast(url: str, html: str) -> list[Listing]:
    found: dict[str, Listing] = {}

    for obj in parse_jsonld_listings(html):
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
