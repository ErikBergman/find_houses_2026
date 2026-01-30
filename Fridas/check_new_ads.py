#!/usr/bin/env python3
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable

APP_DIR = Path(__file__).resolve().parent
STATE_DIR = APP_DIR / "state"
STATE_FILE = STATE_DIR / "seen_urls.json"
HOUSES_FILE = APP_DIR / "houses.txt"


def load_seen_urls() -> set[str]:
    if not STATE_FILE.exists():
        return set()
    try:
        data = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    except Exception:
        return set()
    if isinstance(data, list):
        return {str(x) for x in data}
    if isinstance(data, dict) and isinstance(data.get("urls"), list):
        return {str(x) for x in data["urls"]}
    return set()


def save_seen_urls(urls: Iterable[str]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    payload = sorted(set(urls))
    STATE_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def parse_listings(text: str) -> list[tuple[str, str]]:
    listings: list[tuple[str, str]] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#######") or line.startswith("ERROR:"):
            continue
        if line.startswith("Skipping") or line.startswith("(No matches"):
            continue
        if "|" not in line:
            continue

        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue
        url = parts[-1]
        if not (url.startswith("http://") or url.startswith("https://")):
            continue
        listings.append((url, line))
    return listings


def write_output(name: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if not path:
        return
    with open(path, "a", encoding="utf-8") as f:
        if "\n" in value:
            f.write(f"{name}<<EOF\n{value}\nEOF\n")
        else:
            f.write(f"{name}={value}\n")


def main() -> int:
    if not HOUSES_FILE.exists():
        print(f"[warn] Missing houses file: {HOUSES_FILE}")
        write_output("new_ads_count", "0")
        write_output("message", "No houses file produced.")
        return 0

    text = HOUSES_FILE.read_text(encoding="utf-8")
    listings = parse_listings(text)

    current_urls = [url for url, _ in listings]
    seen_urls = load_seen_urls()

    new_listings = [(url, line) for url, line in listings if url not in seen_urls]
    new_urls = [url for url, _ in new_listings]

    # Persist union so we don't re-notify for old ads
    save_seen_urls(set(seen_urls).union(current_urls))

    run_url = os.getenv("RUN_URL", "").strip()
    if new_listings:
        lines = [f"🏠 New ads found: {len(new_listings)}"]
        lines.extend(line for _, line in new_listings)
        if run_url:
            lines.append(f"Run: {run_url}")
        message = "\n".join(lines)
    else:
        message = "No new ads."

    write_output("new_ads_count", str(len(new_listings)))
    write_output("message", message)

    if new_urls:
        print(f"[new_ads] {len(new_urls)}")
    else:
        print("[new_ads] 0")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
