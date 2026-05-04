#!/usr/bin/env python3
"""
Elite Property DXB - XML feed rebuilder.

Reads the source CRM (Bitrix24) XML feed and rewrites every property's
<agent> block so the output only contains 6 chosen agents. Optionally
merges UAE off-plan projects from the Reelly API and assigns those
listings via an equal round-robin across the 6 agents.

Usage
-----
    python3 rebuild_feed.py feed.xml new_feed.xml
    python3 rebuild_feed.py feed.xml new_feed.xml --offplan offplan_uae.json
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote


# ---------------------------------------------------------------------------
# Target agents
# ---------------------------------------------------------------------------

def _hash_id(email: str) -> str:
    return hashlib.md5(email.encode("utf-8")).hexdigest()


TARGET_AGENTS = {
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
        "photo": (
            "https://crm.elitepropertydxb.com/upload/main/cc2/"
            "w38yu03o7n09nmmjg2qs1o5jl6uh4u8j/"
            + quote("WhatsApp Image 2026-02-05 at 5.58.56 PM.png")
        ),
        "license_no": "",
    },
}

ROUTING = {
    "RS": [
        "evelyn@elitepropertydxb.com",
        "alba@elitepropertydxb.com",
        "diana@elitepropertydxb.com",
        "aaron@elitepropertydxb.com",
    ],
    "RR": [
        "jennifer@elitepropertydxb.com",
        "evelyn@elitepropertydxb.com",
    ],
    "CS": [
        "jake@elitepropertydxb.com",
        "alba@elitepropertydxb.com",
        "aaron@elitepropertydxb.com",
    ],
    "CR": [
        "aaron@elitepropertydxb.com",
        "jake@elitepropertydxb.com",
    ],
}

FALLBACK_POOL = list(TARGET_AGENTS.keys())


# ---------------------------------------------------------------------------
# XML helpers
# ---------------------------------------------------------------------------

PROPERTY_RE = re.compile(r"<property\b[^>]*>.*?</property>", re.DOTALL)
AGENT_RE = re.compile(r"<agent>.*?</agent>", re.DOTALL)
OFFERING_RE = re.compile(r"<offering_type>\s*<!\[CDATA\[([^\]]*)\]\]>\s*</offering_type>", re.DOTALL)
EMAIL_RE = re.compile(r"<agent>.*?<email>\s*<!\[CDATA\[([^\]]*)\]\]>\s*</email>.*?</agent>", re.DOTALL)
LIST_OPEN_RE = re.compile(r"<list\b([^>]*)>")
LISTING_COUNT_RE = re.compile(r'listing_count="(\d+)"')


def render_agent_block(a: dict) -> str:
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


# XML 1.0 disallows most control characters (everything in 0x00-0x1F except
# \t \n \r). Reelly descriptions sometimes contain stray bytes like \x1d
# (Group Separator) that break parsers downstream. Strip them.
_XML_ILLEGAL_CTRL_RE = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")


def _cdata(value) -> str:
    if value is None:
        return ""
    s = str(value)
    s = _XML_ILLEGAL_CTRL_RE.sub("", s)
    return s.replace("]]>", "]]]]><![CDATA[>")


_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


def _strip_html(value) -> str:
    if not value:
        return ""
    text = html.unescape(_TAG_RE.sub(" ", str(value)))
    return _WS_RE.sub(" ", text).strip()


def _now_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%y-%m-%d %H:%M:%S")


def _xml_completion(api_status) -> str:
    """Map Reelly's status vocab to the CRM feed vocab."""
    s = (api_status or "").strip().lower()
    if s in {"completed", "complete", "current", "ready"}:
        return "completed"
    return "off_plan"


def _intl_block(rec: dict, agent_email: str, stamp: str) -> str:
    rid = rec.get("id")
    if rid is None:
        return ""
    pid = 500000 + int(rid)
    ref = rec.get("reference_number") or f"REELLY-{rid}"
    title = rec.get("title_en") or rec.get("property_name") or ref
    desc = rec.get("description_en") or ""
    price = rec.get("price") or "0"
    offering = (rec.get("offering_type") or "RS").upper()
    ptype = (rec.get("property_type") or "AP").upper()
    size = rec.get("size") or "0"
    bedroom = rec.get("bedroom") or "0"
    bathroom = rec.get("bathroom") or "0"
    completion = _xml_completion(rec.get("completion_status"))

    emirate = rec.get("emirate") or {}
    location_name = emirate.get("name") or rec.get("city") or "UAE"
    if "," in location_name:
        city = location_name.split(",")[-1].strip()
    else:
        city = location_name
    community = location_name
    sub_community = location_name

    photos = rec.get("photos") or []
    photo_urls = [(p.get("url") or "").strip() for p in photos if p.get("url")]

    parts = [
        f'<property last_update="{stamp}" id="{pid}">',
        f"<reference_number><![CDATA[{_cdata(ref)}]]></reference_number>",
        f"<price><![CDATA[{_cdata(price)}]]></price>",
        f"<price_currency><![CDATA[{_cdata(rec.get('price_currency') or 'AED')}]]></price_currency>",
        f"<offering_type><![CDATA[{_cdata(offering)}]]></offering_type>",
        f"<property_type><![CDATA[{_cdata(ptype)}]]></property_type>",
        f"<city><![CDATA[{_cdata(city)}]]></city>",
        f"<community><![CDATA[{_cdata(community)}]]></community>",
        f"<sub_community><![CDATA[{_cdata(sub_community)}]]></sub_community>",
        f"<title_en><![CDATA[{_cdata(title)}]]></title_en>",
        f"<description_en><![CDATA[{_cdata(desc)}]]></description_en>",
        f"<size><![CDATA[{_cdata(size)}]]></size>",
        f"<bedroom><![CDATA[{_cdata(bedroom)}]]></bedroom>",
        f"<bathroom><![CDATA[{_cdata(bathroom)}]]></bathroom>",
        f"<completion_status><![CDATA[{_cdata(completion)}]]></completion_status>",
        f"<developer><![CDATA[{_cdata(rec.get('developer') or '')}]]></developer>",
        "<source><![CDATA[reelly-uae-offplan]]></source>",
        render_agent_block(TARGET_AGENTS[agent_email]),
    ]
    if photo_urls:
        photo_section = ["<photo>"]
        for u in photo_urls[:30]:
            photo_section.append(f'<url last_update="{stamp}" watermark="No"><![CDATA[{_cdata(u)}]]></url>')
            photo_section.append(f"<original_url><![CDATA[{_cdata(u)}]]></original_url>")
        photo_section.append("</photo>")
        parts.append("".join(photo_section))
    parts.append("<is_featured><![CDATA[0]]></is_featured>")
    parts.append("<is_exclusive><![CDATA[0]]></is_exclusive>")
    parts.append("<branch><![CDATA[Off-Plan UAE]]></branch>")
    parts.append("</property>")
    return "".join(parts)


def build_offplan_blocks(json_path: Path) -> tuple[list[str], Counter]:
    """Read pre-filtered UAE off-plan JSON and return XML <property> blocks
    plus a Counter of how many were assigned to each agent (equal round-robin
    across all 6 target agents)."""
    data = json.loads(json_path.read_text(encoding="utf-8"))
    stamp = _now_stamp()

    pool = list(TARGET_AGENTS.keys())
    rr = [0]
    per_agent: Counter = Counter()

    def next_agent() -> str:
        e = pool[rr[0] % len(pool)]
        rr[0] += 1
        per_agent[e] += 1
        return e

    blocks: list[str] = []
    for rec in (data.get("international") or []):
        b = _intl_block(rec, next_agent(), stamp)
        if b:
            blocks.append(b)
    return blocks, per_agent


# ---------------------------------------------------------------------------
# CRM rewrite
# ---------------------------------------------------------------------------

def rebuild(xml_text: str, extra_property_blocks: list[str] | None = None) -> tuple[str, dict]:
    properties = PROPERTY_RE.findall(xml_text)
    if not properties:
        raise SystemExit("No <property> blocks found in source")
    if extra_property_blocks:
        properties.extend(extra_property_blocks)

    pool_index = {k: 0 for k in ROUTING}
    pool_index["__fallback__"] = 0

    stats = {
        "total": len(properties),
        "kept_with_owner": Counter(),
        "reassigned_by_pool": Counter(),
        "assigned_to": Counter(),
        "missing_agent_block": 0,
        "fallback_used": 0,
    }

    new_properties: list[str] = []
    for prop in properties:
        m_email = EMAIL_RE.search(prop)
        current_email = m_email.group(1).strip().lower() if m_email else ""
        m_off = OFFERING_RE.search(prop)
        offering = (m_off.group(1).strip().upper() if m_off else "")

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
            stats["missing_agent_block"] += 1
            new_prop = prop.replace("</property>", agent_block + "</property>", 1)

        new_properties.append(new_prop)
        stats["assigned_to"][chosen_email] += 1

    list_open_match = LIST_OPEN_RE.search(xml_text)
    if not list_open_match:
        raise SystemExit("Could not find <list> opening tag")
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
    parser = argparse.ArgumentParser(description="Rebuild Elite Property feed with 6-agent mapping.")
    parser.add_argument("source", nargs="?", default="feed.xml")
    parser.add_argument("output", nargs="?", default="new_feed.xml")
    parser.add_argument("--offplan", help="Path to pre-filtered UAE off-plan JSON (from fetch_offplan.py)")
    args = parser.parse_args()

    src = Path(args.source)
    out = Path(args.output)
    xml_text = src.read_text(encoding="utf-8")

    extras: list[str] = []
    offplan_per_agent: Counter = Counter()
    if args.offplan:
        json_path = Path(args.offplan)
        extras, offplan_per_agent = build_offplan_blocks(json_path)
        sys.stderr.write(f"Off-plan blocks merged    : {len(extras)} (from {json_path})\n")

    new_xml, stats = rebuild(xml_text, extra_property_blocks=extras)
    out.write_text(new_xml, encoding="utf-8")

    sys.stderr.write(f"Input  : {src}  ({len(xml_text):,} bytes)\n")
    sys.stderr.write(f"Output : {out}  ({len(new_xml):,} bytes)\n")
    sys.stderr.write(f"Properties processed     : {stats['total']}\n")
    sys.stderr.write(f"Kept with current owner  : {sum(stats['kept_with_owner'].values())}\n")
    sys.stderr.write(f"Reassigned via pool      : {sum(stats['reassigned_by_pool'].values())}\n")
    sys.stderr.write(f"Fallback pool used       : {stats['fallback_used']}\n")
    sys.stderr.write("\nFinal counts per agent:\n")
    for email, n in stats["assigned_to"].most_common():
        sys.stderr.write(f"  {n:5d}  {TARGET_AGENTS[email]['name']:30s}\n")
    if offplan_per_agent:
        sys.stderr.write("\nOff-plan equal round-robin per agent:\n")
        for email, n in offplan_per_agent.most_common():
            sys.stderr.write(f"  {n:5d}  {TARGET_AGENTS[email]['name']:30s}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
