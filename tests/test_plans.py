from datetime import date, timedelta

import pytest

from analysis import plans, zones

VDOT = 38
START = date(2026, 10, 5)  # a Monday


def make(goal="Half marathon", weeks=14, base=18, days=4, goal_time=None, long_dow=6, start=START):
    race = start + timedelta(days=weeks * 7 - 1 - (6 - 5))  # race on the Saturday of the last week
    return plans.generate_plan(goal, race, start, base, VDOT, days_per_week=days,
                               long_run_dow=long_dow, goal_time_s=goal_time), race


def by_week(plan):
    out = {}
    for w in plan["workouts"]:
        out.setdefault(w["week"], []).append(w)
    return out


def test_race_is_on_race_date_and_nothing_after():
    plan, race = make()
    race_workouts = [w for w in plan["workouts"] if w["kind"] == "race"]
    assert len(race_workouts) == 1 and race_workouts[0]["date"] == race.isoformat()
    assert max(w["date"] for w in plan["workouts"]) == race.isoformat()
    assert min(w["date"] for w in plan["workouts"]) >= START.isoformat()


def test_day_before_race_is_rest():
    plan, race = make()
    dates = {w["date"] for w in plan["workouts"]}
    assert (race - timedelta(days=1)).isoformat() not in dates


def test_runs_per_full_week_matches_days_per_week():
    for d in (3, 4, 5, 6):
        plan, _ = make(days=d)
        weeks = by_week(plan)
        for wk in range(2, 6):  # early full weeks
            assert len(weeks[wk]) == d, (d, wk)


def test_weekly_mileage_growth_is_capped_before_taper():
    plan, _ = make(weeks=16, base=20)
    last_normal = None
    for w in plan["weeks"]:
        if w["phase"] == "taper":
            break
        if last_normal is not None:
            assert w["planned_mi"] <= last_normal * 1.12 + 1.0, (last_normal, w["planned_mi"])
        if not w["recovery"]:
            last_normal = w["planned_mi"]


def test_recovery_weeks_dip_and_taper_is_lighter_than_peak():
    plan, _ = make(weeks=16, base=20)
    wk = plan["weeks"]
    assert any(w["recovery"] for w in wk)
    peak = max(w["planned_mi"] for w in wk if w["phase"] != "taper")
    assert all(w["planned_mi"] < peak for w in wk if w["phase"] == "taper")
    assert wk[-1]["phase"] == "taper"


def test_long_run_is_the_longest_run_of_each_full_week():
    plan, _ = make(weeks=14, base=18)
    for wk, items in by_week(plan).items():
        if len(items) < 4 or items[-1]["kind"] == "race" or any(w["kind"] == "race" for w in items):
            continue
        longest = max(items, key=lambda w: w["distance_mi"])
        assert longest["kind"] == "long", (wk, [(w["kind"], w["distance_mi"]) for w in items])


def test_paces_come_from_vdot_and_goal_pace_used_for_race():
    plan, _ = make(goal_time=2 * 3600 + 10 * 60)
    race = next(w for w in plan["workouts"] if w["kind"] == "race")
    goal_pace = (2 * 3600 + 600) / (21097.5 / zones.MI)
    assert race["pace_lo"] == pytest.approx(goal_pace, abs=1)
    easy = next(w for w in plan["workouts"] if w["kind"] == "easy")
    p = zones.training_paces(VDOT)
    assert easy["pace_lo"] == pytest.approx(p["easy_fast"], abs=1)
    assert easy["pace_hi"] == pytest.approx(p["easy_slow"], abs=1)


def test_quality_workouts_exist_and_use_threshold_or_interval_pace():
    plan, _ = make(weeks=14)
    kinds = {w["kind"] for w in plan["workouts"]}
    assert {"easy", "long", "race"} <= kinds
    assert kinds & {"tempo", "intervals"}


def test_too_few_weeks_warns():
    plan, _ = make(goal="Marathon", weeks=6)
    assert any("weeks" in w.lower() for w in plan["warnings"])


def test_ambitious_goal_warns():
    plan, _ = make(goal="Half marathon", goal_time=75 * 60)
    assert any("faster than" in w.lower() for w in plan["warnings"])


def test_low_base_is_lifted_to_feasible_start_with_warning():
    plan, _ = make(base=4, days=5)
    assert plan["weeks"][0]["planned_mi"] >= 10
    assert any("recent mileage" in w.lower() for w in plan["warnings"])


def test_saturday_long_run_shifts_week():
    plan, _ = make(long_dow=5)
    longs = [w for w in plan["workouts"] if w["kind"] == "long"]
    assert longs and all(date.fromisoformat(w["date"]).weekday() == 5 for w in longs)


def test_mid_week_start_begins_on_start_date():
    start = date(2026, 10, 7)  # Wednesday
    race = date(2026, 12, 19)
    plan = plans.generate_plan("10K", race, start, 15, VDOT, days_per_week=4)
    assert min(w["date"] for w in plan["workouts"]) >= start.isoformat()


def test_race_before_start_raises():
    with pytest.raises(ValueError):
        plans.generate_plan("5K", date(2026, 10, 1), date(2026, 10, 5), 15, VDOT)


def test_custom_distance_accepted():
    plan = plans.generate_plan(10000, date(2026, 12, 19), START, 15, VDOT)
    assert plan["workouts"][-1]["kind"] == "race"
