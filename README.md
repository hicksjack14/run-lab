# Run Lab

A personal, local-first running app. Pulls runs from Strava (Garmin syncs into it), shows pace and heart rate, and replays each run on a live map with the songs Jack was listening to.

Design and notes live in the Claude-Brain vault (`Run Lab/` folder). See `CLAUDE.md` for how to run and work on it.

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python server.py     # http://127.0.0.1:5057
```

Personal data (GPS, heart rate, listening history) stays in `data/` and is gitignored.

## Always-on read-only copy
`./update.sh` refreshes your data and publishes a snapshot to GitHub Pages (`docs/`). `./install_daily_update.sh` does it every morning. See `CLAUDE.md` for setup.
