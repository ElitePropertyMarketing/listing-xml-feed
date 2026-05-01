# Elite Property DXB - 6-agent XML feed

This repository hosts the public XML listings feed used by third-party
websites that integrate with Elite Property DXB.

The CRM publishes the master feed at
`https://youtupia.net/eliteproperty/website/full.xml`. This repo
**downloads that feed once a day, rewrites every `<agent>` block so the
output only contains 6 chosen agents, and republishes it via GitHub
Pages**.

The third party should hit a single, stable URL forever (set up in
step 4 below).

## How it works
1. GitHub Actions runs at 02:00 Dubai time daily (`.github/workflows/refresh-feed.yml`).
2. It downloads the source CRM feed in chunks (the source server times
   out on full GETs, so this is required).
3. `rebuild_feed.py` rewrites every property's `<agent>` block.
4. A safety check refuses to publish if the result has fewer than 200
   listings or contains any agent outside the 6 allowed.
5. GitHub Pages serves the result.

## Routing rules
Listings already owned by one of the 6 stay with that owner. Everything
else is reassigned by `offering_type`:

| `offering_type` | Description | Pool (round-robin) |
| --- | --- | --- |
| `RS` | Residential Sale | Evelyn, Alba, Diana, Aaron |
| `RR` | Residential Rent | Jennifer, Evelyn |
| `CS` | Commercial Sale | Jake, Alba, Aaron |
| `CR` | Commercial Rent | Aaron, Jake |

The 6 agents are defined in `rebuild_feed.py`. Edit the `TARGET_AGENTS`
dict to change a phone, photo or license number; the next refresh will
pick it up.

---

## One-time setup (do this once)

You only need to do this once. Total time: ~5 minutes.

GitHub account: **ElitePropertyMarketing**
Target repo:    **listing-xml-feed**
Final URL:      **https://elitepropertymarketing.github.io/listing-xml-feed/full.xml**

### 1. Create the GitHub repository
1. Sign in at <https://github.com/login> as **ElitePropertyMarketing**.
2. Go to <https://github.com/new>.
3. Owner: `ElitePropertyMarketing`. Repository name: `listing-xml-feed`.
4. Visibility: **Public** (required so GitHub Pages can serve it on a
   free account; the listings feed is meant to be public anyway).
5. Leave "Add a README file" **unchecked** - we'll upload one.
6. Click **Create repository**.

### 2. Upload the files
On the empty repo page, click the **uploading an existing file** link
(it appears in the "Quick setup" panel). Drag in **every file in this
folder**, keeping the folder structure:
- `rebuild_feed.py`
- `README.md`
- `.gitignore`
- `.github/workflows/refresh-feed.yml`

Then scroll down and click **Commit changes**.

> The `.github/workflows/refresh-feed.yml` path is important - GitHub
> reads workflows only from that exact location. If the drag-and-drop
> upload doesn't preserve the folder structure, do this instead:
> click **Add file -> Create new file**, type
> `.github/workflows/refresh-feed.yml` as the filename, paste the
> contents from this bundle, then commit. Repeat for the other files.

### 3. Enable GitHub Pages
1. In your new repo, go to **Settings -> Pages**
   (<https://github.com/ElitePropertyMarketing/listing-xml-feed/settings/pages>).
2. Under "Build and deployment -> Source", choose **GitHub Actions**.
3. Save. Nothing else to configure.

### 4. Trigger the first build
1. Go to the **Actions** tab
   (<https://github.com/ElitePropertyMarketing/listing-xml-feed/actions>).
2. If GitHub asks you to enable Actions, click **I understand my workflows, go ahead and enable them**.
3. Click **Refresh feed** on the left.
4. Click **Run workflow -> Run workflow**.
5. Wait ~2 minutes. When the run finishes with a green tick, your feed is live at:

```
https://elitepropertymarketing.github.io/listing-xml-feed/full.xml
```

That is the URL you give the third-party website. It will never change.

### 5. (Optional) Custom domain
If you want the feed on `feed.elitepropertydxb.com` instead:
1. Add a `CNAME` record at your DNS provider:
   `feed.elitepropertydxb.com  ->  elitepropertymarketing.github.io`
2. In **Settings -> Pages -> Custom domain**, enter
   `feed.elitepropertydxb.com` and save.
3. The feed becomes `https://feed.elitepropertydxb.com/full.xml`.

---

## Verifying it's working
- The Actions tab shows a green run every day at ~02:00 Dubai time.
- Open `https://<user>.github.io/<repo>/` in a browser - you'll see a
  small landing page linking to `full.xml`.
- Open the XML directly - you should see ~840 listings, 6 distinct
  agents.

## When you change the agents or routing
1. Edit `rebuild_feed.py` (`TARGET_AGENTS` and `ROUTING` at the top).
2. Commit on GitHub (web editor is fine).
3. The next scheduled run picks up the change. Or, hit "Run workflow"
   in the Actions tab to apply immediately.

## When the source feed is broken
If the source CRM returns a tiny / corrupt feed for a day, the workflow
**will not** overwrite the published feed. The previous good copy stays
live until the next successful run. Watch the Actions tab for a red run
- click in to see what failed.

## Manual local rebuild
You don't need this for normal operation, but if you want to test
locally:

```bash
curl -sS -o feed.xml "https://youtupia.net/eliteproperty/website/full.xml"
python3 rebuild_feed.py feed.xml new_feed.xml
```

(Pure Python 3, no extra packages required.)
