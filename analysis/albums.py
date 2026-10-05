"""Spot albums that were played all the way through.

An album counts as finished when EVERY track on it was mostly played (at least 80% of its length) and the
whole set happened inside a 48-hour window. Order doesn't matter, so shuffle, pauses and a night's sleep in
the middle are all fine. Pure functions, no database or network.

Only plays captured live from Spotify have the album details this needs (album id, track number, track
length); plays imported from Spotify's old export don't, so they can never complete an album.
Singles and tiny releases are ignored: an "album" here is Spotify's own album type with at least 4 tracks.
"""
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

FMT = "%Y-%m-%dT%H:%M:%SZ"
PLAYED_FRACTION = 0.8
WINDOW = timedelta(hours=48)
MIN_TRACKS = 4
DEFAULT_TZ = "America/New_York"


def _parse(ts):
    return datetime.strptime(ts, FMT)


def _mostly_played(p):
    dur = p.get("duration_ms") or 0
    return dur > 0 and (p.get("ms_played") or 0) >= PLAYED_FRACTION * dur


def listened_on(finished_at, tz_name=DEFAULT_TZ):
    """The local calendar date (YYYY-MM-DD) of a UTC timestamp like '2026-10-06T02:30:00Z'."""
    return _parse(finished_at).replace(tzinfo=timezone.utc).astimezone(ZoneInfo(tz_name)).strftime("%Y-%m-%d")


def find_finished_albums(plays):
    """plays: dicts with album_id, album, artist, album_type, total_tracks, track_number, disc_number,
    duration_ms, ms_played, end_utc. Returns [{album_id, album, artist, total_tracks, finished_at}], oldest first.
    An album played through twice (separated by more than the window) is reported twice."""
    by_album = {}
    for p in plays:
        if not p.get("album_id") or p.get("album_type") != "album" or not p.get("track_number"):
            continue
        by_album.setdefault(p["album_id"], []).append(p)

    finished = []
    for album_id, rows in by_album.items():
        total = max((r.get("total_tracks") or 0) for r in rows)
        if total < MIN_TRACKS:
            continue
        good = sorted((r for r in rows if _mostly_played(r)), key=lambda r: r["end_utc"])
        i = 0
        while i < len(good):
            window_start = _parse(good[i]["end_utc"])
            seen, j, done_at = set(), i, None
            while j < len(good) and _parse(good[j]["end_utc"]) - window_start <= WINDOW:
                seen.add((good[j].get("disc_number") or 1, good[j]["track_number"]))
                if len(seen) >= total:
                    done_at = good[j]["end_utc"]
                    break
                j += 1
            if done_at:
                first = good[i]
                finished.append({"album_id": album_id, "album": first.get("album"), "artist": first.get("artist"),
                                 "total_tracks": total, "finished_at": done_at})
                i = j + 1        # a second finish needs a fresh run of plays after this one
            else:
                i += 1
    finished.sort(key=lambda f: f["finished_at"])
    return finished
