"""Fitness and pace math: VDOT (Jack Daniels), training paces, race predictions, HR zones.

Pure functions, no database. Paces are seconds per mile; times are seconds.
"""
import math
from datetime import date

MI = 1609.344

# Strava best_effort names -> distance in metres
EFFORT_DISTANCES = {
    "Fastest400": 400, "FastestHalfMile": 804.672, "Fastest1k": 1000, "FastestMile": MI,
    "Fastest2Mile": 2 * MI, "Fastest5k": 5000, "Fastest10k": 10000, "Fastest15k": 15000,
    "Fastest10Mile": 10 * MI, "Fastest20k": 20000, "FastestHalfMarathon": 21097.5,
    "Fastest30k": 30000, "FastestMarathon": 42195,
}
RACES = {"5K": 5000, "10K": 10000, "Half marathon": 21097.5, "Marathon": 42195}

HR_ZONE_NAMES = ["Recovery", "Easy aerobic", "Tempo", "Threshold", "VO2 max"]
# fraction of max HR where each zone starts
HR_ZONE_STARTS = [0.5, 0.6, 0.7, 0.8, 0.9]


def _vo2_at_velocity(v):  # v in metres/minute
    return -4.60 + 0.182258 * v + 0.000104 * v * v


def _fraction_of_max(t_min):  # fraction of VO2max sustainable for t minutes
    return 0.8 + 0.1894393 * math.exp(-0.012778 * t_min) + 0.2989558 * math.exp(-0.1932605 * t_min)


def vdot(distance_m, time_s):
    t = time_s / 60
    return _vo2_at_velocity(distance_m / t) / _fraction_of_max(t)


def predict_time(vdot_value, distance_m):
    """Race time (seconds) a given VDOT is worth over a distance. Bisection: vdot() falls as time rises."""
    lo, hi = 60.0, 36000.0
    for _ in range(80):
        mid = (lo + hi) / 2
        if vdot(distance_m, mid) > vdot_value:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def race_predictions(vdot_value):
    return {name: predict_time(vdot_value, d) for name, d in RACES.items()}


def _pace_at_fraction(vdot_value, fraction):
    vo2 = vdot_value * fraction
    a, b, c = 0.000104, 0.182258, -(4.60 + vo2)
    v = (-b + math.sqrt(b * b - 4 * a * c)) / (2 * a)  # metres/minute
    return MI / v * 60


def training_paces(vdot_value):
    """Seconds per mile for each kind of training run."""
    return {
        "easy_slow": _pace_at_fraction(vdot_value, 0.62),
        "easy_fast": _pace_at_fraction(vdot_value, 0.72),
        "marathon": predict_time(vdot_value, 42195) / (42195 / MI),
        "threshold": _pace_at_fraction(vdot_value, 0.88),
        "interval": _pace_at_fraction(vdot_value, 0.975),
    }


def hr_zones(max_hr):
    los = [round(max_hr * f) for f in HR_ZONE_STARTS]
    zones = []
    for i, lo in enumerate(los):
        hi = los[i + 1] - 1 if i + 1 < len(los) else max_hr
        zones.append({"zone": i + 1, "name": HR_ZONE_NAMES[i], "lo": lo, "hi": hi})
    return zones


def zone_for_hr(hr, max_hr):
    zone = 1
    for z in hr_zones(max_hr):
        if hr >= z["lo"]:
            zone = z["zone"]
    return zone


def estimate_max_hr(run_max_hrs):
    """Highest HR he really reaches, ignoring optical-sensor spikes: the 95th percentile of per-run
    maximums, or with very few runs, the highest value after dropping the single top reading."""
    vals = sorted(v for v in run_max_hrs if v)
    if not vals:
        return None
    if len(vals) >= 8:
        return round(vals[int(0.95 * (len(vals) - 1))])
    return round(vals[-2] if len(vals) >= 2 else vals[0])


def estimate_vdot(efforts, today=None, window_days=120):
    """Best recent fitness estimate from best-efforts inside training runs.

    Efforts under 5K are discounted 3% (a mile split inside a run is rarely all-out and says less about
    endurance). Anything under 1K is ignored. Returns {"vdot", "basis"} or None.
    """
    today = date.fromisoformat(today) if isinstance(today, str) else (today or date.today())
    best = None
    for e in efforts:
        dist = EFFORT_DISTANCES.get(e["type"])
        if not dist or dist < 1000:
            continue
        age = (today - date.fromisoformat(e["date"][:10])).days
        if age < 0 or age > window_days:
            continue
        v = vdot(dist, e["seconds"]) * (1.0 if dist >= 5000 else 0.97)
        if best is None or v > best["vdot"]:
            best = {"vdot": v, "basis": {**e, "distance_m": dist}}
    return best


def fmt_pace(seconds_per_mile):
    s = round(seconds_per_mile)
    return f"{s // 60}:{s % 60:02d}"


def fmt_time(seconds):
    s = round(seconds)
    h, rem = divmod(s, 3600)
    return f"{h}:{rem // 60:02d}:{rem % 60:02d}" if h else f"{rem // 60}:{rem % 60:02d}"
