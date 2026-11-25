# Richmond League Hub

Private league history site for our fantasy football league. Fantasy data provided by Yahoo Fantasy.

Live site: https://gen-gallon.github.io/richmond-league-hub/

## How it works

```
GitHub Actions (every 4h) ──> ingest/ (Python) ──> Yahoo Fantasy API (read-only, OAuth 2.0)
                                     │
                                     └──> site/data/*.json ──> GitHub Pages (static site in site/)
```

- **ingest/** pulls league metadata, settings, standings, weekly scoreboards, draft results and transactions.
  It walks back through past seasons using Yahoo's `renew` links, so all 20 seasons come from one league ID.
- Finished seasons are pulled once and cached in `site/data/seasons/`. Only the current season is refreshed.
- **site/** is plain HTML/CSS/JS with no build step: This Season, All-Time, Head-to-Head, Records, and Past Seasons.
- Privacy: only team names, manager nicknames and stats are stored. Manager emails and Yahoo GUIDs are never
  written; owners are identified by a short hash. The page has `noindex` so search engines skip it.

Until Yahoo credentials are added, the site shows clearly labelled **demo data** (`python -m ingest.demo`).

## Setup (one time, after Yahoo approves API access)

1. **Turn on Pages:** repo Settings → Pages → Source: **GitHub Actions**.
2. **Get a refresh token** on your own computer:
   ```bash
   git clone https://github.com/gen-gallon/richmond-league-hub && cd richmond-league-hub
   pip install requests
   python scripts/get_token.py
   ```
   Enter the Client ID and Secret Yahoo gave you, approve access in the browser, and paste the code back.
   If Yahoo's app settings require a real redirect URI instead of `oob`, enter that same URI when the script asks.
3. **Add repo secrets** (Settings → Secrets and variables → Actions → *Secrets*):
   `YAHOO_CLIENT_ID`, `YAHOO_CLIENT_SECRET`, `YAHOO_REFRESH_TOKEN` (and `YAHOO_REDIRECT_URI` if not `oob`).
4. **Optional variable** (same page → *Variables*): `YAHOO_LEAGUE_ID` (defaults to `8049`).
5. **Run it:** Actions → *Refresh league data and deploy* → Run workflow. The first run backfills every season
   (a few hundred API calls, several minutes). Later runs take well under a minute.

## Fixing owner names

Yahoo nicknames can be odd, and someone who changed Yahoo accounts shows up as two owners. After the first
real run, open `config/owners_seen.json` to see each owner id and the names it has used, then edit
`config/owners.json`:

```json
{
  "names": { "a1b2c3d4e5": "Big Mike" },
  "merge": { "oldid12345": "a1b2c3d4e5" }
}
```

Commit the change; the next run applies it.

## Local development

```bash
pip install -r requirements.txt pytest
python -m pytest -q                    # parser + aggregation tests against sample Yahoo XML
python -m ingest.demo                  # fake data
python -m http.server -d site 8000     # http://localhost:8000
```

With credentials in your environment, `python -m ingest.build` pulls real data (`--full` re-pulls everything).

## Known unknowns (verify on first real run)

- **Final rank = playoff finish.** Champions come from Yahoo's final standings rank once a season is finished.
- **How far back history goes.** If Yahoo stops returning a very old season, the walk stops there and the
  site shows what it has; the log says where it stopped.
- **Scheduled runs pause after 60 days without repo activity** (a GitHub rule for public repos). In the
  offseason, re-enable from the Actions tab or push any commit.
