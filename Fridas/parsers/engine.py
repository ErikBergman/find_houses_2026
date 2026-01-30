from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from .common import (
    Listing,
    fetch_html_playwright,
    fetch_html_requests,
    parse_area_m2,
    parse_price_sek,
)


def load_sources(path: Path) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    sources = data.get("sources")
    if not isinstance(sources, list):
        raise ValueError("sources.json must contain a list under 'sources'")
    return [s for s in sources if isinstance(s, dict)]


def select_source(sources: Iterable[dict[str, Any]], url: str) -> dict[str, Any] | None:
    host = url.split("//")[-1].split("/")[0].lower()
    for source in sources:
        hosts = source.get("match_hosts", [])
        if any(isinstance(h, str) and h in host for h in hosts):
            return source
    return None


def fetch_html(url: str, source: dict[str, Any]) -> str | None:
    fetcher = source.get("fetch", "requests")
    if fetcher == "playwright":
        return fetch_html_playwright(url)
    return fetch_html_requests(url)


def _walk_dicts(obj: Any) -> Iterable[dict[str, Any]]:
    if isinstance(obj, dict):
        yield obj
        for v in obj.values():
            yield from _walk_dicts(v)
    elif isinstance(obj, list):
        for it in obj:
            yield from _walk_dicts(it)


def _get_nested(obj: dict[str, Any], dotted: str) -> Any:
    cur: Any = obj
    for part in dotted.split("."):
        if not isinstance(cur, dict):
            return None
        cur = cur.get(part)
    return cur


def parse_link_text(url: str, html: str, source: dict[str, Any]) -> list[Listing]:
    soup = BeautifulSoup(html, "html.parser")
    href_includes = [h for h in source.get("href_includes", []) if isinstance(h, str)]
    href_excludes = [h for h in source.get("href_excludes", []) if isinstance(h, str)]
    href_exclude_exact = [
        h.strip().lower()
        for h in source.get("href_exclude_exact", [])
        if isinstance(h, str)
    ]
    max_depth = int(source.get("text_container_max_depth", 8))
    require_area_or_price = bool(source.get("require_area_or_price", True))
    found: dict[str, Listing] = {}

    for a in soup.select("a[href]"):
        href = a.get("href", "")
        if not href or not isinstance(href, str):
            continue

        if href_includes and not any(h in href for h in href_includes):
            continue
        if href_excludes and any(h in href for h in href_excludes):
            continue
        if href_exclude_exact:
            if href.rstrip("/").lower() in href_exclude_exact:
                continue

        abs_url = urljoin(url, href)

        best_text = ""
        if max_depth <= 0:
            best_text = " ".join(a.get_text(" ", strip=True).split())
        else:
            node = a
            for _ in range(max_depth):
                node = node.parent
                if node is None:
                    break
                text = " ".join(node.get_text(" ", strip=True).split())
                if not text:
                    continue
                if not require_area_or_price:
                    best_text = text
                    break
                has_price = "kr" in text.lower()
                has_area = ("m²" in text) or ("kvm" in text.lower()) or ("m&#178;" in text.lower())
                if has_price or has_area:
                    best_text = text
                    break

        combined = best_text or " ".join(a.get_text(" ", strip=True).split())
        if not combined:
            continue

        area = parse_area_m2(combined)
        price = parse_price_sek(combined)

        found[abs_url] = Listing(
            site=str(source.get("id", "unknown")),
            title=combined,
            url=abs_url,
            area_m2=area,
            price=price,
        )

    return list(found.values())


def _parse_jsonld_listings(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    objs: list[dict[str, Any]] = []
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


def parse_jsonld(url: str, html: str, source: dict[str, Any]) -> list[Listing]:
    found: dict[str, Listing] = {}
    url_field = str(source.get("listing_url_field", "url"))
    title_fields = source.get("title_fields", {})
    address_map = title_fields.get("address", {}) if isinstance(title_fields, dict) else {}
    name_key = ""
    if isinstance(title_fields, dict):
        name_key = str(title_fields.get("name", "")).strip()

    price_fields = [p for p in source.get("price_fields", []) if isinstance(p, str)]
    area_fields = [a for a in source.get("area_fields", []) if isinstance(a, str)]

    for obj in _parse_jsonld_listings(html):
        graph = obj.get("@graph")
        candidates = graph if isinstance(graph, list) else [obj]

        for d in candidates:
            if not isinstance(d, dict):
                continue

            rel = d.get(url_field)
            if not isinstance(rel, str):
                continue

            abs_url = urljoin(url, rel)

            name = d.get(name_key) if name_key else ""
            name = name if isinstance(name, str) else ""
            address = d.get("address") if isinstance(d.get("address"), dict) else {}
            street = address.get(address_map.get("street", "")) if isinstance(address, dict) else ""
            locality = address.get(address_map.get("locality", "")) if isinstance(address, dict) else ""
            title = " ".join(x for x in [street, locality] if isinstance(x, str) and x).strip() or name or abs_url

            price = None
            for key in price_fields:
                v = _get_nested(d, key)
                if isinstance(v, (int, float, str)):
                    price = parse_price_sek(str(v))
                    if price is not None:
                        break

            area = None
            for key in area_fields:
                v = _get_nested(d, key)
                if isinstance(v, (int, float, str)):
                    area = parse_area_m2(str(v))
                    if area is not None:
                        break
            if area is None:
                area = parse_area_m2(json.dumps(d, ensure_ascii=False))

            found[abs_url] = Listing(
                site=str(source.get("id", "unknown")),
                title=title,
                url=abs_url,
                area_m2=area,
                price=price,
            )

    return list(found.values())


def _extract_next_data(html: str) -> dict[str, Any] | None:
    m = re.search(r'<script[^>]+id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(1))
    except json.JSONDecodeError:
        return None


def parse_next_data(url: str, html: str, source: dict[str, Any]) -> list[Listing]:
    cfg = source.get("next_data", {}) if isinstance(source.get("next_data"), dict) else {}
    url_fields = [u for u in cfg.get("url_fields", []) if isinstance(u, str)]
    url_includes = [u for u in cfg.get("url_includes", []) if isinstance(u, str)]
    url_prefix = str(cfg.get("url_prefix", "")).strip()
    title_fields = [t for t in cfg.get("title_fields", []) if isinstance(t, str)]
    area_fields = [a for a in cfg.get("area_fields", []) if isinstance(a, str)]
    price_fields = [p for p in cfg.get("price_fields", []) if isinstance(p, str)]

    data = _extract_next_data(html)
    if not data:
        return []

    found: dict[str, Listing] = {}

    for d in _walk_dicts(data):
        rel = None
        for key in url_fields:
            val = d.get(key)
            if isinstance(val, str):
                rel = val
                break
        if not rel:
            continue
        if url_includes and not any(u in rel for u in url_includes):
            continue
        if rel.rstrip("/").lower() == "/homes":
            continue

        abs_url = urljoin(url_prefix or url, rel)

        parts: list[str] = []
        for v in d.values():
            if isinstance(v, str) and v.strip():
                parts.append(v.strip())
        combined = " | ".join(parts[:12])

        area = None
        price = None
        for key in area_fields:
            v = d.get(key)
            if isinstance(v, (int, float)) and v > 0:
                area = float(v)
                break
        for key in price_fields:
            v = d.get(key)
            if isinstance(v, int) and v > 0:
                price = v
                break
        if area is None and combined:
            area = parse_area_m2(combined)
        if price is None and combined:
            price = parse_price_sek(combined)

        title = ""
        for key in title_fields:
            v = d.get(key)
            if isinstance(v, str) and v.strip():
                title = v.strip()
                break
        if not title:
            title = combined or abs_url

        found[abs_url] = Listing(
            site=str(source.get("id", "unknown")),
            title=title,
            url=abs_url,
            area_m2=area,
            price=price,
        )

    return list(found.values())


def _apply_overrides(source: dict[str, Any], overrides: dict[str, Any]) -> dict[str, Any]:
    merged = dict(source)
    for key, value in overrides.items():
        merged[key] = value
    return merged


def parse_listings(url: str, html: str, source: dict[str, Any]) -> list[Listing]:
    strategy = source.get("strategy")
    if strategy == "link_text":
        return parse_link_text(url, html, source)
    if strategy == "jsonld":
        return parse_jsonld(url, html, source)
    if strategy == "next_data":
        listings = parse_next_data(url, html, source)
        if listings:
            return listings
        fallback = source.get("fallback")
        if isinstance(fallback, dict):
            fallback_source = _apply_overrides(source, fallback)
            if fallback_source.get("strategy") == "link_text":
                return parse_link_text(url, html, fallback_source)
        return []
    return []
