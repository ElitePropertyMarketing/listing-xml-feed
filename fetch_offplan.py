#!/usr/bin/env python3
"""
fetch_offplan.py
----------------
Fetch every page of the Elite Property International off-plan API, keep only
UAE projects that are NOT yet delivered, and write the qualifying records
to a single JSON file.

Filter
------
- emirate.country_id is 193 (clear UAE bucket)  OR
  emirate.country_id is 182 (mixed bucket) AND emirate.name does not
  contain a non-UAE keyword (Bali / Oman / Phuket / etc.)
- completion_status is NOT 'completed' (case-insensitive)

Pages are fetched in parallel because the source API exposes 12 records
per page and currently returns ~150 pages. Serial fetching would take
several minutes; parallel keeps it under a minute.

Usage:
    python3 fetch_offplan.py [output_path]   # defaults to /tmp/offplan_uae.json

Pure stdlib, no extra packages required.
"""

from __future__ import annotations

import concurrent.futures
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

API_URL = "https://elitepropertydxb.com/api/properties/international"
USER_AGENT = "elitepropertydxb-feed-rebuilder/2.0"

UAE_COUNTRY_IDS = {193, 182}

# Names that, if seen inside emirate.name, mark a record as definitely NOT UAE.
NON_UAE_RE = re.compile(
    r"\b(bali|oman|salalah|yiti|sifah|phuket|thailand|indonesia|nuanu|"
    r"canggu|ubud|bukit|uluwatu|berawa|kuta|sanur|seminyak|cemagi|"
    r"pererenan|seseh|candi\s*dasa|hawana|nai\s*harn|muscat|"
    r"united\s*kingdom|england|scotland|wales|northern\s*ireland|"
    r"london|manchester|birmingham|liverpool|leeds|nottingham|"
    r"sheffield|bristol|newcastle|glasgow|edinburgh|cardiff|belfast)\b",
    re.IGNORECASE,
)


def is_uae(rec: dict) -> bool:
    em = rec.get("emirate") or {}
    if em.get("country_id") not in UAE_COUNTRY_IDS:
        return False
    name = em.get("name") or ""
    if NON_UAE_RE.search(name):
        return False
    return True


def is_active(rec: dict) -> bool:
    """True for any project that has NOT been marked Completed."""
    return (rec.get("completion_status") or "").strip().lower() != "completed"


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
            print(f"  retry {attempt}/{retries} after {sleep}s for {url}: {e}", file=sys.stderr)
            time.sleep(sleep)
    raise SystemExit(f"GET failed after {retries} retries: {url} -- {last_err}")


def main() -> int:
    out_path = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/tmp/offplan_uae.json")

    # Page 1 first to learn the total page count
    print(f"Probing page 1 to discover total pages...", file=sys.stderr)
    first = fetch_json(API_URL + "?page=1")
    pagination = first.get("pagination") or {}
    last_page = int(pagination.get("last_page") or 1)
    total_in_api = pagination.get("total")
    print(f"API reports last_page={last_page}, total={total_in_api}", file=sys.stderr)

    # Collect data from page 1 + remaining pages in parallel
    all_records: list[dict] = list(first.get("data") or [])

    if last_page > 1:
        urls = [f"{API_URL}?page={p}" for p in range(2, last_page + 1)]
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as ex:
            for body in ex.map(fetch_json, urls):
                all_records.extend(body.get("data") or [])

    print(f"Fetched total records           : {len(all_records)}", file=sys.stderr)

    uae = [r for r in all_records if is_uae(r)]
    active = [r for r in uae if is_active(r)]

    print(f"After UAE filter                : {len(uae)}", file=sys.stderr)
    print(f"After UAE + active filter       : {len(active)}", file=sys.stderr)

    out_path.write_text(
        json.dumps({"international": active}, ensure_ascii=False),
        encoding="utf-8",
    )
    print(f"Wrote {out_path}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
