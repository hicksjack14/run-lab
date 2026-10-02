# Run Lab — CLAUDE.md

Jack's personal running app: Strava/Garmin runs + Spotify songs, shown on charts and a live map replay. Local-first.

**Brain files (read before working):** `/Users/jackhicks/Desktop/Claude-Brain/context/run-lab.md` (status, gotchas) and `/Users/jackhicks/Desktop/Claude-Brain/Run Lab/Run Lab - Design Spec.md` (full design). Specs, plans, and notes go in `/Users/jackhicks/Desktop/Claude-Brain/Run Lab/`, never in this repo. Update `context/run-lab.md` when status changes.

## Run it
```bash
cd ~/run-lab
.venv/bin/python server.py            # http://127.0.0.1:5057
.venv/bin/python -m pytest -q         # tests
.venv/bin/python -m ingest.strava_import   # load data/strava-dumps/*.json into SQLite
```
Restart the server after editing Python modules (no auto-reload of imports).

## Layout
- `db.py` — SQLite schema + `connect()`. DB file: `data/runlab.db`.
- `ingest/strava_import.py` — idempotent loader for dump JSON (format below).
- `ingest/spotify_import.py` — (todo) Spotify Extended Streaming History -> `plays`.
- `analysis/` — `music_match.py`, `zones.py`, `plans.py` (todo; pure functions, unit-tested).
- `server.py` — Flask on `127.0.0.1` only. JSON API + serves `web/`.
- `web/` — static dashboard (Leaflet map replay, charts). No build step.
- `data/` — gitignored: `runlab.db`, `strava-dumps/`, `spotify-export/`.

## How Strava data gets in
Strava comes through the **Strava MCP connector** (tools `list_activities`, `get_activity_streams`, `get_activity_performance`). The app cannot call it; Claude does. Flow: Claude pulls an activity + streams + performance, writes `data/strava-dumps/<activity_id>.json`, then runs the importer.

Dump format (one file per run):
```json
{"activity": {<one item from list_activities>},
 "streams": {"time":[], "heart_rate":[], "velocity_smooth":[], "cadence":[], "distance":[], "moving":[], "location":[[lat,lng]], "altitude":[]},
 "performance": {<get_activity_performance result>}}
```
Pull streams with `resolution: 1000` (medium): full resolution costs ~40k tokens per run in Claude's context. For big backfills, direct Strava API sync is cheaper (see spec open questions).

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
