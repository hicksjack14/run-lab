"""Turn the whole season of runs into honest findings: what is going well, what to fix, what works for him.

Approach: fit a small regression of running *efficiency* (speed per heartbeat) on date, effort, distance, time
of day, rest, shoes and hills, so each factor is judged while the others are held steady. A factor is only
reported when the data supports it (|t| >= 2); everything else is listed as "unclear" with its sample size.
Pure-Python (no numpy). Distances in miles, paces in seconds per mile.
"""
import math
import statistics
from collections import defaultdict
from datetime import date, timedelta

from analysis import fitness, zones
from analysis.zones import MI

FT = 3.28084
MIN_RUNS_FOR_PATTERNS = 12
MIN_RUNS_FOR_REGRESSION = 20


# ---------------------------------------------------------------- statistics helpers
def _invert(m):
    n = len(m)
    a = [row[:] + [1.0 if i == j else 0.0 for j in range(n)] for i, row in enumerate(m)]
    for col in range(n):
        piv = max(range(col, n), key=lambda r: abs(a[r][col]))
        if abs(a[piv][col]) < 1e-12:
            return None
        a[col], a[piv] = a[piv], a[col]
        p = a[col][col]
        a[col] = [v / p for v in a[col]]
        for r in range(n):
            if r != col:
                f = a[r][col]
                a[r] = [v - f * w for v, w in zip(a[r], a[col])]
    return [row[n:] for row in a]


def ols(X, y):
    """Ordinary least squares. X rows include the intercept column. Returns beta, t-stats, n or None if singular."""
    n, k = len(X), len(X[0])
    if n <= k:
        return None
    xtx = [[sum(X[r][i] * X[r][j] for r in range(n)) for j in range(k)] for i in range(k)]
    xty = [sum(X[r][i] * y[r] for r in range(n)) for i in range(k)]
    inv = _invert(xtx)
    if inv is None:
        return None
    beta = [sum(inv[i][j] * xty[j] for j in range(k)) for i in range(k)]
    resid = [y[r] - sum(X[r][i] * beta[i] for i in range(k)) for r in range(n)]
    s2 = sum(e * e for e in resid) / (n - k)
    se = [math.sqrt(max(s2 * inv[i][i], 0.0)) for i in range(k)]
    return {"beta": beta, "se": se, "t": [b / s if s > 1e-12 else 0.0 for b, s in zip(beta, se)], "n": n}


def _monday(d):
    return d - timedelta(days=d.weekday())


def _fmt_day(d):
    return f"{d:%b} {d.day}"


def _confidence(t, n):
    t = abs(t)
    return "high" if t >= 3 and n >= 40 else "medium" if t >= 2 else "low"


def _finding(fid, kind, title, body, stat, confidence, n, runs=()):
    return {"id": fid, "kind": kind, "title": title, "body": body, "stat": stat,
            "confidence": confidence, "n": n, "runs": list(runs)[:8]}


# ---------------------------------------------------------------- per-run metrics
def _stream_metrics(samples, max_hr):
    """samples: rows of (t_s, hr, speed_mps, distance_m, moving). Returns fade, drift, zone seconds."""
    pts, prev_t = [], None
    for t, hr, speed, dist, moving in samples:
        dt = 0 if prev_t is None else min(t - prev_t, 15)
        prev_t = t
        ok = moving != 0 and speed is not None and speed >= 0.8 and dist is not None
        pts.append((dt if ok else 0, hr, speed, dist))
    valid = [p for p in pts if p[0] > 0]
    out = {"fade": None, "drift": None, "zone_secs": [0.0] * 5}
    if len(valid) < 20:
        return out
    for dt, hr, _, _ in valid:
        if hr:
            out["zone_secs"][zones.zone_for_hr(hr, max_hr) - 1] += dt
    half_d = max(p[3] for p in valid) / 2
    halves = ([p for p in valid if p[3] < half_d], [p for p in valid if p[3] >= half_d])
    if all(len(h) >= 8 for h in halves):
        def stats(h):
            secs = sum(p[0] for p in h)
            dist = max(p[3] for p in h) - min(p[3] for p in h)
            hrs = [(p[0], p[1]) for p in h if p[1]]
            hr = sum(w * v for w, v in hrs) / sum(w for w, _ in hrs) if hrs else None
            return secs, dist, hr
        (s1, d1, h1), (s2, d2, h2) = stats(halves[0]), stats(halves[1])
        if d1 > 0 and d2 > 0:
            out["fade"] = (s2 / d2) / (s1 / d1) - 1  # >0 means the second half was slower
            if h1 and h2:
                out["drift"] = ((d1 / s1) / h1) / ((d2 / s2) / h2) - 1  # >0 means efficiency fell
    return out


def load_runs(conn, max_hr):
    rows = conn.execute(
        "SELECT strava_id, name, start_local, distance_m, moving_s, avg_hr, max_hr, avg_cadence_spm, gear_id, elevation_gain_m "
        "FROM runs WHERE distance_m > 0 AND moving_s > 0 ORDER BY start_local").fetchall()
    streams = defaultdict(list)
    for r in conn.execute("SELECT strava_id, t_s, hr, speed_mps, distance_m, moving FROM run_streams ORDER BY strava_id, t_s"):
        streams[r[0]].append((r[1], r[2], r[3], r[4], r[5]))
    days = {r["start_local"][:10] for r in rows}
    runs = []
    for r in rows:
        miles = r["distance_m"] / MI
        d = date.fromisoformat(r["start_local"][:10])
        m = _stream_metrics(streams[r["strava_id"]], max_hr) if streams.get(r["strava_id"]) and max_hr else \
            {"fade": None, "drift": None, "zone_secs": [0.0] * 5}
        ef = (r["distance_m"] / (r["moving_s"] / 60)) / r["avg_hr"] if r["avg_hr"] else None
        runs.append({
            "id": r["strava_id"], "name": r["name"], "date": d, "start_hour": int(r["start_local"][11:13]),
            "dist_mi": miles, "moving_s": r["moving_s"], "pace": r["moving_s"] / miles, "avg_hr": r["avg_hr"],
            "max_hr_run": r["max_hr"], "ef": ef, "hr_frac": (r["avg_hr"] / max_hr) if r["avg_hr"] and max_hr else None,
            "gear": r["gear_id"], "elev_per_mi": (r["elevation_gain_m"] or 0) * FT / miles,
            "cadence": r["avg_cadence_spm"], "fade": m["fade"], "drift": m["drift"], "zone_secs": m["zone_secs"],
            "prev_day_run": (d - timedelta(days=1)).isoformat() in days,
        })
    return runs


# ---------------------------------------------------------------- regression
def _design(runs):
    first = min(r["date"] for r in runs)
    gears = defaultdict(int)
    for r in runs:
        if r["gear"]:
            gears[r["gear"]] += 1
    top = sorted(gears, key=gears.get, reverse=True)[:2]
    second = top[1] if len(top) == 2 and gears[top[0]] >= 5 and gears[top[1]] >= 5 else None
    cols = {
        "months": [(r["date"] - first).days / 30 for r in runs],
        "effort": [(r["hr_frac"] or 0) * 10 for r in runs],        # per 10 points of max HR
        "distance": [r["dist_mi"] for r in runs],
        "evening": [1.0 if r["start_hour"] >= 16 else 0.0 for r in runs],
        "back_to_back": [1.0 if r["prev_day_run"] else 0.0 for r in runs],
        "hills": [r["elev_per_mi"] / 100 for r in runs],
    }
    if second:
        cols["shoe"] = [1.0 if r["gear"] == second else 0.0 for r in runs]
    cols = {k: v for k, v in cols.items() if max(v) - min(v) > 1e-9}
    return cols, top, second


def _regress(runs):
    cols, gears, second = _design(runs)
    names = list(cols)
    X = [[1.0] + [cols[n][i] for n in names] for i in range(len(runs))]
    fit = ols(X, [r["ef"] for r in runs])
    if not fit:
        return None
    return {"coef": dict(zip(names, fit["beta"][1:])), "t": dict(zip(names, fit["t"][1:])), "n": fit["n"],
            "mean_ef": statistics.mean(r["ef"] for r in runs), "mean_pace": statistics.mean(r["pace"] for r in runs),
            "mean_hr": statistics.mean(r["avg_hr"] for r in runs), "gears": gears if second else None, "second_gear": second}


def _pace_gain(delta, mean_pace):
    """Seconds per mile gained at the same heart rate when efficiency rises by fraction delta."""
    return mean_pace * delta / (1 + delta)


def _hr_cost(delta, mean_hr):
    """Extra heartbeats per minute at the same speed when efficiency changes by fraction delta (negative = worse)."""
    return mean_hr * (-delta) / (1 + delta)


# ---------------------------------------------------------------- findings
def _consistency(runs, today):
    this_monday = _monday(today)
    weeks = [this_monday - timedelta(days=7 * i) for i in range(8, 0, -1)]
    counts = {w: 0 for w in weeks}
    for r in runs:
        w = _monday(r["date"])
        if w in counts:
            counts[w] += 1
    vals = [counts[w] for w in weeks]
    avg = statistics.mean(vals)
    streak = 0
    for v in reversed(vals):
        if v >= 3:
            streak += 1
        else:
            break
    empty = sum(1 for v in vals if v == 0)
    if avg >= 2.5:
        title = f"You are running {avg:.1f} times a week" + (f", {streak} weeks in a row at 3 or more" if streak >= 3 else "")
        body = (f"Over the last 8 full weeks you averaged {avg:.1f} runs a week. Consistency is the thing that builds fitness "
                "fastest, and you have it.")
        return _finding("consistency", "good", title, body, {"label": "runs per week", "value": f"{avg:.1f}"}, "high", sum(vals))
    body = (f"Over the last 8 full weeks you averaged {avg:.1f} runs a week with {empty} week{'s' if empty != 1 else ''} "
            "of no running. Three easy runs a week beats one big one: this is the biggest lever you have right now.")
    return _finding("consistency", "improve", f"Consistency is the biggest lever: {avg:.1f} runs a week lately", body,
                    {"label": "runs per week", "value": f"{avg:.1f}"}, "high", sum(vals))


def _ramp(runs, today):
    this_monday = _monday(today)
    weeks = [this_monday - timedelta(days=7 * i) for i in range(12, 0, -1)]
    miles = {w: 0.0 for w in weeks}
    for r in runs:
        w = _monday(r["date"])
        if w in miles:
            miles[w] += r["dist_mi"]
    spikes = []
    for prev, cur in zip(weeks, weeks[1:]):
        if miles[prev] >= 5 and miles[cur] > miles[prev] * 1.3:
            spikes.append((cur, miles[prev], miles[cur]))
    if spikes:
        s = max(spikes, key=lambda x: x[2] / x[1])
        more = f" ({len(spikes)} weeks like that in the last 12)" if len(spikes) > 1 else ""
        body = (f"The week of {_fmt_day(s[0])} jumped from {s[1]:.0f} to {s[2]:.0f} miles, +{(s[2] / s[1] - 1) * 100:.0f}%{more}. "
                "Jumps over about 10 to 30% are where overuse injuries tend to show up. Build up more gradually, with a lighter week every fourth.")
        return _finding("ramp", "improve", f"Mileage spiked {(s[2] / s[1] - 1) * 100:.0f}% in one week", body,
                        {"label": "biggest jump", "value": f"+{(s[2] / s[1] - 1) * 100:.0f}%"}, "high", len(weeks))
    active = [w for w in weeks if miles[w] > 0]
    if len(active) >= 4:
        return _finding("ramp", "good", "You are adding mileage sensibly",
                        "No week in the last 12 jumped more than 30% over the one before. That is how you stack up volume without breaking down.",
                        {"label": "weeks checked", "value": str(len(weeks))}, "high", len(weeks))
    return None


def _intensity(runs, max_hr, today):
    cutoff = today - timedelta(days=56)
    recent = [r for r in runs if r["date"] >= cutoff] or runs
    totals = [sum(r["zone_secs"][i] for r in recent) for i in range(5)]
    total = sum(totals)
    if total < 3600:
        return None
    easy, gray, hard = (totals[0] + totals[1]) / total, totals[2] / total, (totals[3] + totals[4]) / total
    z = zones.hr_zones(max_hr)
    n = len(recent)
    if gray >= 0.40:
        return _finding("intensity", "improve", f"{gray * 100:.0f}% of your running is in the gray zone",
                        f"Zone 3 ({z[2]['lo']}-{z[2]['hi']} bpm, assuming a max HR of {max_hr}) is too hard to recover from and too easy to sharpen you. "
                        f"Only {easy * 100:.0f}% of your time is truly easy. Slow the easy days down so the hard days can be hard.",
                        {"label": "easy time", "value": f"{easy * 100:.0f}%"}, "medium", n)
    if easy >= 0.70:
        return _finding("intensity", "good", f"{easy * 100:.0f}% of your running is easy, the way it should be",
                        f"About {easy * 100:.0f}% of your time sits in zones 1 and 2 (under {z[2]['lo']} bpm) with {hard * 100:.0f}% hard. "
                        "That polarized mix builds endurance and still leaves room for quality.",
                        {"label": "easy time", "value": f"{easy * 100:.0f}%"}, "medium", n)
    return None


def _pacing(runs):
    rs = [r for r in runs if r["fade"] is not None and r["dist_mi"] >= 3]
    if len(rs) < 8:
        return None
    fades = [r["fade"] for r in rs]
    mean, pos = statistics.mean(fades), sum(1 for f in fades if f > 0.01) / len(rs)
    neg = sum(1 for f in fades if f < -0.01) / len(rs)
    worst = [r["id"] for r in sorted(rs, key=lambda r: -r["fade"])]
    if mean >= 0.03 and pos >= 0.6:
        return _finding("pacing", "improve", f"You start too fast: {mean * 100:.1f}% slower in the second half",
                        f"On {pos * 100:.0f}% of runs of 3+ miles your second half was slower than your first, by {mean * 100:.1f}% on average. "
                        "Start the first mile 15 to 20 seconds slower than feels natural and the back half gets easier.",
                        {"label": "avg fade", "value": f"{mean * 100:.1f}%"}, "medium", len(rs), worst)
    if neg >= 0.45 or mean <= 0.01:
        return _finding("pacing", "good", "You pace runs well",
                        f"You ran the second half as fast or faster on {max(neg, 1 - pos) * 100:.0f}% of runs of 3+ miles. Controlled starts are a real skill.",
                        {"label": "avg fade", "value": f"{mean * 100:+.1f}%"}, "medium", len(rs))
    return None


def _drift(runs):
    rs = [r for r in runs if r["drift"] is not None and r["moving_s"] >= 3000]
    if len(rs) < 4:
        return None
    med = statistics.median(r["drift"] for r in rs)
    if med >= 0.05:
        return _finding("drift", "improve", f"Long runs lose {med * 100:.0f}% efficiency by the second half",
                        f"On runs over 50 minutes your heart rate climbs about {med * 100:.0f}% relative to your speed from the first half to the second "
                        "(cardiac drift). Under 5% means a solid aerobic base. Slow the start, drink, and take fuel on runs past an hour.",
                        {"label": "median drift", "value": f"{med * 100:.1f}%"}, "medium", len(rs), [r["id"] for r in rs])
    return _finding("drift", "good", "Your aerobic base holds up on long runs",
                    f"Past 50 minutes your efficiency dropped only {med * 100:.1f}% between halves (under 5% is solid).",
                    {"label": "median drift", "value": f"{med * 100:.1f}%"}, "medium", len(rs))


def _cadence(runs):
    rs = [r for r in runs if r["cadence"]]
    if len(rs) < 12:
        return None
    fit = ols([[1.0, (r["date"] - rs[0]["date"]).days / 30] for r in rs], [r["cadence"] for r in rs])
    if not fit or abs(fit["t"][1]) < 2:
        return None
    months = (rs[-1]["date"] - rs[0]["date"]).days / 30
    total = fit["beta"][1] * months
    if total >= 3:
        return _finding("cadence", "good", f"Your cadence is up {total:.0f} steps a minute",
                        f"Trend line from about {fit['beta'][0]:.0f} to {fit['beta'][0] + total:.0f} spm over the season. Many runners settle "
                        "between 165 and 180; quicker, lighter steps usually go with better efficiency.",
                        {"label": "cadence change", "value": f"+{total:.0f} spm"}, _confidence(fit["t"][1], len(rs)), len(rs))
    return None


def _regression_findings(runs, gear_names=None):
    gear_names = gear_names or {}
    label = lambda gid: gear_names.get(gid) or f"shoes ...{str(gid)[-4:]}"
    eligible = [r for r in runs if r["ef"] and r["moving_s"] >= 1200 and r["hr_frac"]]
    findings, unclear = [], []
    if len(eligible) < MIN_RUNS_FOR_REGRESSION:
        return findings, unclear, len(eligible)
    reg = _regress(eligible)
    if not reg:
        return findings, unclear, len(eligible)
    coef, t, n = reg["coef"], reg["t"], reg["n"]
    mef, mp, mhr = reg["mean_ef"], reg["mean_pace"], reg["mean_hr"]
    delta = lambda name, scale=1.0: coef[name] * scale / mef

    if "months" in coef:
        span = (eligible[-1]["date"] - eligible[0]["date"]).days / 30
        d_total = delta("months", span)
        if abs(t["months"]) >= 2 and d_total > 0:
            gain = _pace_gain(d_total, mp)
            findings.append(_finding(
                "fitness-trend", "good", f"Your engine is growing: about {gain:.0f} sec/mi faster at the same heart rate",
                f"Holding effort, distance, time of day and rest steady, your speed per heartbeat has risen about {d_total * 100:.0f}% since your first run "
                f"({span:.1f} months). The same effort now buys you roughly {gain:.0f} seconds a mile.",
                {"label": "efficiency gain", "value": f"+{d_total * 100:.0f}%"}, _confidence(t["months"], n), n))
        elif abs(t["months"]) >= 2 and d_total < 0:
            findings.append(_finding(
                "fitness-trend", "improve", "Your efficiency has slipped",
                f"At the same effort your speed per heartbeat has fallen about {abs(d_total) * 100:.0f}% since you started. Fatigue, heat, or too little easy running are the usual causes.",
                {"label": "efficiency change", "value": f"{d_total * 100:.0f}%"}, _confidence(t["months"], n), n))
        else:
            unclear.append({"id": "fitness-trend", "text": f"No clear fitness trend in your efficiency yet ({n} runs)."})

    if "evening" in coef:
        ev = [r for r in eligible if r["start_hour"] >= 16]
        other = len(eligible) - len(ev)
        if min(len(ev), other) < 5:
            unclear.append({"id": "time-of-day", "text": f"Not enough runs in both time slots to compare ({len(ev)} evening, {other} daytime)."})
        else:
            d = delta("evening")
            if abs(t["evening"]) >= 2:
                good = d > 0
                gain = abs(_pace_gain(d, mp))
                title = ("Evening runs are your best runs" if good else "Daytime runs are your best runs")
                body = (f"At the same effort, you are about {abs(d) * 100:.0f}% more efficient {'in the evening' if good else 'earlier in the day'} "
                        f"(roughly {gain:.0f} sec/mi at the same heart rate; {len(ev)} evening vs {other} daytime runs). "
                        f"Put {'your key workouts and long runs in the evening' if good else 'your key workouts earlier'} when you can.")
                findings.append(_finding("time-of-day", "works", title, body,
                                         {"label": "evening vs day", "value": f"{d * 100:+.0f}%"}, _confidence(t["evening"], n), n))
            else:
                unclear.append({"id": "time-of-day", "text": f"No clear difference between evening and daytime runs yet ({len(ev)} vs {other})."})

    if "back_to_back" in coef:
        b2b = sum(1 for r in eligible if r["prev_day_run"])
        if min(b2b, len(eligible) - b2b) < 5:
            unclear.append({"id": "back-to-back", "text": "Not enough rest-day vs back-to-back runs to compare yet."})
        else:
            d = delta("back_to_back")
            if abs(t["back_to_back"]) >= 2:
                cost = abs(_hr_cost(d, mhr))
                if d < 0:
                    findings.append(_finding(
                        "back-to-back", "doesnt", "Running the day after a run costs you",
                        f"On days after a run your heart rate runs about {cost:.0f} bpm higher for the same speed ({b2b} back-to-back runs vs {len(eligible) - b2b} after rest). "
                        "Your legs are telling you they want an easy day or a day off. Make the day after a hard run truly easy.",
                        {"label": "heart-rate cost", "value": f"+{cost:.0f} bpm"}, _confidence(t["back_to_back"], n), n))
                else:
                    findings.append(_finding(
                        "back-to-back", "works", "You run well on consecutive days",
                        f"Back-to-back runs are as good or better than after rest for you (about {d * 100:.0f}% more efficient). You recover quickly.",
                        {"label": "after a run", "value": f"{d * 100:+.0f}%"}, _confidence(t["back_to_back"], n), n))
            else:
                unclear.append({"id": "back-to-back", "text": f"No clear difference between back-to-back days and rested days yet ({b2b} vs {len(eligible) - b2b})."})

    if "shoe" in coef and reg["gears"]:
        a, b = reg["gears"]
        d = delta("shoe")
        if abs(t["shoe"]) >= 2 and abs(d) >= 0.015:
            better, worse = (label(b), label(a)) if d > 0 else (label(a), label(b))
            findings.append(_finding(
                "shoes", "works", f"Your {better} are the more efficient pair",
                f"At the same effort you are about {abs(d) * 100:.0f}% more efficient in {better} than in {worse}. Worth reaching for them on key days "
                "(check mileage on the other pair too).",
                {"label": "shoe difference", "value": f"{abs(d) * 100:.0f}%"}, _confidence(t["shoe"], n), n))
        else:
            unclear.append({"id": "shoes", "text": f"No clear difference between your two main pairs of shoes yet."})

    if "distance" in coef and t["distance"] <= -2 and abs(coef["distance"] / mef) >= 0.008:  # small effects aren't worth a headline
        per_mile = abs(coef["distance"] / mef)
        findings.append(_finding(
            "distance", "improve", "Efficiency fades the farther you go",
            f"Each extra mile costs about {per_mile * 100:.1f}% efficiency on top of normal drift. That is typical while you are building endurance; "
            "a steady long-run progression and slower starts are the fix.",
            {"label": "per extra mile", "value": f"-{per_mile * 100:.1f}%"}, _confidence(t["distance"], n), n))

    if "hills" in coef and abs(t["hills"]) >= 2:
        d = delta("hills", 1.0)
        if d < 0:
            findings.append(_finding(
                "hills", "doesnt", "Hilly routes cost you more than they pay back",
                f"Every extra 100 ft of climbing per mile costs about {abs(d) * 100:.0f}% efficiency. Run hills on purpose (hill repeats), "
                "and keep the easy days on flatter routes so they stay easy.",
                {"label": "per 100 ft/mi", "value": f"{d * 100:.0f}%"}, _confidence(t["hills"], n), n))
    return findings, unclear, n


def build_findings(runs, today, max_hr, gear_names=None):
    if len(runs) < MIN_RUNS_FOR_PATTERNS:
        return {"status": f"Not enough runs yet to find patterns ({len(runs)} so far, need {MIN_RUNS_FOR_PATTERNS}). "
                          "Sync more of your history and this page fills in.", "findings": [], "unclear": []}
    findings = [f for f in (_consistency(runs, today), _ramp(runs, today), _intensity(runs, max_hr, today),
                            _pacing(runs), _drift(runs), _cadence(runs)) if f]
    reg_findings, unclear, n_reg = _regression_findings(runs, gear_names or {})
    findings += reg_findings
    order = {"works": 0, "good": 1, "improve": 2, "doesnt": 3}
    findings.sort(key=lambda f: (order[f["kind"]], {"high": 0, "medium": 1, "low": 2}[f["confidence"]]))
    status = f"Based on {len(runs)} runs ({n_reg} long enough for the efficiency analysis)."
    return {"status": status, "findings": findings, "unclear": unclear}


# ---------------------------------------------------------------- charts + summary
def _routes(conn, runs, limit=150, points=70):
    out = []
    for r in runs[-limit:]:
        rows = conn.execute("SELECT lat, lng FROM run_streams WHERE strava_id = ? AND lat IS NOT NULL ORDER BY t_s", (r["id"],)).fetchall()
        if len(rows) < 10:
            continue
        step = max(1, len(rows) // points)
        pts = [[round(x[0], 5), round(x[1], 5)] for x in rows[::step]]
        out.append({"id": r["id"], "date": r["date"].isoformat(), "miles": round(r["dist_mi"], 2), "pts": pts})
    return out


def _series(conn, runs, today, max_hr):
    first_monday = _monday(runs[0]["date"])
    weekly, w = [], first_monday
    by_week = defaultdict(lambda: [0.0, 0])
    for r in runs:
        k = _monday(r["date"])
        by_week[k][0] += r["dist_mi"]
        by_week[k][1] += 1
    while w <= _monday(today):
        weekly.append({"start": w.isoformat(), "miles": round(by_week[w][0], 2), "runs": by_week[w][1]})
        w += timedelta(days=7)
    hours = [{"hour": h, "runs": 0, "miles": 0.0, "ef": None, "_efs": []} for h in range(24)]
    for r in runs:
        h = hours[r["start_hour"]]
        h["runs"] += 1
        h["miles"] += r["dist_mi"]
        if r["ef"]:
            h["_efs"].append(r["ef"])
    for h in hours:
        efs = h.pop("_efs")
        h["ef"] = round(statistics.mean(efs), 4) if efs else None
        h["miles"] = round(h["miles"], 1)
    buckets = [("0-2", 0, 2), ("2-4", 2, 4), ("4-6", 4, 6), ("6-8", 6, 8), ("8+", 8, 99)]
    return {
        "weekly": weekly,
        "runs": [{"id": r["id"], "name": r["name"], "date": r["date"].isoformat(), "miles": round(r["dist_mi"], 2),
                  "pace": round(r["pace"]), "hr": round(r["avg_hr"]) if r["avg_hr"] else None,
                  "ef": round(r["ef"], 4) if r["ef"] else None, "hour": r["start_hour"], "cadence": round(r["cadence"]) if r["cadence"] else None}
                 for r in runs],
        "hours": hours,
        "calendar": {r["date"].isoformat(): 0 for r in []} | _calendar(runs),
        "zones": {"seconds": [round(sum(r["zone_secs"][i] for r in runs)) for i in range(5)], "bands": zones.hr_zones(max_hr) if max_hr else None},
        "distance_hist": [{"label": lab, "runs": sum(1 for r in runs if lo <= r["dist_mi"] < hi)} for lab, lo, hi in buckets],
        "routes": _routes(conn, runs),
    }


def _calendar(runs):
    cal = defaultdict(float)
    for r in runs:
        cal[r["date"].isoformat()] += r["dist_mi"]
    return {k: round(v, 2) for k, v in cal.items()}


def _summary(runs, today):
    total_s = sum(r["moving_s"] for r in runs)
    miles = sum(r["dist_mi"] for r in runs)
    first, last = runs[:max(3, len(runs) // 6)], runs[-max(3, len(runs) // 6):]
    pace = lambda rs: sum(r["moving_s"] for r in rs) / sum(r["dist_mi"] for r in rs)
    weeks_run = {_monday(r["date"]) for r in runs}
    streak, w = 0, _monday(today) - timedelta(days=7)
    if _monday(today) in weeks_run:
        w = _monday(today)
    while w in weeks_run:
        streak += 1
        w -= timedelta(days=7)
    return {
        "runs": len(runs), "miles": round(miles, 1), "hours": round(total_s / 3600, 1),
        "avg_pace": round(total_s / miles), "first_pace": round(pace(first)), "recent_pace": round(pace(last)),
        "longest_mi": round(max(r["dist_mi"] for r in runs), 1), "since": runs[0]["date"].isoformat(),
        "active_streak_weeks": streak,
        "avg_hr": round(statistics.mean(r["avg_hr"] for r in runs if r["avg_hr"])) if any(r["avg_hr"] for r in runs) else None,
    }


def analyze(conn, today=None):
    today = today or date.today()
    gear_names = fitness.get_settings(conn).get("gear_names", {})
    snap = fitness.snapshot(conn, today)
    max_hr = snap["max_hr"]
    runs = load_runs(conn, max_hr)
    if not runs:
        return {"summary": None, "series": None, "findings": [], "unclear": [], "status": "No runs yet.", "max_hr": max_hr}
    out = build_findings(runs, today, max_hr or 195, gear_names)
    return {"summary": _summary(runs, today), "series": _series(conn, runs, today, max_hr), "max_hr": max_hr, **out}
