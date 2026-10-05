import math
from datetime import date

import pytest

import db
from analysis import calculator, fitness

TODAY = date(2026, 10, 1)
MI = 1609.344


def add_run(conn, i, day, miles, pace, hr=None, stopped_s=0):
    moving = round(miles * pace)
    conn.execute("INSERT INTO runs (strava_id, name, start_local, start_utc, distance_m, moving_s, elapsed_s, avg_hr, max_hr) VALUES (?,?,?,?,?,?,?,?,?)",
                 (str(i), "r", f"{day}T17:00:00", f"{day}T21:00:00Z", miles * MI, moving, moving + stopped_s, hr, (hr or 150) + 20))
    conn.commit()


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    # twelve runs whose pace slows with distance exactly as 500 + 40*ln(miles) seconds per mile
    miles = [2, 2.5, 3, 3.5, 4, 4.5, 5, 5.5, 6, 6.5, 3, 4]
    for i, mi in enumerate(miles):
        day = f"2026-09-{i + 1:02d}"
        pace = 500 + 40 * math.log(mi)
        add_run(c, i, day, mi, pace, hr=round(200 - 0.1 * pace), stopped_s=round(mi * 60))   # one minute stopped per mile
    return c


def at(model, miles):
    return next(p for p in model["curve"] if p["mi"] == miles)


def test_fade_model_recovers_how_pace_slows_with_distance(conn):
    m = calculator.build(conn, TODAY)
    assert m["usual"]["n"] == 12
    assert at(m, 3.0)["usual"] == pytest.approx(500 + 40 * math.log(3), abs=1.0)
    assert at(m, 6.0)["usual"] == pytest.approx(500 + 40 * math.log(6), abs=1.0)
    assert at(m, 6.0)["usual"] > at(m, 3.0)["usual"]


def test_confidence_drops_beyond_the_longest_run(conn):
    m = calculator.build(conn, TODAY)                      # longest run 6.5 mi
    assert m["longest_mi"] == pytest.approx(6.5)
    assert at(m, 6.5)["confidence"] == "solid"
    assert at(m, 10.0)["confidence"] == "stretch"          # ~1.5x
    assert at(m, 26.0)["confidence"] == "guess"            # 4x
    assert at(m, 26.0)["band"] > at(m, 6.5)["band"]        # and the uncertainty band widens


def test_observed_stopping_habit(conn):
    m = calculator.build(conn, TODAY)
    assert m["stops"]["observed_min_per_mile"] == pytest.approx(1.0, abs=0.05)
    assert m["defaults"]["stop_every_mi"] == 3.0 and m["defaults"]["stop_min"] == 1.0


def test_heart_rate_at_pace_is_learned_from_runs(conn):
    hr = calculator.build(conn, TODAY)["hr_at_pace"]
    assert hr and hr["n"] == 12 and hr["k"] == pytest.approx(-0.1, abs=0.02)
    assert hr["c"] + hr["k"] * 600 == pytest.approx(200 - 0.1 * 600, abs=2)


def test_race_effort_curve_comes_from_fitness(conn):
    m = calculator.build(conn, TODAY)
    snap = fitness.snapshot(conn, TODAY)
    assert m["vdot"] == pytest.approx(snap["vdot"])
    assert at(m, 6.0)["race_s"] < at(m, 13.0)["race_s"] if at(m, 13.0)["race_s"] else True
    assert at(m, 6.0)["race_s"] == pytest.approx(__import__("analysis.zones", fromlist=["x"]).predict_time(snap["vdot"], 6.0 * MI), rel=0.01)


def test_flat_or_backwards_trend_is_treated_as_no_fade(tmp_path):
    c = db.connect(tmp_path / "t.db")
    for i, mi in enumerate([2, 3, 4, 5, 6, 7, 3, 4, 5]):
        add_run(c, i, f"2026-09-{i + 1:02d}", mi, 600 - 10 * mi)         # faster on longer runs (odd, but possible)
    m = calculator.build(c, TODAY)
    assert at(m, 3.0)["usual"] == pytest.approx(at(m, 7.0)["usual"], abs=0.5)   # never predicts getting faster with distance


def test_too_little_data_gives_no_usual_estimate_but_does_not_crash(tmp_path):
    c = db.connect(tmp_path / "t.db")
    for i in range(3):
        add_run(c, i, f"2026-09-0{i + 1}", 3.0, 600)
    m = calculator.build(c, TODAY)
    assert m["usual"] is None and all(p["usual"] is None for p in m["curve"])


def test_empty_database(tmp_path):
    m = calculator.build(db.connect(tmp_path / "t.db"), TODAY)
    assert m["usual"] is None and m["vdot"] is None and m["longest_mi"] == 0
    assert m["curve"] and m["stops"] is None and m["hr_at_pace"] is None


def test_defaults_come_from_saved_settings_else_the_built_ins(conn):
    assert calculator.build(conn, TODAY)["defaults"] == {"stop_every_mi": 3.0, "stop_min": 1.0, "pace_s": None}
    fitness.set_setting(conn, "calc_defaults", {"pace_s": 587, "stop_every_mi": 3.1, "stop_min": 1.25})
    assert calculator.build(conn, TODAY)["defaults"] == {"stop_every_mi": 3.1, "stop_min": 1.25, "pace_s": 587}
