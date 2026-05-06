# Elite Property DXB - listings XML feed

Public, daily-refreshed XML feed used by third-party integrations.

- **Live URL**: <https://elitepropertymarketing.github.io/listing-xml-feed/full.xml>
- **Schedule**: every day at 02:00 Dubai time (cron `0 22 * * *` UTC)
- **Source**: Bitrix24 CRM only (~834 listings). Reelly UAE off-plan integration has been removed.
- **Agents**: 6 (Evelyn, Alba, Diana, Aaron, Jake, Jennifer). CRM listings stay with their owner if it's one of the 6, otherwise they're routed by `offering_type`.

## Files

| File | Purpose |
| --- | --- |
| `rebuild_feed.py` | Rewrites the source CRM feed so every listing is mapped to one of the 6 target agents. |
| `.github/workflows/refresh-feed.yml` | The GitHub Actions workflow that downloads, rewrites and publishes the feed to GitHub Pages. |
| `.gitignore` | |

## Manual run (local)

```bash
curl -sS -o /tmp/feed.xml "https://youtupia.net/eliteproperty/website/full.xml"
python3 rebuild_feed.py /tmp/feed.xml /tmp/new_feed.xml
```

Pure Python 3.11+, no extra packages.
