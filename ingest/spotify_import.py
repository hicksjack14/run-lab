"""Import Spotify listening history into the plays table.

Request it at spotify.com/account/privacy ("Extended streaming history"; arrives in a few days), unzip it, and drop the
folder into data/spotify-export/. Then:  python -m ingest.spotify_import

Handles both formats Spotify uses:
  - Extended:  Streaming_History_Audio_*.json   ("ts" = when the play ENDED, UTC; "ms_played")
  - Account data: StreamingHistory*.json        ("endTime" = UTC, "msPlayed")
Plays under 30 s are treated as skips and dropped; podcasts are ignored. The IP address and other
account fields in the export are never stored. Safe to re-run.
"""
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import db

EXPORT_DIR = Path(__file__).resolve().parent.parent / "data" / "spotify-export"
MIN_PLAY_MS = 30_000
FMT = "%Y-%m-%dT%H:%M:%SZ"


def _is_history_file(path):
    name = path.name
    return name.startswith("Streaming_History_Audio") or re.fullmatch(r"StreamingHistory\d*\.json", name) is not None


def _normalise(entry):
    """-> (end_datetime_utc, ms_played, track, artist, album, uri) or None if it is not a song play."""
    if "ts" in entry:                                   # extended history
        track = entry.get("master_metadata_track_name")
        if not track:
            return None
        end = datetime.strptime(entry["ts"], FMT)
        artist = entry.get("master_metadata_album_artist_name")
        album = entry.get("master_metadata_album_album_name")
        uri = entry.get("spotify_track_uri") or f"legacy:{artist}|{track}"
        return end, int(entry.get("ms_played") or 0), track, artist, album, uri
    if "endTime" in entry:                              # account-data history
        track, artist = entry.get("trackName"), entry.get("artistName")
        if not track:
            return None
        end = datetime.strptime(entry["endTime"], "%Y-%m-%d %H:%M")
        return end, int(entry.get("msPlayed") or 0), track, artist, None, f"legacy:{artist}|{track}"
    return None


def import_dir(conn, directory=EXPORT_DIR):
    directory = Path(directory)
    if not directory.exists():
        raise FileNotFoundError(f"No Spotify export folder at {directory}. Drop the unzipped export there first.")
    files = sorted(p for p in directory.rglob("*.json") if _is_history_file(p))
    added = short = other = 0
    first_end = last_end = None            # the period the export covers
    for path in files:
        for entry in json.loads(path.read_text(encoding="utf-8")):
            norm = _normalise(entry)
            if norm is None:
                other += 1
                continue
            end, ms, track, artist, album, uri = norm
            if ms < MIN_PLAY_MS:
                short += 1
                continue
            start = end - timedelta(milliseconds=ms)
            first_end = end if first_end is None or end < first_end else first_end
            last_end = end if last_end is None or end > last_end else last_end
            cur = conn.execute("INSERT OR IGNORE INTO plays (start_utc, end_utc, ms_played, track, artist, album, spotify_uri) VALUES (?,?,?,?,?,?,?)",
                               (start.strftime(FMT), end.strftime(FMT), ms, track, artist, album, uri))
            added += cur.rowcount
    if first_end is not None:
        # Spotify's file is exact; plays polled live inside its period are replaced by it so nothing is counted twice
        conn.execute("DELETE FROM plays WHERE source = 'live' AND end_utc >= ? AND end_utc <= ?", (first_end.strftime(FMT), last_end.strftime(FMT)))
    conn.commit()
    return {"files": len(files), "added": added, "skipped_short": short, "skipped_other": other}


if __name__ == "__main__":
    target = Path(sys.argv[1]) if len(sys.argv) > 1 else EXPORT_DIR
    try:
        res = import_dir(db.connect(), target)
    except FileNotFoundError as e:
        sys.exit(str(e))
    if not res["files"]:
        sys.exit(f"No Streaming_History_Audio_*.json files found under {target}.")
    print(f"Read {res['files']} file(s): added {res['added']} plays, dropped {res['skipped_short']} skips (<30 s) and {res['skipped_other']} non-song entries.")
