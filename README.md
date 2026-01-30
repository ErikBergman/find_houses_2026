# Project overview

This repo is a proof-of-concept housing watcher. It scrapes listing pages from a few housing companies, filters the results, and notifies a Telegram bot when new ads appear. A GitHub Actions workflow runs the scraper on a schedule so notifications happen without a local machine running all day.

# Development history and why some files are unused

The repo started with small experiments to validate scraping and HTML extraction:

- `request_poc.py` was an early sanity check for fetching a URL and printing content.
- `html_change_poc.py` plus `resources/config.json` was a separate experiment for XPath extraction and logging HTML changes.
- `logs/` holds those PoC logs.

The newer WIP lives in `Fridas/`. It contains the actual scraper, Telegram diffing logic, and a small Flask app for local viewing. The static `Fridas/untitled folder/index.html` is an early UI mock and is not wired into the Flask app. Local `__pycache__` files are build artifacts and not part of the project logic.

# File map

- `.github/workflows/scheduled-fetch.yml` — scheduled GitHub Actions job that runs the scraper, checks for new ads, and sends Telegram messages.
- `requirements.txt` — Python dependencies for the workflow and local runs.
- `.gitignore` — ignores generated artifacts like logs and scraper outputs.
- `request_poc.py` — legacy PoC fetch script (unused in the current workflow).
- `html_change_poc.py` — legacy PoC for XPath HTML extraction (unused in the current workflow).
- `resources/config.json` — config for `html_change_poc.py`.
- `logs/` — PoC logs from `html_change_poc.py`.

`Fridas/` (main WIP):
- `Fridas/find_houses.py` — orchestrates scraping and filtering, writes `Fridas/houses.txt`.
- `Fridas/check_new_ads.py` — compares current listings to cached URLs and prepares Telegram messages.
- `Fridas/app.py` — Flask app that reads `Fridas/houses.txt` and renders a page (template missing; not used in CI).
- `Fridas/untitled folder/index.html` — static mockup; not connected to the Flask app.
- `Fridas/parsers/common.py` — shared fetch + parsing helpers and the `Listing` dataclass.
- `Fridas/parsers/fastighetsbyran.py` — parser for fastighetsbyran.com.
- `Fridas/parsers/erikolsson.py` — parser for erikolsson.se (Next.js JSON + fallback).
- `Fridas/parsers/lansfast.py` — parser for lansfast.se.
- `Fridas/parsers/svenskfast.py` — parser for svenskfast.se.
- `Fridas/parsers/__init__.py` — exports parser symbols.
- `Fridas/state/seen_urls.json` — generated cache of seen listings (created in CI).
- `Fridas/houses.txt` — generated output file (created by `find_houses.py`).

# Suggested next steps

1. Add a real config layer (YAML/JSON) for sources, filters, and keywords so the scraper is not hard-coded.
2. Introduce a small persistent store (SQLite or JSONL) for listing history, not just URLs, to track price/area changes.
3. Add parser tests + HTML fixtures so site changes are detected before production runs.
