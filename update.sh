#!/bin/bash
# Refresh Run Lab and publish it: sync Strava, import Spotify (if an export is there), rebuild the snapshot in docs/, push.
# Run it by hand:   ./update.sh        (or let install_daily_update.sh run it for you every morning)
cd "$(dirname "$0")" || exit 1
export PATH="/opt/homebrew/bin:/usr/local/bin:$PATH"
mkdir -p data
{
  echo "=== $(date) ==="
  .venv/bin/python -m ingest.strava_api sync || echo "Strava sync did not finish (not signed in yet, offline, or the rate limit). Continuing with what is already saved."
  if find data/spotify-export -name '*.json' 2>/dev/null | grep -q .; then
    .venv/bin/python -m ingest.spotify_import || echo "Spotify import had a problem; continuing."
  fi
  if ! .venv/bin/python -m tools.export_static; then echo "Could not build the snapshot."; exit 1; fi
  git add docs
  if git diff --cached --quiet; then
    echo "Nothing new to publish."
  elif git commit -q -m "Update snapshot $(date +%F)" && git push -q; then
    echo "Published. The site updates within a minute or two."
  else
    echo "Built the snapshot but could not push it. Check your GitHub login (try: git push) and run ./update.sh again."
  fi
} 2>&1 | tee -a data/update.log
