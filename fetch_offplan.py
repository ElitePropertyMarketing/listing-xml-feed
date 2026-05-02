#!/usr/bin/env python3
"""
fetch_offplan.py
----------------
Fetch every page of the two off-plan APIs and write a single combined
JSON file to disk.

APIs:
- International:  https://elitepropertydxb.com/api/properties/international
- UK:             https://elitepropertydxb.com/api/properties/uk-properties

Both expose a Laravel-style paginator: each page response has a `data`
list and a `pagination` object with `next_page_url`. We follow
`next_page_url` until it's null.

Usage:
    python3 fetch_offplan.py [output_path]

Output JSON shape:
    {
      "international": [<record>, ...],
      "uk":            [<record>, ...]
    }

Pure stdlib, no extra packages required.
"""

from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

SOURCES = {
    "international": "https://elitepropertydxb.com/api/properties/international",
    "uk":            "https://elitepropertydxb.com/api/properties/uk-properties",
}

USER_AGENT = "elitepropertydxb-feed-rebuilder/1.0 (+github.com/ElitePropertyMarketing/listing-xml-feed)"


def fetch_json(url: str, *, retries: int = 3, timeout: int = 30) -> dict[str, Any]:
    last_err: Exception | None = None
    for attempt in range(1, retries + 1):
        try:
            req = urllib.request.Request(url, headers={
                "Accept": "application/json",
                "User-Agent": USER_AGENT,
            })
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8"))
        except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError) as e:
            last_err = e
            sleep = attempt * 2
            print(f"  retry {attempt}/{retries} after {sleep}s: {e}", file=sys.stderr)
            time.sleep(sleep)
    raise SystemExit(f"GET failed after {retries} retries: {url} -- {last_err}")


def fetch_all_pages(start_url: str) -> list[dict]:
    out: list[dict] = []
    url = start_url
    page = 1
    while url:
        print(f"  page {page}: {url}", file=sys.stderr)
        body = fetch_json(url)
        data = body.get("data", [])
        out.extend(data)
        pagination = body.get("pagination") or {}
        url = pagination.get("next_page_url")
        page += 1
        if page > 200:
            print("  refusing to follow more than 200 pages -- stopping", file=sys.stderr)
            break
    return out


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/offplan_all.json")

    bundle: dict[str, list[dict]] = {}
    for name, url in SOURCES.items():
        print(f"Fetching {name}: {url}", file=sys.stderr)
        records = fetch_all_pages(url)
        print(f"  got {len(records)} records", file=sys.stderr)
        bundle[name] = records

    out_path.write_text(json.dumps(bundle, ensure_ascii=False), encoding="utf-8")
    print(f"\nWrote {out_path}: "
          f"international={len(bundle['international'])}, uk={len(bundle['uk'])}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
