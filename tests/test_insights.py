import random
from datetime import date, timedelta
from pathlib import Path

import pytest

import db
from analysis import insights

TODAY = date(2026, 10, 1)


def run(i, day, miles=4.0, pace=600, hr=150, hour=17, gear="a", fade=0.0, drift=0.0, cad=165, z=(0.1, 0.5, 0.3, 0.08, 0.02)):
    """A hand-made run dict shaped like insights.load_runs output."""
    speed = 1609.344 / pace * 60  # m/min
    return {
        "id": str(i), "date": day, "start_hour": hour, "dist_mi": miles, "moving_s": miles * pace, "pace": pace,
        "avg_hr": hr, "max_hr_run": hr + 20, "ef": speed / hr, "hr_frac": hr / 195, "gear": gear,
        "elev_per_mi": 40.0, "cadence": cad, "fade": fade, "drift": drift, "zone_secs": [x * miles * pace for x in z],
        "prev_day_run": False,
    }


# ---------- regression helper ----------
def test_ols_recovers_known_coefficients():
    rng = random.Random(1)
    X, y = [], []
    for _ in range(200):
        a, b = rng.uniform(0, 10), rng.choice([0, 1])
        X.append([1.0, a, b])
        y.append(3 + 2 * a - 5 * b + rng.gauss(0, 0.5))
    fit = insights.ols(X, y)
    assert fit["beta"] == pytest.approx([3, 2, -5], abs=0.3)
    assert abs(fit["t"][1]) > 10 and abs(fit["t"][2]) > 10


def test_ols_singular_returns_none():
    assert insights.ols([[1, 2, 4], [1, 3, 6], [1, 4, 8], [1, 5, 10]], [1, 2, 3, 4]) is None


# ---------- per-run metrics from streams ----------
def test_load_runs_computes_halves_zones_and_prev_day(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    for rid, day in (("1", "2026-09-28"), ("2", "2026-09-29")):
        conn.execute("INSERT INTO runs (strava_id, name, start_local, start_utc, distance_m, moving_s, elapsed_s, avg_hr, max_hr, avg_cadence_spm, gear_id, elevation_gain_m, has_gps)"
                     " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,1)", (rid, "r", f"{day}T17:30:00", f"{day}T21:30:00Z", 3218.688, 1200, 1200, 150, 170, 168, "g", 30))
    # run 2: 20 minutes, first half faster than second half, HR 130 then 170
    rows = []
    for k in range(0, 1201, 10):
        first = k < 600
        speed = 3.0 if first else 2.0
        rows.append(("2", k, 130 if first else 170, speed, 84, 0 if k == 0 else None, 1 if True else 0))
    dist = 0.0
    for r in rows:
        t = r[1]
        dist = dist + (r[3] * 10 if t else 0)
        conn.execute("INSERT INTO run_streams (strava_id, t_s, hr, speed_mps, cadence_spm, distance_m, moving) VALUES (?,?,?,?,?,?,1)",
                     ("2", t, r[2], r[3], 168, dist))
    conn.commit()
    runs = insights.load_runs(conn, max_hr=200)
    r2 = next(r for r in runs if r["id"] == "2")
    assert r2["prev_day_run"] is True
    assert r2["fade"] > 0.3  # second half much slower
    assert r2["start_hour"] == 17
    z = r2["zone_secs"]
    assert z[1] > 0 and z[3] > 0  # 130/200 = 65% -> zone 2 (index 1), 170/200 = 85% -> zone 4 (index 3)
    assert next(r for r in runs if r["id"] == "1")["prev_day_run"] is False


# ---------- findings on hand-made data ----------
def many(n, start=date(2026, 5, 4), gap=2, **kw):
    return [run(i, start + timedelta(days=i * gap), **kw) for i in range(n)]


def kinds(findings):
    return {f["id"]: f for f in findings["findings"]}


def test_too_little_data_is_reported_honestly():
    out = insights.build_findings(many(4), TODAY, max_hr=195)
    assert out["findings"] == [] or all(f["confidence"] == "low" for f in out["findings"])
    assert "enough" in out["status"].lower()


def test_consistency_good_when_three_plus_runs_every_week():
    runs = [run(i, date(2026, 8, 3) + timedelta(days=d)) for i, d in enumerate([0, 2, 4, 7, 9, 11, 14, 16, 18, 21, 23, 25, 28, 30, 32, 35, 37, 39, 42, 44, 46, 49, 51, 53])]
    f = kinds(insights.build_findings(runs, TODAY, max_hr=195))
    assert f["consistency"]["kind"] == "good"


def test_consistency_flags_gaps():
    runs = [run(i, date(2026, 6, 1) + timedelta(days=d)) for i, d in enumerate([0, 3, 7, 30, 33, 60, 64, 90, 93, 97, 100, 104, 120, 125, 127, 129])]
    f = kinds(insights.build_findings(runs, TODAY, max_hr=195))
    assert f["consistency"]["kind"] == "improve"


def test_mileage_spike_is_flagged_with_the_week():
    runs = []
    miles_by_week = [10, 11, 12, 13, 12, 22, 14, 15]
    for w, mi in enumerate(miles_by_week):
        for d in (0, 2, 4):
            runs.append(run(len(runs), date(2026, 8, 3) + timedelta(days=7 * w + d), miles=mi / 3))
    f = kinds(insights.build_findings(runs, date(2026, 10, 1), max_hr=195))
    assert f["ramp"]["kind"] == "improve"
    assert "2026-09-07" in f["ramp"]["body"] or "Sep 7" in f["ramp"]["body"]


def test_gray_zone_heavy_training_is_flagged_and_polarized_is_praised():
    polar_runs = [{**r, "zone_secs": [r["moving_s"] * x for x in (0.3, 0.5, 0.08, 0.08, 0.04)]} for r in many(30)]
    gray_runs = [{**r, "zone_secs": [r["moving_s"] * x for x in (0.05, 0.15, 0.6, 0.15, 0.05)]} for r in many(30)]
    assert kinds(insights.build_findings(gray_runs, TODAY, max_hr=195))["intensity"]["kind"] == "improve"
    assert kinds(insights.build_findings(polar_runs, TODAY, max_hr=195))["intensity"]["kind"] == "good"


def test_fade_detected_as_starting_too_fast():
    runs = many(30, fade=0.06)
    f = kinds(insights.build_findings(runs, TODAY, max_hr=195))
    assert f["pacing"]["kind"] == "improve"


def test_negative_splits_are_praised():
    f = kinds(insights.build_findings(many(30, fade=-0.02), TODAY, max_hr=195))
    assert f["pacing"]["kind"] == "good"


def test_cardiac_drift_on_long_runs():
    runs = many(30, miles=7.0, pace=620, drift=0.09)
    f = kinds(insights.build_findings(runs, TODAY, max_hr=195))
    assert f["drift"]["kind"] == "improve"


# ---------- end-to-end recovery of planted effects ----------
DEMO = Path(__file__).resolve().parent.parent / "data" / "demo.db"


@pytest.mark.skipif(not DEMO.exists(), reason="demo database not generated (python -m tools.make_demo_data)")
def test_engine_recovers_effects_planted_in_demo_data():
    conn = db.connect(DEMO)
    out = insights.analyze(conn, TODAY)
    f = {x["id"]: x for x in out["findings"]}
    assert f["fitness-trend"]["kind"] == "good"          # planted: fitness improves
    assert f["time-of-day"]["kind"] == "works"           # planted: evening is more efficient
    assert f["back-to-back"]["kind"] == "doesnt"         # planted: day-after-run costs ~4 bpm
    assert out["summary"]["runs"] > 50
    assert len(out["series"]["weekly"]) > 20
    assert out["series"]["hours"] and len(out["series"]["hours"]) == 24


@pytest.mark.skipif(not DEMO.exists(), reason="demo database not generated")
def test_engine_recovers_planted_music_effect():
    conn = db.connect(DEMO)
    if not conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0]:
        pytest.skip("demo database has no plays (regenerate with python -m tools.make_demo_data)")
    f = {x["id"]: x for x in insights.analyze(conn, TODAY)["findings"]}
    assert "Demo Artist 3" in f["music-works"]["title"]       # planted: ~3 bpm easier
    assert "Demo Artist 7" in f["music-doesnt"]["title"]      # planted: ~3 bpm harder
