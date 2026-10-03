#!/bin/bash
# Save your Spotify plays every 30 minutes in the background (Spotify only remembers your last 50 songs).
#   ./install_spotify_poll.sh            turn it on
#   ./install_spotify_poll.sh --remove   turn it off
# Needs: SPOTIFY_CLIENT_ID in .env and a finished `python -m ingest.spotify_live auth`. Output: data/spotify-poll.log
set -e
cd "$(dirname "$0")"
REPO="$(pwd)"
PLIST="$HOME/Library/LaunchAgents/com.runlab.spotify.plist"
if [ "$1" = "--remove" ]; then
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Spotify polling turned off."
  exit 0
fi
[ -f data/spotify_token.json ] || { echo "Sign in first: .venv/bin/python -m ingest.spotify_live auth"; exit 1; }
mkdir -p "$HOME/Library/LaunchAgents" data
cat > "$PLIST" <<PLISTEND
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.runlab.spotify</string>
  <key>ProgramArguments</key><array><string>$REPO/.venv/bin/python</string><string>-m</string><string>ingest.spotify_live</string><string>poll</string></array>
  <key>WorkingDirectory</key><string>$REPO</string>
  <key>StartInterval</key><integer>1800</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardErrorPath</key><string>$REPO/data/spotify-poll.log</string>
  <key>StandardOutPath</key><string>$REPO/data/spotify-poll.log</string>
</dict></plist>
PLISTEND
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Spotify polling is on (every 30 minutes). Check data/spotify-poll.log. Turn it off with: ./install_spotify_poll.sh --remove"
