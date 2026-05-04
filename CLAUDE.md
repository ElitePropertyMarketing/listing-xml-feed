# Instructions for Claude Code

This folder is a ready-to-push update for the GitHub repo
`ElitePropertyMarketing/listing-xml-feed`.

## What to do

1. Make sure git is configured locally:
   ```bash
   git config --global user.name "Mehmood Asghar"
   git config --global user.email "marketing@elitepropertydxb.com"
   ```

2. From the directory containing this CLAUDE.md, push everything to the `main` branch of `https://github.com/ElitePropertyMarketing/listing-xml-feed`:
   ```bash
   git init
   git checkout -b main
   git remote add origin https://github.com/ElitePropertyMarketing/listing-xml-feed.git
   git fetch origin main
   git reset --soft origin/main
   git add -A
   git commit -m "Re-add Reelly UAE off-plan integration (filtered: UAE only, exclude Completed)"
   git push origin main
   ```

   You'll be prompted for credentials. Use a **GitHub Personal Access Token** (Settings → Developer settings → Personal access tokens → Fine-grained, with "Contents: write" + "Workflows: write" scopes on the `listing-xml-feed` repo) — not your account password.

3. Trigger the workflow so the live feed updates immediately instead of waiting for the 02:00 Dubai cron:
   ```bash
   gh workflow run refresh-feed.yml --repo ElitePropertyMarketing/listing-xml-feed
   ```
   If `gh` isn't installed, the user can click "Run workflow" at
   <https://github.com/ElitePropertyMarketing/listing-xml-feed/actions/workflows/refresh-feed.yml>.

4. Wait ~3 minutes, then verify:
   ```bash
   curl -sI https://elitepropertymarketing.github.io/listing-xml-feed/full.xml
   ```

## Expected outcome

After the workflow's green tick, the feed should contain ~2,316 listings: 840 from CRM + 1,476 UAE off-plan. Six agents only.
