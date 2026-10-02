"""Database-aware fitness helpers: settings, current fitness snapshot, weekly mileage, plan adherence."""
import json
from collections import defaultdict
from datetime import date, timedelta

from analysis import zones
from analysis.zones import MI, fmt_pace, fmt_time


def get_settings(conn):
    return {r["key"]: json.loads(r["value"]) for r in conn.execute("SELECT key, value FROM settings")}


def set_setting(conn, key, value):
    if value is None:
        conn.execute("DELETE FROM settings WHERE key = ?", (key,))
    else:
        conn.execute("INSERT INTO settings (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                     (key, json.dumps(value)))
    conn.commit()


def _monday(d):
    return d - timedelta(days=d.weekday())


def weekly_miles(conn, today, n=12):
    """Miles per Monday-start week for the last n weeks, oldest first (weeks with no runs are 0)."""
    this_monday = _monday(today)
    first = this_monday - timedelta(days=7 * (n - 1))
    totals = defaultdict(float)
    for r in conn.execute("SELECT substr(start_local, 1, 10) AS d, distance_m FROM runs WHERE substr(start_local, 1, 10) >= ?",
                          (first.isoformat(),)):
        totals[_monday(date.fromisoformat(r["d"])).isoformat()] += (r["distance_m"] or 0) / MI
    return [{"start": (first + timedelta(days=7 * i)).isoformat(),
             "miles": totals.get((first + timedelta(days=7 * i)).isoformat(), 0.0)} for i in range(n)]


def snapshot(conn, today=None):
    today = today or date.today()
    settings = get_settings(conn)
    efforts = [dict(r) for r in conn.execute(
        "SELECT be.type AS type, be.seconds AS seconds, substr(r.start_local, 1, 10) AS date "
        "FROM best_efforts be JOIN runs r ON r.strava_id = be.strava_id")]
    est = zones.estimate_vdot(efforts, today)
    needs = []

    if settings.get("vdot_override"):
        vdot, vdot_source, basis = float(settings["vdot_override"]), "override", None
    elif est:
        vdot, vdot_source, basis = est["vdot"], "data", est["basis"]
    else:
        vdot, vdot_source, basis = None, None, None
        needs.append("A 5K-or-longer effort in the last 4 months (or a manual fitness override) is needed to set paces.")

    cutoff = (today - timedelta(days=365)).isoformat()
    max_hrs = [r["max_hr"] for r in conn.execute(
        "SELECT max_hr FROM runs WHERE max_hr IS NOT NULL AND substr(start_local, 1, 10) >= ?", (cutoff,))]
    if settings.get("max_hr"):
        max_hr, max_hr_source = int(settings["max_hr"]), "override"
    else:
        max_hr = zones.estimate_max_hr(max_hrs)
        max_hr_source = "data" if max_hr else None
        if not max_hr:
            needs.append("Heart-rate data from at least one run is needed to set heart-rate zones.")

    paces = predictions = None
    if vdot:
        p = zones.training_paces(vdot)
        paces = {
            "easy": {"fast": p["easy_fast"], "slow": p["easy_slow"], "text": f"{fmt_pace(p['easy_fast'])} to {fmt_pace(p['easy_slow'])}"},
            "marathon": {"pace": p["marathon"], "text": fmt_pace(p["marathon"])},
            "threshold": {"pace": p["threshold"], "text": fmt_pace(p["threshold"])},
            "interval": {"pace": p["interval"], "text": fmt_pace(p["interval"])},
        }
        predictions = zones.race_predictions(vdot)

    start = (today - timedelta(days=27)).isoformat()
    last4 = conn.execute("SELECT COALESCE(SUM(distance_m), 0) FROM runs WHERE substr(start_local, 1, 10) >= ?", (start,)).fetchone()[0]
    return {
        "vdot": vdot, "vdot_source": vdot_source, "vdot_basis": basis,
        "max_hr": max_hr, "max_hr_source": max_hr_source,
        "hr_zones": zones.hr_zones(max_hr) if max_hr else None,
        "paces": paces, "predictions": predictions,
        "prediction_text": {k: fmt_time(v) for k, v in predictions.items()} if predictions else None,
        "recent_weekly_mi": last4 / MI / 4,
        "needs": needs,
    }


def adherence(conn, workouts, today):
    """Compare planned workouts with what he actually ran that day."""
    days = defaultdict(list)
    for r in conn.execute("SELECT strava_id, substr(start_local, 1, 10) AS d, distance_m FROM runs"):
        days[r["d"]].append((r["distance_m"] or 0, r["strava_id"]))
    out = []
    for w in workouts:
        runs = days.get(w["date"], [])
        actual = sum(d for d, _ in runs) / MI
        run_id = max(runs)[1] if runs else None
        d = date.fromisoformat(w["date"])
        if d > today:
            status = "upcoming"
        elif actual >= 0.7 * w["distance_mi"]:
            status = "done"
        elif actual > 0:
            status = "partial"
        elif d == today:
            status = "today"
        else:
            status = "missed"
        out.append({**w, "status": status, "actual_mi": actual, "run_id": run_id})
    return out
