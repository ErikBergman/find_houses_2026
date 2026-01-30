#!/usr/bin/env python3
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from flask import Flask, render_template

APP_DIR = Path(__file__).resolve().parent
HOUSES_FILE = APP_DIR / "houses.txt"

app = Flask(__name__)

@dataclass
class Listing:
    area: str
    price: str
    description: str
    url: str

@dataclass
class Section:
    source_url: str
    listings: List[Listing]

def parse_houses_file(text: str) -> List[Section]:
    sections: List[Section] = []
    current: Optional[Section] = None

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue

        # Example: "####### Source: https://..."
        if line.lower().startswith("####### source:"):
            src = line.split(":", 1)[1].strip()
            current = Section(source_url=src, listings=[])
            sections.append(current)
            continue

        # ignore separator lines like "#######"
        if line.startswith("#######"):
            continue

        # listing line: "82.3 m² | 2895000 | ... | https://..."
        parts = [p.strip() for p in line.split("|")]
        if len(parts) < 4:
            continue

        area = parts[0]
        price = parts[1]
        description = parts[2]
        url = parts[3]

        if current is None:
            current = Section(source_url="(no source header in file)", listings=[])
            sections.append(current)

        current.listings.append(Listing(area=area, price=price, description=description, url=url))

    return sections

@app.get("/")
def index():
    # Read the text file once right before rendering the page
    try:
        text = HOUSES_FILE.read_text(encoding="utf-8")
    except FileNotFoundError:
        text = ""

    sections = parse_houses_file(text)
    return render_template("index.html", sections=sections, houses_file=str(HOUSES_FILE))

if __name__ == "__main__":
    # Localhost server
    app.run(host="127.0.0.1", port=8000, debug=True)