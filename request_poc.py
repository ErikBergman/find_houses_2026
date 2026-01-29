from __future__ import annotations
import json
import os
import sys
from datetime import datetime, timezone


import requests

def main() -> int:
    url = os.getenv("FETCH_URL", "https://httpbin.org/json")
    print(url)
    timeout_s = int(os.getenv("FETCH_TIMEOUT_SECONDS", "20"))

    r = requests.get(url, timeout=timeout_s)
    try:
        data = r.json()
        print("[content_type] json")
        print(json.dumps(data, indent = 2)[:2000])
    except Exception:
        print("[content_type] text")
        print(r.text[:2000])
    return 0

if __name__ == "__main__":
    sys.exit(main())