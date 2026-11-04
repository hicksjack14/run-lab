"""Put the songs you listened to on a run into that run's Strava description, in the order you played them.

Off until you turn it on:  python -m ingest.strava_post enable     (only runs from today on are ever touched)
  python -m ingest.strava_post preview <run_id>   show the text for a run, post nothing
  python -m ingest.strava_post run                post for runs that are ready (update.sh does this every hour)
  python -m ingest.strava_post disable

Needs Strava's "write" permission: run `python -m ingest.strava_api auth` once more and tick the new permission on Strava's page.
A run is ready 45 minutes after it ends (Spotify is checked every 30 minutes, so by then every song is saved). The song list is added
under whatever description you already wrote and is never added twice. Runs older than 3 days are left alone.
"""
import sys
from datetime import date, datetime, timedelta, timezone

import db
from analysis import fitness, music_match
from ingest import strava_api
from ingest.strava_api import RateLimited, StravaError

HEADER = "🎧 Songs on this run (via Run Lab)"
READY_AFTER_MIN = 45
MAX_AGE_DAYS = 3
MAX_CHARS = 1800                      # stay well under Strava's description limit


class WriteNotAllowed(Exception):
    pass


def format_description(songs):
    """Numbered list in play order. Cut with '+N more' if it would get too long."""
    lines, size = [], len(HEADER)
    for i, s in enumerate(songs, 1):
        line = f"{i}. {s['track']}" + (f" - {s['artist']}" if s.get("artist") else "")
        if size + len(line) + 1 > MAX_CHARS - 20:
            lines.append(f"+{len(songs) - i + 1} more")
            break
        lines.append(line)
        size += len(line) + 1
    return HEADER + "\n" + "\n".join(lines)


def _state(conn):
    st = fitness.get_settings(conn).get("song_posts") or {}
    return {"enabled": bool(st.get("enabled")), "since": st.get("since"), "done": dict(st.get("done") or {})}


def _run_end(run):
    start = datetime.strptime(run["start_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return start + timedelta(seconds=run["elapsed_s"] or run["moving_s"] or 0)


def post_ready(conn, client, now=None, log=print):
    """Add the song list to every ready run that has not had it yet. Returns the run ids posted."""
    st = _state(conn)
    if not st["enabled"]:
        return []
    now = now or datetime.now(timezone.utc)
    posted = []
    runs = conn.execute("SELECT strava_id, name, start_utc, elapsed_s, moving_s FROM runs WHERE substr(start_local, 1, 10) >= ? ORDER BY start_utc", (st["since"],)).fetchall()
    for run in runs:
        rid, end = run["strava_id"], _run_end(run)
        if rid in st["done"] or now < end + timedelta(minutes=READY_AFTER_MIN) or now > end + timedelta(days=MAX_AGE_DAYS):
            continue
        songs = music_match.songs_for_run(conn, rid)
        if not songs:
            continue                                  # no music saved for this run (yet): try again next hour, until it is too old
        try:
            current = client.get(f"/activities/{rid}").get("description") or ""
            if HEADER not in current:                 # never post twice, even if our record was lost
                text = format_description(songs)
                client.put(f"/activities/{rid}", description=(current.rstrip() + "\n\n" if current.strip() else "") + text)
                posted.append(rid)
                log(f"  added {len(songs)} songs to Strava: {run['name']}")
        except StravaError as e:
            if e.status in (401, 403):
                raise WriteNotAllowed("Strava refused the edit. Run `python -m ingest.strava_api auth` again and allow it to update your activities.") from e
            raise
        st["done"][rid] = now.isoformat(timespec="seconds")
        fitness.set_setting(conn, "song_posts", {"enabled": True, "since": st["since"], "done": st["done"]})
    return posted


def main(argv):
    cmd = argv[1] if len(argv) > 1 else ""
    conn = db.connect()
    st = _state(conn)
    if cmd == "enable":
        since = date.today().isoformat()
        fitness.set_setting(conn, "song_posts", {"enabled": True, "since": since, "done": st["done"]})
        return print(f"On. From runs on {since} onward, the songs get added to Strava about 45 minutes after you finish. Make sure you re-ran `python -m ingest.strava_api auth` for the write permission.")
    if cmd == "disable":
        fitness.set_setting(conn, "song_posts", {"enabled": False, "since": st["since"], "done": st["done"]})
        return print("Off. Nothing more will be posted to Strava.")
    if cmd == "preview":
        songs = music_match.songs_for_run(conn, argv[2]) if len(argv) > 2 else []
        return print(format_description(songs) if songs else "No songs saved for that run (or no run with that id).")
    if cmd == "run":
        if not st["enabled"]:
            return print("Song posting is off. Turn it on with: python -m ingest.strava_post enable")
        try:
            n = len(post_ready(conn, strava_api.StravaClient(strava_api.load_env())))
        except WriteNotAllowed as e:
            sys.exit(str(e))
        except RateLimited:
            return print("Hit Strava's rate limit; will retry next time.")
        return print(f"Added songs to {n} run(s) on Strava.")
    sys.exit("Usage: python -m ingest.strava_post enable | disable | preview <run_id> | run")


if __name__ == "__main__":
    main(sys.argv)
