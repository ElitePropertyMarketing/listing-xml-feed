#!/usr/bin/env python3
"""
Elite Property DXB - XML feed rebuilder

Reads the source CRM feed (with 25+ agents) and rewrites every property's
<agent> block so that the resulting feed only contains 6 chosen agents.

Rules
-----
1. Listings already owned by one of the 6 target agents stay with that agent
   (no listing is moved between target agents).
2. Listings owned by anyone else are reassigned by offering_type using a
   round-robin across the agents the user nominated for that offering type.
3. Every listing in the source feed is preserved byte-for-byte except for
   the <agent>...</agent> block, which is replaced with a standardized one.
4. Output is well-formed XML and the listing_count attribute is updated to
   the actual number of properties found.

Run:
    python3 rebuild_feed.py feed.xml > new_feed.xml
"""

from __future__ import annotations

import hashlib
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import quote


# --------------------------------------------------------------------------
# 1. Target agents -- single source of truth.  Anything we publish about
#    these agents on the integrating website comes from here.
# --------------------------------------------------------------------------

def _hash_id(email: str) -> str:
    """Stable MD5-hex id derived from email -- matches the format used by
    the source CRM, which we want to keep so portals that key on <id> don't
    break."""
    return hashlib.md5(email.encode("utf-8")).hexdigest()


TARGET_AGENTS = {
    # key = lowercase email
    "evelyn@elitepropertydxb.com": {
        "id": "83efe5eb66e3ce15cb3e70a0243f02e9",
        "name": "Evelyn Oprea",
        "email": "evelyn@elitepropertydxb.com",
        "phone": "971586487299",
        "photo": "https://crm.elitepropertydxb.com/upload/main/6fc/fqph3u8mq7vneyu15c2q7xxf3kia325d/Evelyn.jpg",
        "license_no": "58890",
    },
    "alba@elitepropertydxb.com": {
        "id": "c5580cfa13d1115afebf1a72c5c089bc",
        "name": "Alba Cavallo Esclapez",
        "email": "alba@elitepropertydxb.com",
        "phone": "971585314404",
        "photo": "https://crm.elitepropertydxb.com/upload/main/2df/wf3vhx9at4np6hx0wxqq85q400jgt0vp/Alba.jpg",
        "license_no": "52792",
    },
    "diana@elitepropertydxb.com": {
        "id": "ff3f510582d2030834b395ab918c407f",
        "name": "Diana David",
        "email": "diana@elitepropertydxb.com",
        "phone": "971524065513",
        "photo": "https://crm.elitepropertydxb.com/upload/main/8e7/j90x9pfad2rlvpk1v90qsla86hv32oyn/Diana.jpg",
        "license_no": "59808",
    },
    "aaron@elitepropertydxb.com": {
        "id": "ba3b75f23eb01843c37b0e4f0eaa12ed",
        "name": "Aaron Leo",
        "email": "aaron@elitepropertydxb.com",
        "phone": "971567548787",
        "photo": "https://crm.elitepropertydxb.com/upload/main/e37/kp1bllyasjt7su5oj11kdu7m0muhp2bu/Aaron.jpg",
        "license_no": "41517",
    },
    "jake@elitepropertydxb.com": {
        "id": "df9390898c90eb1cdc9b149d1451b327",
        "name": "Jake Jones",
        "email": "jake@elitepropertydxb.com",
        "phone": "971565055043",
        "photo": "https://crm.elitepropertydxb.com/upload/main/2dc/m5tmydxc1s8cu0rxhzc48jyedtfpz7ju/Jake.jpg",
        "license_no": "37157",
    },
    "jennifer@elitepropertydxb.com": {
        "id": _hash_id("jennifer@elitepropertydxb.com"),
        "name": "Jennifer Gorodetski",
        "email": "jennifer@elitepropertydxb.com",
        "phone": "971547223923",
        # Source URL contains spaces -- URL-encode them so portals don't 404.
        "photo": (
            "https://crm.elitepropertydxb.com/upload/main/cc2/"
            "w38yu03o7n09nmmjg2qs1o5jl6uh4u8j/"
            + quote("WhatsApp Image 2026-02-05 at 5.58.56 PM.png")
        ),
        "license_no": "",
    },
}


# --------------------------------------------------------------------------
# 2. Routing rules per offering_type (provided by the user).  Each list is
#    used as a round-robin pool; the order matters for fairness.
# --------------------------------------------------------------------------

ROUTING = {
    "RS": [   # Residential Sale -- 488 listings
        "evelyn@elitepropertydxb.com",
        "alba@elitepropertydxb.com",
        "diana@elitepropertydxb.com",
        "aaron@elitepropertydxb.com",
    ],
    "RR": [   # Residential Rent -- 294 listings
        "jennifer@elitepropertydxb.com",
        "evelyn@elitepropertydxb.com",
    ],
    "CS": [   # Commercial Sale -- 53 listings
        "jake@elitepropertydxb.com",
        "alba@elitepropertydxb.com",
        "aaron@elitepropertydxb.com",
    ],
    "CR": [   # Commercial Rent -- 5 listings
        "aaron@elitepropertydxb.com",
        "jake@elitepropertydxb.com",
    ],
}

# Fallback if a property has no/unknown offering_type -- spread across all 6.
FALLBACK_POOL = list(TARGET_AGENTS.keys())


# --------------------------------------------------------------------------
# 3. XML helpers (regex-based -- avoids ElementTree re-serialising and
#    breaking CDATA / Arabic content).
# --------------------------------------------------------------------------

PROPERTY_RE = re.compile(
    r"<property\b[^>]*>.*?</property>",
    re.DOTALL,
)
AGENT_RE = re.compile(
    r"<agent>.*?</agent>",
    re.DOTALL,
)
OFFERING_RE = re.compile(
    r"<offering_type>\s*<!\[CDATA\[([^\]]*)\]\]>\s*</offering_type>",
    re.DOTALL,
)
EMAIL_RE = re.compile(
    r"<agent>.*?<email>\s*<!\[CDATA\[([^\]]*)\]\]>\s*</email>.*?</agent>",
    re.DOTALL,
)
LIST_OPEN_RE = re.compile(r"<list\b([^>]*)>")
LISTING_COUNT_RE = re.compile(r'listing_count="(\d+)"')


def render_agent_block(a: dict) -> str:
    """Re-create an <agent> block in the exact shape the source feed uses."""
    return (
        "<agent>"
        f"<id><![CDATA[{a['id']}]]></id>"
        f"<name><![CDATA[{a['name']}]]></name>"
        f"<email><![CDATA[{a['email']}]]></email>"
        f"<phone><![CDATA[{a['phone']}]]></phone>"
        f"<photo><![CDATA[{a['photo']}]]></photo>"
        f"<license_no><![CDATA[{a['license_no']}]]></license_no>"
        "</agent>"
    )


# --------------------------------------------------------------------------
# 4. Main rewrite logic
# --------------------------------------------------------------------------

def rebuild(xml_text: str) -> tuple[str, dict]:
    properties = PROPERTY_RE.findall(xml_text)
    if not properties:
        raise SystemExit("No <property> blocks found -- input does not look like the expected feed")

    # Round-robin counters per pool
    pool_index: dict[str, int] = {k: 0 for k in ROUTING}
    pool_index["__fallback__"] = 0

    stats = {
        "total": len(properties),
        "kept_with_owner": Counter(),       # listings already on a target agent
        "reassigned_by_pool": Counter(),    # listings reassigned per offering_type
        "assigned_to": Counter(),           # final per-agent count
        "missing_agent_block": 0,
        "fallback_used": 0,
    }

    new_properties: list[str] = []

    for prop in properties:
        # Detect current agent's email
        m_email = EMAIL_RE.search(prop)
        current_email = m_email.group(1).strip().lower() if m_email else ""

        # Detect offering type
        m_off = OFFERING_RE.search(prop)
        offering = (m_off.group(1).strip().upper() if m_off else "")

        # Decide which agent to use
        if current_email in TARGET_AGENTS:
            chosen_email = current_email
            stats["kept_with_owner"][chosen_email] += 1
        else:
            pool = ROUTING.get(offering)
            if not pool:
                pool = FALLBACK_POOL
                stats["fallback_used"] += 1
                key = "__fallback__"
            else:
                key = offering
            chosen_email = pool[pool_index[key] % len(pool)]
            pool_index[key] += 1
            stats["reassigned_by_pool"][offering or "?"] += 1

        agent_block = render_agent_block(TARGET_AGENTS[chosen_email])

        if AGENT_RE.search(prop):
            new_prop = AGENT_RE.sub(agent_block, prop, count=1)
        else:
            # If a property had no <agent> at all, append one before </property>
            stats["missing_agent_block"] += 1
            new_prop = prop.replace("</property>", agent_block + "</property>", 1)

        new_properties.append(new_prop)
        stats["assigned_to"][chosen_email] += 1

    # Stitch the document back together: keep the original <list ...> opening
    # but update listing_count to the actual count, and emit a clean </list>.
    list_open_match = LIST_OPEN_RE.search(xml_text)
    if not list_open_match:
        raise SystemExit("Could not find <list ...> opening tag in source")

    list_attrs = list_open_match.group(1)
    new_count = str(len(new_properties))
    if LISTING_COUNT_RE.search(list_attrs):
        list_attrs = LISTING_COUNT_RE.sub(f'listing_count="{new_count}"', list_attrs)
    else:
        list_attrs = list_attrs.rstrip() + f' listing_count="{new_count}"'

    output = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        f"<list{list_attrs}>"
        + "".join(new_properties)
        + "</list>\n"
    )
    return output, stats


def main() -> int:
    src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("feed.xml")
    out = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("new_feed.xml")
    xml_text = src.read_text(encoding="utf-8")
    new_xml, stats = rebuild(xml_text)
    out.write_text(new_xml, encoding="utf-8")

    # Report
    sys.stderr.write(f"Input  : {src}  ({len(xml_text):,} bytes)\n")
    sys.stderr.write(f"Output : {out}  ({len(new_xml):,} bytes)\n")
    sys.stderr.write(f"Properties processed     : {stats['total']}\n")
    sys.stderr.write(f"Kept with current owner  : {sum(stats['kept_with_owner'].values())}\n")
    sys.stderr.write(f"Reassigned via pool      : {sum(stats['reassigned_by_pool'].values())}\n")
    sys.stderr.write(f"Fallback pool used       : {stats['fallback_used']}\n")
    sys.stderr.write(f"Properties missing agent : {stats['missing_agent_block']}\n")
    sys.stderr.write("\nFinal counts per agent:\n")
    for email, n in stats["assigned_to"].most_common():
        sys.stderr.write(f"  {n:5d}  {TARGET_AGENTS[email]['name']:30s}  ({email})\n")
    sys.stderr.write("\nReassigned per offering_type:\n")
    for off, n in stats["reassigned_by_pool"].most_common():
        sys.stderr.write(f"  {n:5d}  {off}\n")
    sys.stderr.write("\nKept (already owned by target agent):\n")
    for email, n in stats["kept_with_owner"].most_common():
        sys.stderr.write(f"  {n:5d}  {TARGET_AGENTS[email]['name']:30s}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
