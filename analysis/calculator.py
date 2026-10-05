"""Model behind the race-time calculator: how he runs now, so the page can estimate a finish time.

Two estimates, deliberately different:
  - "usual effort": his own recent runs say how his pace slows as the distance grows (pace = a + b*ln(miles)),
    so this is roughly the pace he holds in training at that distance. It is honest about running out of evidence:
    beyond his longest run the band widens and the confidence drops.
  - "race effort": what his fitness score says he could run if he raced the distance flat out.
The page adds his stops (water, gels) on top of either one. Pure functions plus one DB reader.
"""
import math
import statistics
from datetime import date, timedelta

from analysis import fitness, insights, zones
from analysis.zones import MI

CURVE_MILES = [x / 2 for x in range(2, 61)]   # 1.0, 1.5 ... 30.0
RECENT_DAYS = 120
MIN_RUNS = 8
MIN_SPREAD_MI = 1.5          # need runs of noticeably different lengths to see a trend


def _fit(xs, ys):
    fit = insights.ols([[1.0, x] for x in xs], ys)
    if not fit:
        return None
    a, b = fit["beta"]
    resid = [y - (a + b * x) for x, y in zip(xs, ys)]
    return a, b, math.sqrt(sum(r * r for r in resid) / max(1, len(resid) - 2))


def build(conn, today=None):
    today = today or date.today()
    snap = fitness.snapshot(conn, today)
    mine = fitness.get_settings(conn).get("calc_defaults", {})        # his own starting pace and stop routine, if saved
    cutoff = (today - timedelta(days=RECENT_DAYS)).isoformat()
    rows = [r for r in conn.execute(
        "SELECT distance_m, moving_s, elapsed_s, avg_hr FROM runs WHERE distance_m >= 1600 AND moving_s >= 600 AND substr(start_local, 1, 10) >= ?", (cutoff,))]
    runs = [{"mi": r["distance_m"] / MI, "pace": r["moving_s"] / (r["distance_m"] / MI), "hr": r["avg_hr"],
             "stopped_min_per_mi": max(0, (r["elapsed_s"] or r["moving_s"]) - r["moving_s"]) / 60 / (r["distance_m"] / MI)} for r in rows]
    longest = conn.execute("SELECT COALESCE(MAX(distance_m), 0) FROM runs").fetchone()[0] / MI

    usual = None
    mis = [r["mi"] for r in runs]
    if len(runs) >= MIN_RUNS and max(mis) - min(mis) >= MIN_SPREAD_MI:
        fit = _fit([math.log(m) for m in mis], [r["pace"] for r in runs])
        if fit:
            a, b, sd = fit
            if b < 0:                         # faster on longer runs happens by chance; never predict that continuing
                b = 0.0
                a = statistics.mean(r["pace"] for r in runs) - b * statistics.mean(math.log(m) for m in mis)
            usual = {"a": a, "b": b, "sd": sd, "n": len(runs), "seconds_slower_per_doubling": b * math.log(2)}

    curve = []
    for d in CURVE_MILES:
        entry = {"mi": d, "usual": None, "band": None, "confidence": None, "race_s": None}
        if usual:
            ratio = d / longest if longest else 99
            entry.update(usual=usual["a"] + usual["b"] * math.log(d),
                         band=usual["sd"] * (1 + 3 * max(0.0, ratio - 1)),
                         confidence="solid" if ratio <= 1.1 else "stretch" if ratio <= 2.0 else "guess")
        if snap["vdot"]:
            entry["race_s"] = zones.predict_time(snap["vdot"], d * MI)
        curve.append(entry)

    stops = None
    stopped = [r["stopped_min_per_mi"] for r in runs if r["mi"] >= 3]
    if stopped:
        stops = {"observed_min_per_mile": statistics.median(stopped), "n": len(stopped)}

    hr_at_pace = None
    hr_runs = [r for r in runs if r["hr"]]
    if len(hr_runs) >= MIN_RUNS and max(r["pace"] for r in hr_runs) - min(r["pace"] for r in hr_runs) >= 20:
        fit = _fit([r["pace"] for r in hr_runs], [r["hr"] for r in hr_runs])
        if fit:
            hr_at_pace = {"c": fit[0], "k": fit[1], "sd": fit[2], "n": len(hr_runs),
                          "pace_lo": min(r["pace"] for r in hr_runs), "pace_hi": max(r["pace"] for r in hr_runs)}

    return {"vdot": snap["vdot"], "vdot_is_estimate": snap["vdot_is_estimate"], "max_hr": snap["max_hr"], "longest_mi": longest,
            "usual": usual, "curve": curve, "stops": stops, "hr_at_pace": hr_at_pace,
            "defaults": {"stop_every_mi": mine.get("stop_every_mi", 3.0), "stop_min": mine.get("stop_min", 1.0), "pace_s": mine.get("pace_s")},
            "recent_runs": len(runs)}
