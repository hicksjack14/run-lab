"""Line up Spotify plays with a run's timeline and measure what he was doing during each song.

A play row stores when it started/ended in UTC. A run stores its UTC start and a per-second stream whose time axis is
seconds since the start of the activity, so a play maps straight onto the run: offset = play time - run start.
"""
import math
import statistics
from collections import defaultdict
from datetime import datetime, timedelta

MI = 1609.344
MIN_OVERLAP_S = 10        # a song that overlaps the run by less than this is dropped
WARMUP_S = 8 * 60         # songs in the first 8 minutes are left out of the "does this artist help" analysis
MIN_SLICE_S = 60
CLIP = 0.15
FMT = "%Y-%m-%dT%H:%M:%SZ"


def _parse(ts):
    return datetime.strptime(ts, FMT)


def _stream(conn, run_id):
    return conn.execute("SELECT t_s, hr, speed_mps, cadence_spm, moving FROM run_streams WHERE strava_id = ? ORDER BY t_s", (run_id,)).fetchall()


def _window_stats(rows, s, e):
    """Average pace / HR / cadence over the moving samples between s and e seconds."""
    pick = [r for r in rows if s <= r["t_s"] <= e and r["moving"] != 0 and r["speed_mps"] and r["speed_mps"] >= 0.8]
    if not pick:
        return None
    speed = statistics.mean(r["speed_mps"] for r in pick)
    hrs = [r["hr"] for r in pick if r["hr"]]
    cads = [r["cadence_spm"] for r in pick if r["cadence_spm"]]
    hr = statistics.mean(hrs) if hrs else None
    return {"avg_pace": MI / speed, "avg_hr": hr, "avg_cadence": statistics.mean(cads) if cads else None,
            "ef": (speed * 60 / hr) if hr else None}


def songs_for_run(conn, run_id):
    run = conn.execute("SELECT start_utc FROM runs WHERE strava_id = ?", (run_id,)).fetchone()
    rows = _stream(conn, run_id)
    if not run or not rows:
        return []
    start = _parse(run["start_utc"])
    end_s = rows[-1]["t_s"]
    stop = start + timedelta(seconds=end_s)
    plays = conn.execute("SELECT * FROM plays WHERE end_utc > ? AND start_utc < ? ORDER BY start_utc",
                         (start.strftime(FMT), stop.strftime(FMT))).fetchall()
    songs = []
    for p in plays:
        s = max(0.0, (_parse(p["start_utc"]) - start).total_seconds())
        e = min(float(end_s), (_parse(p["end_utc"]) - start).total_seconds())
        if e - s < MIN_OVERLAP_S:
            continue
        stats = _window_stats(rows, s, e) or {"avg_pace": None, "avg_hr": None, "avg_cadence": None, "ef": None}
        songs.append({"track": p["track"], "artist": p["artist"], "album": p["album"], "uri": p["spotify_uri"],
                      "start_s": s, "end_s": e, "seconds": e - s, **stats})
    return songs


def slices_for_run(conn, run_id):
    """Per-song efficiency relative to the same run's overall efficiency (so run-to-run differences cancel out)."""
    songs = songs_for_run(conn, run_id)
    rows = _stream(conn, run_id)
    overall = _window_stats(rows, 0, rows[-1]["t_s"]) if rows else None
    if not songs or not overall or not overall["ef"]:
        return []
    return [{"artist": s["artist"], "track": s["track"], "run_id": run_id, "seconds": s["seconds"], "rel_ef": s["ef"] / overall["ef"] - 1}
            for s in songs if s["ef"] and s["start_s"] >= WARMUP_S and s["seconds"] >= MIN_SLICE_S]


def all_slices(conn):
    """Slices from every run that has music playing during it (songs_for_run finds the overlapping plays)."""
    if not conn.execute("SELECT 1 FROM plays LIMIT 1").fetchone():
        return []
    out = []
    for r in conn.execute("SELECT strava_id FROM runs"):
        out.extend(slices_for_run(conn, r["strava_id"]))
    return out


def music_findings(slices, min_songs=5, min_runs=3):
    """Which artists coincide with better or worse running.

    Each artist's songs are compared with all the OTHER songs (Welch's t-test). Comparing against the other songs rather than
    against the whole run cancels the drift every run has (later minutes are always a little less efficient), so only an
    artist's own effect is left. Never more than medium confidence.
    """
    # a song can't really change efficiency by more than ~15%; larger values are sensor glitches, so clip them
    slices = [{**s, "rel_ef": max(-CLIP, min(CLIP, s["rel_ef"]))} for s in slices]
    by_artist = defaultdict(list)
    for s in slices:
        if s["artist"]:
            by_artist[s["artist"]].append(s)
    ranked = []
    for artist, items in by_artist.items():
        n = len(items)
        others = [s["rel_ef"] for s in slices if s["artist"] != artist]
        if n < min_songs or len({i["run_id"] for i in items}) < min_runs or len(others) < 10:
            continue
        vals = [i["rel_ef"] for i in items]
        diff = statistics.mean(vals) - statistics.mean(others)
        se = math.sqrt(statistics.pvariance(vals) / n + statistics.pvariance(others) / len(others))
        t = diff / se if se > 1e-9 else math.copysign(99.0, diff)
        if abs(t) >= 2 and abs(diff) >= 0.01:
            ranked.append((artist, n, diff, t, len({i["run_id"] for i in items})))
    findings = []
    caveat = " Songs are compared with the rest of your music on the same runs, but where you are in a run can't be fully separated from what is playing, so treat it as a lead."
    best = max((r for r in ranked if r[2] > 0), key=lambda r: r[3], default=None)
    worst = min((r for r in ranked if r[2] < 0), key=lambda r: r[3], default=None)
    for item, kind in ((best, "works"), (worst, "doesnt")):
        if not item:
            continue
        artist, n, diff, t, nruns = item
        conf = "medium" if abs(t) >= 3 and n >= 10 else "low"
        if kind == "works":
            title, body = f"You run best to {artist}", f"During {n} songs by {artist} across {nruns} runs you were about {diff * 100:.1f}% more efficient than during your other songs." + caveat
        else:
            title, body = f"Your efficiency dips during {artist}", f"During {n} songs by {artist} across {nruns} runs you were about {abs(diff) * 100:.1f}% less efficient than during your other songs." + caveat
        findings.append({"id": f"music-{kind}", "kind": kind, "title": title, "body": body, "stat": {"label": "vs your other songs", "value": f"{diff * 100:+.1f}%"},
                         "confidence": conf, "n": n, "runs": []})
    return findings
