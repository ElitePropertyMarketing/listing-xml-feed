# Elite Property DXB - listings XML feed

Public, daily-refreshed XML feed used by third-party integrations.

- **Live URL**: <https://elitepropertymarketing.github.io/listing-xml-feed/full.xml>
- **Schedule**: every day at 02:00 Dubai time (cron `0 22 * * *` UTC)
- **Sources**: Bitrix24 CRM (~834 listings) + Reelly UAE off-plan, excluding Completed and incomplete records (~853 listings) = **~1,687 listings total**
- **Agents**: 6 (Evelyn, Alba, Diana, Aaron, Jake, Jennifer). Off-plan listings are split equally; CRM listings stay with their owner if it's one of the 6, otherwise they're routed by `offering_type`.
- **Off-plan quality gate**: a Reelly record is only included if it has a non-zero price and size, a description of at least 50 characters, at least one photo URL, and populated developer / property_type / offering_type fields. UK projects and any records flagged Completed are dropped before this check.

## Files

| File | Purpose |
| --- | --- |
| `rebuild_feed.py` | Rewrites the source CRM feed and merges in the UAE off-plan JSON. |
| `fetch_offplan.py` | Pulls every page of the Reelly international API (149+ pages, parallel) and filters down to UAE-active records. |
| `.github/workflows/refresh-feed.yml` | The GitHub Actions workflow that ties them together and publishes to GitHub Pages. |
| `.gitignore` | |

## Manual run (local)

```bash
python3 fetch_offplan.py /tmp/offplan_uae.json
curl -sS -o /tmp/feed.xml "https://youtupia.net/eliteproperty/website/full.xml"
python3 rebuild_feed.py /tmp/feed.xml /tmp/new_feed.xml --offplan /tmp/offplan_uae.json
```

Pure Python 3.11+, no extra packages.
