"""Generate a clearly-fake demo database (data/demo.db) so the app can be built and tried before real
Strava data is synced. Deterministic (seeded). Runs go through the real importer.

Planted patterns (so the insights engine has something it should find):
  - fitness improves steadily (same speed costs fewer heartbeats over time)
  - evening runs are a little more efficient than morning runs
  - running the day after a run (no rest) costs ~4 bpm
  - one pair of shoes is slightly less efficient
  - long runs drift upward in heart rate; some easy days are run too fast
Run:  .venv/bin/python -m tools.make_demo_data
"""
import json
import math
import random
import sys
from datetime import date, datetime, timedelta
from pathlib import Path

import db
from ingest.strava_import import import_dump

ROOT = Path(__file__).resolve().parent.parent
DEMO_DB = ROOT / "data" / "demo.db"
REAL_DUMPS = ROOT / "data" / "strava-dumps"
MI = 1609.344
MAX_HR, REST_HR = 192, 58


def template_route():
    """A real-looking loop to reuse. Prefer a locally synced run's route; otherwise a wiggly circle."""
    for p in sorted(REAL_DUMPS.glob("*.json")):
        loc = json.loads(p.read_text()).get("streams", {}).get("location")
        if loc and len(loc) > 50:
            return [tuple(x) for x in loc]
    return [(43.040 + 0.012 * math.sin(a) + 0.002 * math.sin(5 * a), -76.130 + 0.016 * math.cos(a) + 0.002 * math.cos(4 * a))
            for a in (i * 2 * math.pi / 200 for i in range(200))]


def _meters(a, b):
    dy = (b[0] - a[0]) * 111320
    dx = (b[1] - a[1]) * 111320 * math.cos(math.radians(a[0]))
    return math.hypot(dx, dy)


class Route:
    def __init__(self, pts, rng):
        self.pts = list(pts) + [pts[0]]
        self.cum = [0.0]
        for a, b in zip(self.pts, self.pts[1:]):
            self.cum.append(self.cum[-1] + _meters(a, b))
        self.length = self.cum[-1]
        self.shift = (rng.uniform(-0.0006, 0.0006), rng.uniform(-0.0006, 0.0006))
        self.offset = rng.uniform(0, self.length)
        self.reverse = rng.random() < 0.4

    def at(self, s):
        s = (-s if self.reverse else s) + self.offset
        s %= self.length
        lo, hi = 0, len(self.cum) - 1
        while hi - lo > 1:
            mid = (lo + hi) // 2
            if self.cum[mid] <= s:
                lo = mid
            else:
                hi = mid
        seg = (self.cum[hi] - self.cum[lo]) or 1
        f = (s - self.cum[lo]) / seg
        a, b = self.pts[lo], self.pts[hi]
        return (a[0] + (b[0] - a[0]) * f + self.shift[0], a[1] + (b[1] - a[1]) * f + self.shift[1])


def best_effort(dist, t, target):
    """Fastest time to cover `target` metres inside the (monotonic) dist/time arrays."""
    best, j = None, 0
    for i in range(len(dist)):
        while j < len(dist) - 1 and dist[j] - dist[i] < target:
            j += 1
        if dist[j] - dist[i] >= target:
            span = t[j] - t[i]
            if best is None or span < best:
                best = span
    return best


def make_run(rid, day, start_hour, kind, dist_m, progress, prev_day_run, shoe, rng, route_pts):
    thr_speed = 2.95 + 0.38 * progress  # threshold speed grows with fitness (m/s)
    kind_mult = {"easy": 0.84, "long": 0.80, "tempo": 0.99, "short": 0.90, "fast_easy": 0.92}[kind]
    v_goal = thr_speed * kind_mult * rng.uniform(0.97, 1.03)
    route = Route(route_pts, rng)
    evening = start_hour >= 16
    efficiency_shift = (-3.0 if evening else 0.0) + (4.0 if prev_day_run else 0.0) + (2.5 if shoe == "g_pegasus" else 0.0)
    t, covered, ar = 0.0, 0.0, 0.0
    hr_state = None
    samples = []
    stop_left = 0
    step = 3
    while covered < dist_m:
        ar = 0.9 * ar + rng.gauss(0, 0.05)
        moving = True
        if stop_left > 0:
            stop_left -= step
            v = 0.0
            moving = False
        else:
            if rng.random() < 0.0035:
                stop_left = rng.randint(6, 40)
            v = max(1.4, v_goal * (1 + ar))
        warm = min(1.0, 0.82 + 0.18 * (t / 420))  # slower for the first 7 minutes
        v *= warm if moving else 1
        covered += v * step
        minutes = t / 60
        ratio = v / thr_speed if moving else 0.0
        frac = 0.73 + 1.2 * (min(1.15, max(0.5, ratio)) - 0.85) if moving else 0.55
        frac += 0.06 * (minutes / 60) + (0.0 if minutes > 4 else -0.07 * (1 - minutes / 4))
        target = REST_HR + (MAX_HR - REST_HR) * min(1.0, max(0.3, frac)) + efficiency_shift
        hr_state = (REST_HR + 35) if hr_state is None else hr_state + (target - hr_state) * (step / 45)
        hr = hr_state + rng.gauss(0, 0.7)
        cad = 0 if not moving else max(70, 82 + 5.5 * (v - 2.6) - 0.6 * (shoe == "g_pegasus") + rng.gauss(0, 1.3))
        lat, lng = route.at(covered)
        alt = 150 + 18 * math.sin(covered / 700) + 8 * math.sin(covered / 230)
        samples.append((t, hr, v, cad, covered, moving, lat, lng, alt))
        t += step
    # downsample to at most ~900 points
    k = max(1, math.ceil(len(samples) / 900))
    samples = samples[::k]
    times = [int(s[0]) for s in samples]
    dist = [round(s[4], 1) for s in samples]
    elapsed = times[-1]
    moving_s = int(sum(step * k for s in samples if s[5]))
    laps = []
    by_mile = {}
    for smp, d in zip(samples, dist):
        by_mile.setdefault(int(d // MI), []).append(smp)
    for mile in sorted(by_mile):
        seg = by_mile[mile]
        last = mile == max(by_mile)
        laps.append({"distance": (dist[-1] - mile * MI) if last else MI,
                     "moving_time": int(sum(step * k for s in seg if s[5])),
                     "avg_hr": sum(s[1] for s in seg) / len(seg), "max_hr": max(s[1] for s in seg)})
    hrs = [s[1] for s in samples]
    efforts = []
    for name, target in (("1k", 1000), ("1 mile", MI), ("5k", 5000), ("10k", 10000)):
        if dist_m >= target:
            be = best_effort(dist, times, target)
            if be:
                efforts.append({"type_value": {"1k": "Fastest1k", "1 mile": "FastestMile", "5k": "Fastest5k", "10k": "Fastest10k"}[name], "value": int(be)})
    local = datetime(day.year, day.month, day.day, start_hour, rng.randint(0, 59), rng.randint(0, 59))
    part = "Morning" if start_hour < 11 else "Lunch" if start_hour < 15 else "Evening"
    names = {"easy": [f"{part} run", f"{part} run", "Easy run", "Recovery jog"], "long": ["Long run", "Sunday long"],
             "tempo": ["Tempo", "Threshold day"], "short": ["Quick one", "Shakeout"], "fast_easy": [f"{part} run"]}
    return {
        "activity": {"id": str(rid), "name": rng.choice(names[kind]), "sport_type": "Run", "start_local": local.isoformat(),
                     "gear_id": shoe, "timezone": "America/New_York",
                     "summary": {"distance": round(dist[-1], 1), "moving_time": moving_s, "elapsed_time": elapsed,
                                 "elevation_gain": round(sum(max(0, b[8] - a[8]) for a, b in zip(samples, samples[1:])), 1),
                                 "avg_cadence": round(sum(s[3] for s in samples if s[5]) / max(1, sum(1 for s in samples if s[5])), 2),
                                 "relative_effort": int(sum(max(0, h - 120) for h in hrs) / len(hrs) * elapsed / 600)}},
        "streams": {"time": times, "heart_rate": [round(h) for h in hrs], "velocity_smooth": [round(s[2], 3) for s in samples],
                    "cadence": [round(s[3]) for s in samples], "distance": dist, "moving": [s[5] for s in samples],
                    "location": [[round(s[6], 6), round(s[7], 6)] for s in samples], "altitude": [round(s[8], 1) for s in samples]},
        "performance": {"average_heartrate": sum(hrs) / len(hrs), "max_heartrate": round(max(hrs)), "laps": laps, "best_efforts": efforts},
    }


def schedule(start, end, rng):
    """(date, kind, miles, hour) tuples with a believable weekly shape that grows over time."""
    out, d = [], start
    total_days = (end - start).days
    gap = (date(2026, 7, 13), date(2026, 7, 26))  # a two-week injury/travel break
    prev = None
    while d <= end:
        progress = (d - start).days / total_days
        dow = d.weekday()
        in_gap = gap[0] <= d <= gap[1]
        runs_per_week = 3 if progress < 0.3 else 4 if progress < 0.75 else 4
        pattern = {3: {1, 3, 6}, 4: {1, 3, 5, 6}}[runs_per_week]
        extra = 0.12 if progress > 0.5 else 0.05  # sometimes an extra Monday run
        if not in_gap and ((dow in pattern and rng.random() > 0.12) or (dow == 0 and rng.random() < extra) or (dow == 4 and rng.random() < 0.06)):
            if dow == 6:
                kind, miles = "long", 4.5 + 6.0 * progress + rng.uniform(-0.6, 0.6)
            elif dow == 1 and progress > 0.2 and rng.random() < 0.65:
                kind, miles = "tempo", 3.0 + 2.2 * progress + rng.uniform(-0.3, 0.3)
            elif rng.random() < 0.18:
                kind, miles = "fast_easy", 3.0 + 2.0 * progress + rng.uniform(-0.5, 0.5)  # easy day run too fast
            elif rng.random() < 0.15:
                kind, miles = "short", 1.5 + rng.uniform(0, 1.2)
            else:
                kind, miles = "easy", 2.8 + 2.4 * progress + rng.uniform(-0.6, 0.8)
            hour = rng.choices([7, 8, 9, 12, 13, 17, 18, 19], weights=[6, 6, 3, 3, 2, 10, 10, 5])[0]
            out.append((d, kind, max(1.2, miles), hour))
        d += timedelta(days=1)
    return out


def build(path=DEMO_DB, seed=2026):
    rng = random.Random(seed)
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    conn = db.connect(path)
    route_pts = template_route()
    start, end = date(2026, 4, 6), date(2026, 9, 30)
    sched = schedule(start, end, rng)
    ran = {d for d, *_ in sched}
    for i, (d, kind, miles, hour) in enumerate(sched):
        progress = (d - start).days / (end - start).days
        shoe = "g_nimbus" if d < date(2026, 7, 1) or rng.random() < 0.45 else "g_pegasus"
        prev = (d - timedelta(days=1)) in ran
        dump = make_run(31000000000 + i, d, hour, kind, miles * MI, progress, prev, shoe, rng, route_pts)
        import_dump(conn, dump)
    n = conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0]
    conn.close()
    return n


if __name__ == "__main__":
    count = build()
    print(f"Wrote {count} demo runs to {DEMO_DB}")
    sys.exit(0)
