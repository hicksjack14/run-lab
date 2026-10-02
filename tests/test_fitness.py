import json
from datetime import date

import pytest

import db
from analysis import fitness


def add_run(conn, rid, day, miles, moving_s, avg_hr=150, max_hr=175, efforts=()):
    conn.execute(
        "INSERT INTO runs (strava_id, name, start_local, start_utc, distance_m, moving_s, elapsed_s, avg_hr, max_hr)"
        " VALUES (?,?,?,?,?,?,?,?,?)",
        (rid, f"Run {rid}", f"{day}T17:00:00", f"{day}T21:00:00Z", miles * 1609.344, moving_s, moving_s, avg_hr, max_hr))
    for t, s in efforts:
        conn.execute("INSERT INTO best_efforts VALUES (?,?,?)", (rid, t, s))
    conn.commit()


@pytest.fixture
def conn():
    return db.connect(":memory:")


def test_settings_roundtrip(conn):
    fitness.set_setting(conn, "max_hr", 199)
    assert fitness.get_settings(conn) == {"max_hr": 199}
    fitness.set_setting(conn, "max_hr", None)
    assert fitness.get_settings(conn) == {}


def test_snapshot_with_no_data_says_what_is_missing(conn):
    snap = fitness.snapshot(conn, date(2026, 10, 1))
    assert snap["vdot"] is None and snap["paces"] is None
    assert snap["needs"]


def test_snapshot_from_efforts_and_max_hr(conn):
    add_run(conn, "1", "2026-09-20", 6.0, 3600, max_hr=185, efforts=[("Fastest5k", 28 * 60)])
    add_run(conn, "2", "2026-09-25", 4.0, 2400, max_hr=190)
    snap = fitness.snapshot(conn, date(2026, 10, 1))
    assert snap["vdot"] == pytest.approx(33.5, abs=0.5)
    assert snap["vdot_source"] == "data"
    assert snap["max_hr"] == 185 and snap["max_hr_source"] == "data"  # two runs: top reading dropped
    assert len(snap["hr_zones"]) == 5
    assert snap["paces"]["easy"]["fast"] < snap["paces"]["easy"]["slow"]
    assert set(snap["predictions"]) == {"5K", "10K", "Half marathon", "Marathon"}


def test_overrides_win(conn):
    add_run(conn, "1", "2026-09-20", 6.0, 3600, efforts=[("Fastest5k", 28 * 60)])
    fitness.set_setting(conn, "vdot_override", 42)
    fitness.set_setting(conn, "max_hr", 201)
    snap = fitness.snapshot(conn, date(2026, 10, 1))
    assert snap["vdot"] == 42 and snap["vdot_source"] == "override"
    assert snap["max_hr"] == 201 and snap["max_hr_source"] == "override"


def test_weekly_miles_groups_by_monday_week(conn):
    add_run(conn, "1", "2026-09-28", 3.0, 1800)   # Monday
    add_run(conn, "2", "2026-10-04", 5.0, 3000)   # Sunday, same week
    add_run(conn, "3", "2026-10-05", 4.0, 2400)   # next Monday
    weeks = fitness.weekly_miles(conn, date(2026, 10, 7), n=3)
    assert [(w["start"], round(w["miles"], 1)) for w in weeks] == [
        ("2026-09-21", 0.0), ("2026-09-28", 8.0), ("2026-10-05", 4.0)]


def test_recent_weekly_average_uses_last_four_weeks(conn):
    for i, day in enumerate(["2026-09-08", "2026-09-15", "2026-09-22", "2026-09-29"]):
        add_run(conn, str(i), day, 10.0, 6000)
    assert fitness.snapshot(conn, date(2026, 10, 1))["recent_weekly_mi"] == pytest.approx(10.0, abs=1.5)


def test_adherence_marks_done_partial_missed_and_upcoming(conn):
    add_run(conn, "1", "2026-10-06", 5.0, 3000)   # did the planned 5
    add_run(conn, "2", "2026-10-08", 2.0, 1200)   # planned 4, did 2 -> partial
    workouts = [
        {"date": "2026-10-06", "distance_mi": 5.0, "kind": "tempo"},
        {"date": "2026-10-08", "distance_mi": 4.0, "kind": "easy"},
        {"date": "2026-10-10", "distance_mi": 4.0, "kind": "easy"},   # past, no run -> missed
        {"date": "2026-10-20", "distance_mi": 6.0, "kind": "long"},   # future
    ]
    out = fitness.adherence(conn, workouts, date(2026, 10, 12))
    assert [o["status"] for o in out] == ["done", "partial", "missed", "upcoming"]
    assert out[0]["actual_mi"] == pytest.approx(5.0)
    assert out[0]["run_id"] == "1"


def test_whole_runs_in_moving_time_raise_a_low_best_effort_estimate(conn):
    # Strava's 5K "best effort" inside this run is inflated by stops (36:33), but the run itself was 10.5 km in 61:31 of moving time
    add_run(conn, "1", "2026-09-20", 6.52, 3691, efforts=[("Fastest5k", 2193)])
    snap = fitness.snapshot(conn, date(2026, 10, 1))
    assert snap["vdot"] > 31 and snap["vdot_basis"]["type"] == "WholeRun" and snap["vdot_is_estimate"] is True


def test_race_result_beats_data_estimate_but_not_manual_override(conn):
    add_run(conn, "1", "2026-09-20", 6.52, 3691)
    fitness.set_setting(conn, "race_result", {"distance_m": 5000, "seconds": 27 * 60, "label": "5K"})
    snap = fitness.snapshot(conn, date(2026, 10, 1))
    assert snap["vdot_source"] == "race" and snap["vdot_is_estimate"] is False
    assert snap["vdot"] == pytest.approx(zones_vdot(5000, 27 * 60))
    fitness.set_setting(conn, "vdot_override", 50)
    assert fitness.snapshot(conn, date(2026, 10, 1))["vdot_source"] == "override"


def zones_vdot(d, t):
    from analysis import zones
    return zones.vdot(d, t)


def test_everyday_pace_estimate_helps_someone_who_never_races(conn):
    # a runner who jogs ~10:13/mi and has never done a hard effort: best efforts alone would read far too low
    for i, day in enumerate(["2026-09-10", "2026-09-14", "2026-09-18", "2026-09-22", "2026-09-26"]):
        add_run(conn, str(i + 1), day, 4.3, int(4.3 * 613), efforts=[("Fastest5k", 2193)])
    snap = fitness.snapshot(conn, date(2026, 10, 1))
    assert snap["vdot_basis"]["type"] == "EverydayPace" and 35 < snap["vdot"] < 40
    assert snap["paces"]["easy"]["fast"] < 613 + 40         # his everyday pace now sits inside (or near) the easy range


def test_everyday_pace_needs_three_runs(conn):
    add_run(conn, "1", "2026-09-26", 4.3, int(4.3 * 613))
    add_run(conn, "2", "2026-09-28", 4.3, int(4.3 * 613))
    assert fitness.snapshot(conn, date(2026, 10, 1))["vdot_basis"]["type"] != "EverydayPace"
