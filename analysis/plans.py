"""Training plan generator: base, build, peak, taper toward a goal race.

Pure functions. Distances in miles, paces in seconds per mile, dates as datetime.date.
Rules of thumb used (conservative, aimed at a newer runner):
  - weekly mileage grows at most ~8% a week, with a lighter recovery week every 4th week
  - one quality session a week (tempo or intervals), one long run, the rest easy
  - the long run is always the longest run of the week
  - taper shrinks volume for the last 1-3 weeks; the day before the race is a rest day
"""
from datetime import date, timedelta

from analysis import zones
from analysis.zones import MI

DISTANCES = {"5K": 5000, "10K": 10000, "Half marathon": 21097.5, "Marathon": 42195}
RULES = {
    "5K": {"min_weeks": 6, "taper": 1, "peak_cap": 30, "long_cap": 8, "long_frac": 0.27},
    "10K": {"min_weeks": 8, "taper": 1, "peak_cap": 38, "long_cap": 10, "long_frac": 0.28},
    "Half marathon": {"min_weeks": 10, "taper": 2, "peak_cap": 45, "long_cap": 13, "long_frac": 0.30},
    "Marathon": {"min_weeks": 14, "taper": 3, "peak_cap": 55, "long_cap": 20, "long_frac": 0.32},
}
TAPER_FRACTIONS = {1: [0.6], 2: [0.75, 0.5], 3: [0.8, 0.65, 0.45]}
GROWTH = 1.08

# (weekday, role) with the long run on Sunday (Mon=0 .. Sun=6)
PATTERNS = {
    3: [(1, "quality"), (3, "easy"), (6, "long")],
    4: [(1, "quality"), (3, "easy"), (5, "easy"), (6, "long")],
    5: [(0, "easy"), (1, "quality"), (3, "easy"), (5, "easy"), (6, "long")],
    6: [(0, "easy"), (1, "quality"), (2, "easy"), (3, "easy"), (5, "easy"), (6, "long")],
}


def _half(x):
    return round(x * 2) / 2


def _monday(d):
    return d - timedelta(days=d.weekday())


def _rules_for(goal):
    if isinstance(goal, str):
        return goal, DISTANCES[goal], RULES[goal]
    metres = float(goal)
    name = "5K" if metres <= 6000 else "10K" if metres <= 12000 else "Half marathon" if metres <= 25000 else "Marathon"
    return "Race", metres, RULES[name]


def _min_feasible_weekly(days):
    return (days - 2) * 2.0 + 6.5  # easy days at 2 mi, a ~3 mi long run floor, a ~3.5 mi quality day


def _weekly_plan(n_weeks, rules, start_mi):
    """List of {target, phase, recovery} per week."""
    taper = min(rules["taper"], n_weeks)
    build_n = n_weeks - taper
    cap = max(rules["peak_cap"], start_mi)
    weeks, level = [], start_mi
    for i in range(build_n):
        recovery = i % 4 == 3
        if i > 0 and not recovery:
            level = min(level * GROWTH, cap)
        frac = i / max(1, build_n)
        phase = "base" if frac < 0.4 else "build" if frac < 0.8 else "peak"
        weeks.append({"target": level * (0.8 if recovery else 1.0), "phase": phase, "recovery": recovery})
    peak = max((w["target"] for w in weeks), default=start_mi)
    for frac in TAPER_FRACTIONS[taper]:
        weeks.append({"target": peak * frac, "phase": "taper", "recovery": False})
    return weeks


def _workout(day, week, phase, kind, title, miles, pace_lo, pace_hi, zones_range, description):
    mid = (pace_lo + pace_hi) / 2
    return {
        "date": day.isoformat(), "week": week, "phase": phase, "kind": kind, "title": title,
        "distance_mi": round(miles, 1), "pace_lo": pace_lo, "pace_hi": pace_hi,
        "hr_zone": zones_range, "duration_min": round(miles * mid / 60), "description": description,
    }


def _quality(kind, q_mi, paces, progress):
    """Return (title, miles, pace_lo, pace_hi, zones, description) for a quality session."""
    if kind == "tempo":
        tempo_mi = min(6.0, max(1.0, q_mi - 2.0))
        tempo_mi = round(tempo_mi * 2) / 2
        t = paces["threshold"]
        return (f"Tempo {tempo_mi + 2:.1f} mi", tempo_mi + 2.0, t - 5, t + 5, (3, 4),
                f"1 mi easy warm-up, {tempo_mi:g} mi at tempo pace ({zones.fmt_pace(t - 5)}-{zones.fmt_pace(t + 5)}/mi), "
                f"1 mi easy cool-down. Comfortably hard: short sentences only.")
    if kind == "intervals":
        rep_m = 800 if progress < 0.4 else 1000 if progress < 0.8 else 1200
        rep_mi = rep_m / MI
        reps = max(3, min(8, round((q_mi - 2.5) / (rep_mi + 0.25))))
        total = 2.5 + reps * (rep_mi + 0.25)
        i = paces["interval"]
        return (f"Intervals {reps} x {rep_m} m", total, i - 5, i + 5, (4, 5),
                f"1.5 mi easy warm-up, {reps} x {rep_m} m at interval pace ({zones.fmt_pace(i - 5)}-{zones.fmt_pace(i + 5)}/mi) "
                f"with 400 m jog recoveries, 1 mi easy cool-down.")
    e_fast, e_slow = paces["easy_fast"], paces["easy_slow"]
    return ("Easy + strides", q_mi, e_fast, e_slow, (2, 2),
            f"Easy running, then 6 x 20 s relaxed strides with full recovery. Builds speed without stress.")


def _quality_kind(phase, build_index, goal_name, week_in_phase):
    if phase == "base":
        return "strides" if week_in_phase < 2 else "tempo"
    if phase == "build":
        first = "tempo" if goal_name in ("Half marathon", "Marathon") else "intervals"
        other = "intervals" if first == "tempo" else "tempo"
        return first if build_index % 2 == 0 else other
    if phase == "peak":
        return "tempo" if goal_name in ("Half marathon", "Marathon") else "intervals"
    return "tempo"  # taper keeps a short sharpener


def generate_plan(goal, race_date, start_date, current_weekly_mi, vdot_value, days_per_week=4,
                  long_run_dow=6, goal_time_s=None):
    """Build a plan. goal is "5K"/"10K"/"Half marathon"/"Marathon" or a distance in metres."""
    if race_date <= start_date:
        raise ValueError("The race date must be after the start date.")
    days_per_week = max(3, min(6, days_per_week))
    goal_name, race_m, rules = _rules_for(goal)
    race_mi = race_m / MI
    paces = zones.training_paces(vdot_value)
    projected = zones.predict_time(vdot_value, race_m)
    race_time = goal_time_s or projected
    goal_pace = race_time / race_mi
    warnings = []

    first_monday = _monday(start_date)
    n_weeks = (_monday(race_date) - first_monday).days // 7 + 1
    if n_weeks < rules["min_weeks"]:
        warnings.append(f"Only {n_weeks} weeks to the race; {rules['min_weeks']} or more is recommended for this "
                        "distance, so the build is compressed. Treat the goal time as less certain.")
    if goal_time_s and goal_time_s < projected * 0.95:
        warnings.append(f"Your goal ({zones.fmt_time(goal_time_s)}) is more than 5% faster than your current fitness "
                        f"predicts ({zones.fmt_time(projected)}). Race-pace work uses the goal pace; easy and hard days "
                        "stay tied to your current fitness.")

    floor = _min_feasible_weekly(days_per_week)
    start_mi = max(current_weekly_mi, floor)
    if current_weekly_mi < floor:
        warnings.append(f"Your recent mileage ({current_weekly_mi:.0f} mi/week) is below what {days_per_week} runs a week "
                        f"needs, so week 1 starts at {floor:.0f} mi. Consider fewer days per week if that feels like too much.")

    weekly = _weekly_plan(n_weeks, rules, start_mi)
    pattern = PATTERNS[days_per_week]
    shift = long_run_dow - 6
    workouts, week_rows = [], []
    build_counter, phase_counter = 0, {}

    for idx, wk in enumerate(weekly):
        monday = first_monday + timedelta(days=7 * idx)
        phase = wk["phase"]
        W = wk["target"]
        in_phase = phase_counter.get(phase, 0)
        phase_counter[phase] = in_phase + 1
        is_race_week = monday <= race_date < monday + timedelta(days=7)
        progress = idx / max(1, n_weeks - 1)

        roles = [((dow + shift) % 7, role) for dow, role in pattern]
        q_mi = min(9.0, max(3.5, 0.22 * W))
        long_frac = rules["long_frac"] + 0.04 * max(0, 5 - days_per_week)  # fewer run days: bigger long-run share
        long_mi = min(rules["long_cap"], max(long_frac * W, 3.0))
        n_easy = sum(1 for _, r in roles if r == "easy")

        qkind = None
        if not wk["recovery"] and not is_race_week:
            qkind = _quality_kind(phase, build_counter, goal_name, in_phase)
            if phase != "taper":
                build_counter += 1
        if qkind is None:
            quality = None
            q_mi = 0
        else:
            quality = _quality(qkind, q_mi, paces, progress)
            q_mi = quality[1]
        long_mi = max(long_mi, q_mi + 0.5)
        rest = W - long_mi - q_mi
        slots_easy = n_easy + (1 if quality is None else 0)  # no quality: that day becomes easy
        easy_mi = max(2.0, rest / max(1, slots_easy))
        # easy days stay clearly shorter than the long run, and never exceed 7 mi; if that caps the week,
        # mileage plateaus rather than turning easy days into long ones
        easy_mi = max(2.0, min(easy_mi, long_mi * 0.65, 7.0))

        for dow, role in sorted(roles):
            day = monday + timedelta(days=dow)
            if day < start_date or day >= race_date - timedelta(days=1):
                continue
            if role == "long" and not is_race_week:
                seg = ""
                if phase in ("peak", "build") and goal_name in ("Half marathon", "Marathon") and not wk["recovery"]:
                    seg_mi = _half(min(long_mi * 0.3, 6))
                    if seg_mi >= 2:
                        long_pace = goal_pace
                        seg = f" Last {seg_mi:g} mi at goal pace ({zones.fmt_pace(long_pace)}/mi)."
                workouts.append(_workout(day, idx + 1, phase, "long", f"Long run {_half(long_mi):.1f} mi", _half(long_mi),
                                         paces["easy_fast"], paces["easy_slow"], (2, 2),
                                         f"Steady and easy, conversational the whole way.{seg}"))
            elif role == "quality" and quality is not None:
                title, miles, lo, hi, zr, desc = quality
                workouts.append(_workout(day, idx + 1, phase, qkind if qkind != "strides" else "strides", title,
                                         _half(miles), lo, hi, zr, desc))
            else:
                if is_race_week and role in ("long", "quality"):
                    miles, title, desc = _half(max(2.0, easy_mi)), "Easy + strides", "Easy running with 4 x 20 s strides to stay sharp."
                    kind = "strides"
                else:
                    miles, title, desc = _half(easy_mi), f"Easy {_half(easy_mi):.1f} mi", "Conversational pace. If you can't chat, slow down."
                    kind = "easy"
                workouts.append(_workout(day, idx + 1, phase, kind, title, miles, paces["easy_fast"], paces["easy_slow"], (2, 2), desc))

    workouts.append(_workout(race_date, n_weeks, "taper", "race", f"RACE DAY: {goal_name if goal_name != 'Race' else f'{race_mi:.1f} mi'}",
                             race_mi, goal_pace, goal_pace, (3, 5),
                             f"Goal {zones.fmt_time(race_time)} ({zones.fmt_pace(goal_pace)}/mi). Start a touch easier than goal pace for the first mile."))
    workouts.sort(key=lambda w: (w["date"], w["kind"] == "race"))

    for idx, wk in enumerate(weekly):
        items = [w for w in workouts if w["week"] == idx + 1]
        week_rows.append({
            "week": idx + 1, "start": (first_monday + timedelta(days=7 * idx)).isoformat(), "phase": wk["phase"],
            "recovery": wk["recovery"], "target_mi": round(wk["target"], 1),
            "planned_mi": round(sum(w["distance_mi"] for w in items), 1),
        })
    return {
        "goal": goal_name, "race_date": race_date.isoformat(), "start_date": start_date.isoformat(),
        "race_distance_m": race_m, "goal_time_s": race_time, "projected_time_s": projected,
        "vdot": vdot_value, "days_per_week": days_per_week,
        "weeks": week_rows, "workouts": workouts, "warnings": warnings,
    }
