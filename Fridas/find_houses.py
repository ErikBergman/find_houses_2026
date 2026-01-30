#!/usr/bin/env python3
from __future__ import annotations

import time
from pathlib import Path
from typing import Iterable
from urllib.parse import urlparse

from parsers.common import (
    Listing,
    fetch_html_playwright,
    fetch_html_requests,
)
from parsers.erikolsson import parse_erikolsson
from parsers.fastighetsbyran import parse_fastighetsbyran
from parsers.lansfast import parse_lansfast
from parsers.svenskfast import parse_svenskfast

APP_DIR = Path(__file__).resolve().parent
SLEEP_BETWEEN_REQUESTS_S = 1.0


def filter_listings(listings: Iterable[Listing], keyword: str, min_area_m2: float) -> list[Listing]:
    kw = keyword.casefold()
    out: list[Listing] = []
    for li in listings:
        if kw not in li.title.casefold():
            continue
        if li.area_m2 is None or li.area_m2 <= min_area_m2:
            continue
        out.append(li)
    return out


def scrape_one(url: str):
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


def read_urls(path: Path) -> list[str]:
    urls: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        urls.append(line)
    return urls


def main() -> None:
    webpages_path = APP_DIR / "webpages.txt"
    out_path = APP_DIR / "houses.txt"

    keyword = "Nöbbelöv"
    min_area = 10.0

    if webpages_path.exists():
        urls = read_urls(webpages_path)
    else:
        urls = [
            # bjurfors.se, skandiamaklarna.se,
            "https://www.svenskfast.se/bostad/skane/lund/lund/",
            "https://www.lansfast.se/till-salu/?areaIds=CMOMRADE4SBR97JRHG5JT9HI&areaNames=N%C3%B6bbel%C3%B6v",
            "https://www.fastighetsbyran.com/sv/sverige/till-salu/skane-lan/lunds-kommun",
            "https://www.erikolsson.se/homes?areaIds=267&city=Lund&label=area%3A267%3AN%C3%B6bbel%C3%B6v",
        ]

    all_lines: list[str] = []
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
