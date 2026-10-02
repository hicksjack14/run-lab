"""Load Strava dump JSON (pulled by Claude via the Strava connector) into SQLite.

Safe to re-run: runs are upserted by strava_id and their streams/laps are replaced.
A per-run timezone override (runs.tz) survives re-imports.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import db

DEFAULT_TZ = "America/New_York"
DUMP_DIR = Path(__file__).resolve().parent.parent / "data" / "strava-dumps"


def local_to_utc(start_local, tz_name):
    """'2026-09-29T18:23:11' in a timezone -> '2026-09-29T22:23:11Z'."""
    naive = datetime.fromisoformat(start_local)
    utc = naive.replace(tzinfo=ZoneInfo(tz_name)).astimezone(timezone.utc)
    return utc.strftime("%Y-%m-%dT%H:%M:%SZ")


def _at(values, i):
    """values[i], or None if the stream is missing or shorter than expected."""
    return values[i] if values is not None and i < len(values) else None


def _spm(cadence):
    """Strava cadence is per foot; steps per minute is double."""
    return None if cadence is None else cadence * 2


def import_dump(conn, dump):
    act = dump["activity"]
    summary = act.get("summary", {})
    perf = dump.get("performance", {})
    streams = dump.get("streams", {})
    sid = str(act["id"])

    existing = conn.execute("SELECT tz FROM runs WHERE strava_id = ?", (sid,)).fetchone()
    tz = existing["tz"] if existing else DEFAULT_TZ

    location = streams.get("location")
    avg_cad = summary.get("avg_cadence")

    conn.execute(
        """INSERT INTO runs (strava_id, name, start_local, tz, start_utc, distance_m, moving_s,
               elapsed_s, elevation_gain_m, avg_hr, max_hr, avg_cadence_spm, effort, gear_id, has_gps)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(strava_id) DO UPDATE SET
               name=excluded.name, start_local=excluded.start_local, start_utc=excluded.start_utc,
               distance_m=excluded.distance_m, moving_s=excluded.moving_s,
               elapsed_s=excluded.elapsed_s, elevation_gain_m=excluded.elevation_gain_m,
               avg_hr=excluded.avg_hr, max_hr=excluded.max_hr,
               avg_cadence_spm=excluded.avg_cadence_spm, effort=excluded.effort,
               gear_id=excluded.gear_id, has_gps=excluded.has_gps""",
        (
            sid, act.get("name"), act["start_local"], tz, local_to_utc(act["start_local"], tz),
            summary.get("distance"), summary.get("moving_time"), summary.get("elapsed_time"),
            summary.get("elevation_gain"), perf.get("average_heartrate"), perf.get("max_heartrate"),
            _spm(avg_cad), summary.get("relative_effort"), act.get("gear_id"),
            1 if location else 0,
        ),
    )

    for table in ("run_streams", "run_laps", "best_efforts"):
        conn.execute(f"DELETE FROM {table} WHERE strava_id = ?", (sid,))

    times = streams.get("time") or []
    for i, t in enumerate(times):
        loc = _at(location, i)
        moving = _at(streams.get("moving"), i)
        conn.execute(
            "INSERT INTO run_streams VALUES (?,?,?,?,?,?,?,?,?,?)",
            (
                sid, t, _at(streams.get("heart_rate"), i), _at(streams.get("velocity_smooth"), i),
                _spm(_at(streams.get("cadence"), i)), _at(streams.get("distance"), i),
                None if moving is None else int(moving),
                loc[0] if loc else None, loc[1] if loc else None, _at(streams.get("altitude"), i),
            ),
        )

    for idx, lap in enumerate(perf.get("laps", [])):
        conn.execute(
            "INSERT INTO run_laps VALUES (?,?,?,?,?,?)",
            (sid, idx, lap.get("distance"), lap.get("moving_time"), lap.get("avg_hr"), lap.get("max_hr")),
        )

    for be in perf.get("best_efforts", []):
        conn.execute(
            "INSERT INTO best_efforts VALUES (?,?,?)", (sid, be["type_value"], be["value"])
        )

    conn.commit()
    return sid


def import_dir(conn, directory=DUMP_DIR):
    ids = []
    for path in sorted(Path(directory).glob("*.json")):
        ids.append(import_dump(conn, json.loads(path.read_text())))
    return ids


if __name__ == "__main__":
    conn = db.connect()
    ids = import_dir(conn)
    print(f"Imported {len(ids)} run(s): {', '.join(ids) or '(none found in data/strava-dumps/)'}")
    sys.exit(0)
