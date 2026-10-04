# Biosimilar Wire

A small news site. Every 3 hours a GitHub job reads the RSS feeds in `feeds.json`,
tags biosimilar news, and saves it to `data/news.json`. `index.html` shows it.
Hosting is free on GitHub.

## Setup (about 30 minutes, once)

1. Create a free account on github.com.
2. Create a new repository, set to **Public**, e.g. `biosimilar-wire`.
3. Upload everything from this folder ("Add file" > "Upload files").
   The folder `.github` is hidden on Mac/Windows. Make sure it gets uploaded too,
   or create the file `.github/workflows/update.yml` by hand in GitHub and paste the content.
4. Settings > Pages > Source: "Deploy from a branch", branch `main`, folder `/ (root)`. Save.
5. Settings > Actions > General > Workflow permissions: "Read and write permissions". Save.
6. Actions tab > "Update news" > "Run workflow". After 1 to 2 minutes the site has data.
7. The site is at `https://YOURNAME.github.io/biosimilar-wire/`.

## Summaries and reports (optional, costs a little)

Without an API key the site shows the feeds' own teaser text and tags news by keyword.
No reports are written.

With a key, each new item gets a one-sentence summary and a relevance score, and a
report is written every 14 days.

1. Get an API key at console.anthropic.com (pay as you go).
2. In the repository: Settings > Secrets and variables > Actions > New repository secret.
   Name: `ANTHROPIC_API_KEY`, value: the key.

Report on demand: Actions > "Update news" > "Run workflow" > tick "Write a new report now".
The Reports tab on the site links there directly.

## Changing things

Everything is in `feeds.json`:

- `feeds`: add or remove sources. `always_biosimilar: true` marks every item from that feed as biosimilar news.
- `keywords`: words that mark an item as biosimilar news (when no API key is set).
- `watchlist`: company names shown as tags on matching items.
- `report_every_days`, `report_window_days`, `keep_days`.

How often it updates: the `cron` line in `.github/workflows/update.yml`.

## Sharing

Anyone with the link can read the site. It is public. A password-protected site
needs a paid GitHub plan or a different host.

## Limits

- LinkedIn is not included. It has no feeds and does not allow crawling.
- Paywalled sites only give headline and teaser.
- Sites without their own feed (GaBI, Center for Biosimilars) come in through Google News search feeds.
- If a feed fails, the site shows it in red at the bottom. Fix the URL in `feeds.json`.
