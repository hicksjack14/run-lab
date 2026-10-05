#!/bin/bash
# Make your Mac run ./update.sh by itself so the published site stays fresh without you doing anything.
#   ./install_daily_update.sh            turn it on (every hour; a new run is on the site within about an hour of the Mac being awake)
#   ./install_daily_update.sh --remove   turn it off
# Output goes to data/update.log. It needs: Strava set up (.env + auth), and `git push` working without a password prompt.
set -e
cd "$(dirname "$0")"
REPO="$(pwd)"
PLIST="$HOME/Library/LaunchAgents/com.runlab.update.plist"
if [ "$1" = "--remove" ]; then
  launchctl unload "$PLIST" 2>/dev/null || true
  rm -f "$PLIST"
  echo "Auto-update turned off."
  exit 0
fi
mkdir -p "$HOME/Library/LaunchAgents"
cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
  <key>Label</key><string>com.runlab.update</string>
  <key>ProgramArguments</key><array><string>/bin/bash</string><string>$REPO/update.sh</string></array>
  <key>StartInterval</key><integer>3600</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardErrorPath</key><string>$REPO/data/update.log</string>
  <key>StandardOutPath</key><string>$REPO/data/update.log</string>
</dict></plist>
EOF
launchctl unload "$PLIST" 2>/dev/null || true
launchctl load "$PLIST"
echo "Auto-update is on (every hour). Check data/update.log to see how it went. Turn it off with: ./install_daily_update.sh --remove"
