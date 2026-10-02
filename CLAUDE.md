# Run Lab — CLAUDE.md

Jack's personal running app: Strava/Garmin runs + Spotify songs, shown on charts and a live map replay. Local-first.

**Brain files (read before working):** `/Users/jackhicks/Desktop/Claude-Brain/context/run-lab.md` (status, gotchas) and `/Users/jackhicks/Desktop/Claude-Brain/Run Lab/Run Lab - Design Spec.md` (full design). Specs, plans, and notes go in `/Users/jackhicks/Desktop/Claude-Brain/Run Lab/`, never in this repo. Update `context/run-lab.md` when status changes.

## Run it
```bash
cd ~/Desktop/Claude-Brain/claude-code/run-lab
.venv/bin/python server.py            # http://127.0.0.1:5057 (real data)
.venv/bin/python server.py --demo     # fake demo data (make it first: python -m tools.make_demo_data)
.venv/bin/python -m pytest -q         # tests
.venv/bin/python -m ingest.strava_api auth    # one-time Strava login (needs .env, see below)
.venv/bin/python -m ingest.strava_api sync    # pull all new runs; re-run any time (--limit N to test)
.venv/bin/python -m ingest.strava_import      # reload data/strava-dumps/*.json into SQLite
.venv/bin/python -m ingest.spotify_import     # import the Spotify export dropped in data/spotify-export/
```

## Strava sync (direct API, preferred)
`ingest/strava_api.py` talks to Strava's API itself; no Claude needed. Setup: create a free app at https://www.strava.com/settings/api (Authorization Callback Domain: `localhost`), copy `.env.example` to `.env` and fill in Client ID/Secret, then run `auth` once. Token is saved to `data/strava_token.json` (chmod 600, gitignored). Limits: ~100 requests/15 min, 1000/day; `sync` stops cleanly on 429 and is resumable (skips runs already in the DB). Never print or commit `.env` or the token.
Restart the server after editing Python modules (no auto-reload of imports).

## Layout
- `db.py`: SQLite schema + `connect()`. Real DB `data/runlab.db`; demo DB `data/demo.db` (`RUNLAB_DB=demo` or `--demo`).
- `ingest/`: `strava_api.py` (OAuth + resumable sync), `strava_import.py` (dump loader), `spotify_import.py` (export -> `plays`).
- `analysis/` (pure, unit-tested): `zones.py` (VDOT, paces, HR zones), `fitness.py` (current numbers + overrides + plan adherence), `plans.py` (plan generator), `ics.py` (Google Calendar export), `insights.py` (findings + analytics series), `places.py` (home base, new ground), `music_match.py` (songs on runs + music findings).
- `server.py`: Flask on `127.0.0.1` only. JSON API + serves `web/`.
- `web/`: no build step. `js/main.js` router; `js/pages/` home, runs, run, planner, analytics (+ `-story`, `-explore`, `-places`); `css/` base, pages, analytics.
- `tools/make_demo_data.py`: generates ~80 fake runs (with planted patterns the tests look for).
- `PRODUCT.md` / `DESIGN.md`: design context (read before any UI work).
- `data/`: gitignored: databases, `strava-dumps/`, `spotify-export/`, `strava_token.json`.

## Fitness numbers
Paces come from a fitness score (VDOT). Sources, in order: manual override, a race result Jack enters, then an estimate from his data (best efforts, whole runs in moving time, everyday pace). The data estimate reads low for someone who mostly runs easy, so the UI labels it an estimate and offers "Add a race result".

## Fallback: Strava via the MCP connector
If the API isn't set up, Strava can also come through the **Strava MCP connector** (tools `list_activities`, `get_activity_streams`, `get_activity_performance`). The app cannot call it; Claude does. Flow: Claude pulls an activity + streams + performance, writes `data/strava-dumps/<activity_id>.json`, then runs the importer.

Dump format (one file per run):
```json
{"activity": {<one item from list_activities>},
 "streams": {"time":[], "heart_rate":[], "velocity_smooth":[], "cadence":[], "distance":[], "moving":[], "location":[[lat,lng]], "altitude":[]},
 "performance": {<get_activity_performance result>}}
```
Pull streams with `resolution: 1000` (medium): full resolution costs ~40k tokens per run in Claude's context. For big backfills, direct Strava API sync is cheaper (see spec open questions).

After writing a dump, ALWAYS check every stream array has the same length (a mis-copied `moving` array once shifted the pause markers). Map tiles are OSM with a CSS invert filter (CARTO dark needs an API key).

## Data gotchas
- `start_local` has no timezone. Default `America/New_York`; per-run override column `tz`. Match Spotify on UTC only.
- Strava cadence is per foot (~85). Store spm = value x 2.
- Strava zones/5K predictions are unreliable estimates; compute zones from his own data.
- Stream arrays are index-aligned; `time` is seconds from start; `moving=false` = watch paused (exclude from averages).
- Treadmill runs have no `location`; map must hide gracefully.

## Rules
- Bind servers to `127.0.0.1`, never `0.0.0.0`.
- Never commit anything under `data/`. This data has GPS + listening history; any public version excludes maps and exact times.
- Before ANY UI work, invoke `frontend-design`, `ui-ux-pro-max`, and `impeccable` (Jack's global rule). Verify UI in the browser preview before calling it done.
- Pace/zone/matching logic gets unit tests with hand-checked numbers. Prove it works before saying done.
- Jack is a beginner coder: brief plain-English explanation after bug fixes; explain before big or hard-to-reverse changes.

## Publishing the read-only snapshot (GitHub Pages)
`python -m tools.export_static` runs the app's own API over a temp copy of the DB and writes a plain-file site to `docs/` (data in `docs/data/*.json`). The front end detects `<meta name="runlab-static">` (`web/js/lib/api.js`): GETs read files, writes are refused, Sync/plan editing are hidden, a "Snapshot" chip shows the export date, and "today"/countdowns use the browser's clock. GPS is trimmed 400 m at both ends of every route by default (`--no-trim` to disable); the real DB is never modified.
- `./update.sh`: sync Strava, import Spotify if an export is present, export, commit `docs/`, push. Logs to `data/update.log`. Claude does not run the push.
- `./install_daily_update.sh` (`--remove` to undo): launchd job running update.sh at 7:30 AM. Only Jack installs it.
- Pages setup (Jack, once): repo must be public (free) or Pro; Settings > Pages > Deploy from branch `master`, folder `/docs`. Site: https://hicksjack14.github.io/run-lab/
- The snapshot is public: it contains run stats, trimmed routes, and listening-derived findings. Never commit `data/`.
- Preview locally: `python -m tools.export_static --demo --out .static-preview` then launch config "Run Lab (static snapshot)".
