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
.venv/bin/python -m ingest.spotify_live auth|poll|recent   # live Spotify capture (see below); `recent` shows latest saved plays
```

## Strava sync (direct API, preferred)
`ingest/strava_api.py` talks to Strava's API itself; no Claude needed. Setup: create a free app at https://www.strava.com/settings/api (Authorization Callback Domain: `localhost`), copy `.env.example` to `.env` and fill in Client ID/Secret, then run `auth` once. Token is saved to `data/strava_token.json` (chmod 600, gitignored). Limits: ~100 requests/15 min, 1000/day; `sync` stops cleanly on 429 and is resumable (skips runs already in the DB). Never print or commit `.env` or the token.
Restart the server after editing Python modules (no auto-reload of imports).

## Layout
- `db.py`: SQLite schema + `connect()`. Real DB `data/runlab.db`; demo DB `data/demo.db` (`RUNLAB_DB=demo` or `--demo`).
- `ingest/`: `strava_api.py` (OAuth + resumable sync), `strava_import.py` (dump loader), `spotify_import.py` (export -> `plays`).
- `analysis/` (pure, unit-tested): `zones.py` (VDOT, paces, HR zones), `fitness.py` (current numbers + overrides + plan adherence), `plans.py` (plan generator), `ics.py` (Google Calendar export), `insights.py` (findings + analytics series), `places.py` (home base, new ground), `music_match.py` (songs on runs + music findings), `calculator.py` (model for the race-time calculator: his pace-vs-distance fade, stopping habit, HR at pace, fitness race curve), `shoes.py` (shoe miles vs. replace-at limit).
- `server.py`: Flask on `127.0.0.1` only. JSON API + serves `web/`.
- `web/`: no build step. `js/main.js` router; `js/pages/` home, runs, run, planner, calculator, analytics (+ `-story`, `-explore`, `-places`); `css/` base, pages, analytics.
- `tools/make_demo_data.py`: generates ~80 fake runs (with planted patterns the tests look for).
- `PRODUCT.md` / `DESIGN.md`: design context (read before any UI work).
- `data/`: gitignored: databases, `strava-dumps/`, `spotify-export/`, `strava_token.json`.

## Shoes
Strava sync refreshes each shoe's lifetime distance (`settings.gear_info`, 1 request per shoe per sync); `analysis/shoes.py` turns that + tagged runs + per-shoe `start_mi`/`limit_mi` (default 400) into the Home "Shoe mileage" block. Runs with no shoe set in Strava aren't counted (only runs since 2026-09-08 are tagged). Home order: recent runs, up next, full plan grid (`web/js/lib/plangrid.js`, shared with the Planner).

## Calculator defaults
The calculator page opens on Jack's own numbers from `settings.calc_defaults` ({pace_s, stop_every_mi, stop_min}; currently 9:47, a stop every 3.1 mi, 1.25 min each, from his 2026-10-04 10-miler). No UI to edit them yet: set with `fitness.set_setting(conn, "calc_defaults", {...})`. Missing keys fall back to his usual-effort pace, 3 mi, 1 min.

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
- A watch pause shows up as a **time gap** in `t_s` (and a few `moving=false` samples), not a run of stopped samples: find stops with `t_s` jumps > ~12 s (elapsed - moving = total paused). Stream resolution is ~4 s.
- Stream arrays are index-aligned; `time` is seconds from start; `moving=false` = watch paused (exclude from averages).
- Treadmill runs have no `location`; map must hide gracefully.
- Strava `best_efforts` use clock time (stops included) so they read low; gear ids need a `g` prefix for `/gear/{id}` (the connector strips it; `import_dump` normalizes). Never let cosmetic lookups (shoe names) crash a sync.
- Python 3.14: use timezone-aware datetimes (`utcnow` is deprecated). `sqlite` timestamps: our ISO strings use `T`...`Z`, SQLite's `datetime()` uses a space, so don't compare them in SQL.

## Rules
- Bind servers to `127.0.0.1`, never `0.0.0.0`.
- Never commit anything under `data/`. This data has GPS + listening history; any public version excludes maps and exact times.
- Before ANY UI work, invoke `frontend-design`, `ui-ux-pro-max`, and `impeccable` (Jack's global rule). Verify UI in the browser preview before calling it done.
- Pace/zone/matching logic gets unit tests with hand-checked numbers. Prove it works before saying done.
- Tests: `.venv/bin/python -m pytest -q` (~135, ~1s). Some insights/music tests assert patterns planted by `tools/make_demo_data.py` and skip if `data/demo.db` is missing: regenerate with `python -m tools.make_demo_data` after changing the generator.
- No `innerHTML` in `web/` (a security hook blocks it, and run names come from Strava): build DOM with `h()`/`s()` from `web/js/lib/dom.js`.
- After any `web/` or API change, run `python -m tools.export_static` so `docs/` matches before committing (`update.sh` does this daily). Restart the preview server after Python edits.
- Preview configs (all port 5057, stop one before starting another): "Run Lab", "Run Lab (demo data)", "Run Lab (static snapshot)" in `Claude-Brain/.claude/launch.json`. Use the demo data to build/verify UI that needs many runs, then smoke-test the real DB (it surfaces things demo data hides).
- Statistics: findings must state sample size + confidence and compare like with like (control effort/distance/drift); never oversell small-n patterns.
- Jack is a beginner coder: brief plain-English explanation after bug fixes; explain before big or hard-to-reverse changes.

## Publishing the read-only snapshot (GitHub Pages)
`python -m tools.export_static` runs the app's own API over a temp copy of the DB and writes a plain-file site to `docs/` (data in `docs/data/*.json`). The front end detects `<meta name="runlab-static">` (`web/js/lib/api.js`): GETs read files, writes are refused, Sync/plan editing are hidden, a "Snapshot" chip shows the export date, and "today"/countdowns use the browser's clock. GPS is trimmed 400 m at both ends of every route by default (`--no-trim` to disable); the real DB is never modified.
- `./update.sh`: sync Strava, import Spotify if an export is present, export, commit `docs/`, push. Logs to `data/update.log`. Claude does not run the push.
- `./install_daily_update.sh` (`--remove` to undo): launchd job running update.sh every hour (+ at load); it only commits when `docs/` changed. Only Jack installs it. GitHub Pages caches data files 10 min (hard-refresh to see a new run).
- Pages setup (Jack, once): repo must be public (free) or Pro; Settings > Pages > Deploy from branch `master`, folder `/docs`. Site: https://hicksjack14.github.io/run-lab/
- The snapshot is public: it contains run stats, trimmed routes, and listening-derived findings. Never commit `data/`.
- Preview locally: `python -m tools.export_static --demo --out .static-preview` then launch config "Run Lab (static snapshot)".

## Theme
Deep navy + light blue (see `DESIGN.md`). Light blue = pace, coral = heart rate. Neutrals are navy-tinted oklch at hue ~258. Changing the palette means `web/css/base.css` tokens, the JS color ramps (`PACE_RAMP`/`TIME_RAMP`/`EFF_RAMP`), `web/js/lib/backdrop.js`, and `tools/make_icon.py` (then `python3 tools/make_icon.py`).

## Live Spotify capture
`ingest/spotify_live.py` polls Spotify's recently-played (last 50) with Authorization Code + PKCE (no secret). Setup (Jack): Spotify developer app (the owner needs **Premium**, a 2026 dev-mode rule), redirect URI exactly `http://127.0.0.1:5059/callback` (localhost is rejected; port 5060 is blocked by browsers), `SPOTIFY_CLIENT_ID` in `.env`, then `auth`. `./install_spotify_poll.sh` polls every 30 min (log `data/spotify-poll.log`); `update.sh` also polls. Plays get `source='live'`; importing the official export deletes live rows inside the export's period. `played_at` is ambiguous (start vs end): treated as end; flip with `spotify_live set-played-at start`. Start time = end minus song length, clipped to the previous song's end. Claude never runs `auth`.

## Chained plans (follow-up races)
`POST /api/plan` with `follow_up: true` adds a plan after the current one instead of replacing it (any number of active `plans` rows form a chain, ordered by race date). `merge_chain()` in `server.py` merges them: week numbers keep counting, workouts/warnings are combined, `plan.chain` lists the races, and the "current" plan is the next race not yet run (so Home/Planner switch to the follow-up after the first race). Extra body fields: `role` (`race` | `companion`), `companion_pace_s`, `name`, `weekly_mi` (starting volume, 3-80; default is the 4-week average, which reads low right after a build), `start_date` (default: day after the previous race). A follow-up always starts with an easy recovery week. `role: companion` = an easy run beside someone slower: pace is theirs, no goal time, no intervals, no ambition/short-build warnings. `DELETE /api/plan?last=1` removes only the latest follow-up; plain DELETE clears everything; a normal POST (no `follow_up`) still replaces the whole chain. Calendar export covers the whole chain with UIDs from the first plan's id, so re-importing updates existing events. Tests: `tests/test_followup.py`. Gotcha: in `generate_plan` the day loop reuses the name `role`, so the real option is saved as `plan_role` first.

## Finished albums -> Crates
`ingest/spotify_live.py poll` now saves each play's album details (album id, type, total tracks, track number, disc, track length: new `plays` columns, added by `db._migrate`; only live plays have them) and then runs `ingest/crates_sync.py`. `analysis/albums.py` calls an album **finished** when every track was played >= 80% of its length within a 48 h window (any order; Spotify type `album`, 4+ tracks; singles ignored). Finishes go in `album_finishes` (one row per album per local day, date from `settings.timezone`, default America/New_York) and are POSTed to Crates' `/api/runlab/listened` with `CRATES_URL` + `CRATES_TOKEN` from `.env` (token must equal `RUNLAB_TOKEN` in Crates/Vercel; https required except localhost). Crates logs it unrated and clears it from the Queue; a repeat listen bumps plays. Network/Crates outages retry forever, refusals stop after 5. CLI: `python -m ingest.crates_sync [run | status | check]`. Plays from Spotify's old export carry no album details, so only albums listened to after this shipped can be detected. Tests: `tests/test_album_finish.py`.

## Races tab (`#/races`)
Three sections. **Coming up**: one card per race in the plan chain (`/api/plan` `chain`, with each workout's `plan_id`, `week_from/week_to`, `warnings`). **Race log**: `race_log` table (manual entries via `POST /api/races`, `DELETE /api/races/<id>`) plus finished plan races added automatically (read-only, time = watch moving time, hidden if a manual race is on the same date); a manual race auto-links the Strava run on that date (within 15% of the distance). Personal bests come from logged times. **Goal races**: `analysis/goal_races.py` holds NYC Half, NYC Marathon and Boston as DATA (standards for **Men 18-34**, ways in, sources, `VERIFIED` date); `evaluate()` computes status (completed = a log entry tagged with that goal; "time standard met" = a logged time in the window that beats it; counters for NYRR 4-of-6 / 9+1 from entries flagged NYRR), plus the gap between his current fitness prediction and each standard. **The requirements change every year: re-check the sources and bump `VERIFIED`** (Boston was read from baa.org; the NYRR facts came via search results because nyrr.org blocks automated reads). Page files: `web/js/pages/races.js` (+ `races-log.js`, `races-goals.js`). Tests: `tests/test_races.py`.
