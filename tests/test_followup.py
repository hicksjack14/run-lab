"""Chained follow-up plans: an easy 'companion' race and a recovery week after a previous race."""
import re
from datetime import date, timedelta

import pytest

import db
from analysis import plans
from server import create_app

TODAY = date(2026, 10, 5)
VDOT = 40.96  # Jack's current estimate

HALF = {"goal": "Half marathon", "race_date": "2026-10-18", "start_date": "2026-10-02", "days_per_week": 4, "long_run_dow": 6}
FOLLOW = {"goal": "10K", "race_date": "2026-11-26", "days_per_week": 4, "long_run_dow": 6, "follow_up": True,
          "role": "companion", "companion_pace_s": 870, "name": "Thanksgiving 10K with Dad"}


def add_run(conn, rid, day, miles=4.0):
    conn.execute(
        "INSERT INTO runs (strava_id, name, start_local, start_utc, distance_m, moving_s, elapsed_s, avg_hr, max_hr, avg_cadence_spm, gear_id, elevation_gain_m, has_gps)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0)",
        (rid, f"Run {rid}", f"{day}T17:00:00", f"{day}T21:00:00Z", miles * 1609.344, 2400, 2400, 150, 185, 165, "g1", 20))
    conn.execute("INSERT INTO best_efforts VALUES (?,?,?)", (rid, "Fastest5k", 1680))
    conn.commit()


@pytest.fixture
def env(tmp_path):
    path = tmp_path / "t.db"
    conn = db.connect(path)
    for i, day in enumerate(["2026-09-08", "2026-09-15", "2026-09-22", "2026-09-29", "2026-09-30"]):
        add_run(conn, str(i + 1), day)
    conn.close()
    clock = {"today": TODAY}
    app = create_app(path, today=lambda: clock["today"])
    return app.test_client(), clock


# ------------------------------------------------------------------ generator
def companion(**kw):
    args = dict(goal="10K", race_date=date(2026, 11, 26), start_date=date(2026, 10, 19), current_weekly_mi=18,
                vdot_value=VDOT, days_per_week=4, long_run_dow=6, role="companion", companion_pace_s=870,
                recovery_first=True, name="Thanksgiving 10K with Dad")
    args.update(kw)
    return plans.generate_plan(**args)


def test_companion_race_is_easy_at_the_companions_pace():
    p = companion()
    race = [w for w in p["workouts"] if w["kind"] == "race"]
    assert len(race) == 1 and race[0]["date"] == "2026-11-26"
    assert race[0]["title"] == "RACE DAY: Thanksgiving 10K with Dad"
    assert race[0]["pace_lo"] == race[0]["pace_hi"] == 870
    assert race[0]["hr_zone"] == [2, 2] or race[0]["hr_zone"] == (2, 2)
    assert p["role"] == "companion" and p["goal"] == "Thanksgiving 10K with Dad"
    assert abs(p["goal_time_s"] - 870 * 6.2137) < 1


def test_companion_plan_has_no_speed_work_or_race_warnings():
    p = companion()
    assert not {w["kind"] for w in p["workouts"]} & {"intervals"}
    assert p["warnings"] == []  # six weeks is plenty for an easy run; no "goal too ambitious"


def test_recovery_first_week_is_easy_and_lighter():
    p = companion()
    wk1 = [w for w in p["workouts"] if w["week"] == 1]
    assert wk1 and {w["kind"] for w in wk1} <= {"easy", "long"}
    assert p["weeks"][0]["recovery"] is True
    wk2_mi = p["weeks"][1]["planned_mi"]
    assert p["weeks"][0]["planned_mi"] < wk2_mi
    assert min(w["date"] for w in p["workouts"]) >= "2026-10-19"


def test_normal_race_plans_are_unchanged_by_the_new_options():
    a = plans.generate_plan("Half marathon", date(2026, 12, 19), date(2026, 10, 5), 18, VDOT, days_per_week=4)
    b = plans.generate_plan("Half marathon", date(2026, 12, 19), date(2026, 10, 5), 18, VDOT, days_per_week=4,
                            role="race", recovery_first=False, name=None)
    assert a["workouts"] == b["workouts"] and a["goal"] == "Half marathon" and a["warnings"] == b["warnings"]


# ------------------------------------------------------------------ API
def build_chain(client):
    assert client.post("/api/plan", json=HALF).status_code == 201
    return client.post("/api/plan", json=FOLLOW)


def test_follow_up_chains_after_the_first_plan(env):
    client, _ = env
    r = build_chain(client)
    assert r.status_code == 201
    body = r.get_json()
    assert body["plan"]["goal"] == "Half marathon"              # still on the half until it's run
    assert [c["goal"] for c in body["plan"]["chain"]] == ["Half marathon", "Thanksgiving 10K with Dad"]
    assert [c["role"] for c in body["plan"]["chain"]] == ["race", "companion"]
    races = [w for w in body["workouts"] if w["kind"] == "race"]
    assert [w["date"] for w in races] == ["2026-10-18", "2026-11-26"]
    dates = [w["date"] for w in body["workouts"]]
    assert dates == sorted(dates)
    # the follow-up starts the day after the half; week numbers keep counting (3 half weeks, then 6)
    follow_first = min(w["date"] for w in body["workouts"] if w["date"] > "2026-10-18")
    assert follow_first >= "2026-10-19"
    assert [wk["week"] for wk in body["plan"]["weeks"]] == list(range(1, 10))
    assert max(w["week"] for w in body["workouts"]) == 9
    assert body["days_to_race"] == (date(2026, 10, 18) - TODAY).days


def test_current_plan_switches_to_the_follow_up_after_the_first_race(env):
    client, clock = env
    build_chain(client)
    clock["today"] = date(2026, 10, 19)
    body = client.get("/api/plan").get_json()
    assert body["plan"]["goal"] == "Thanksgiving 10K with Dad" and body["plan"]["role"] == "companion"
    assert body["days_to_race"] == (date(2026, 11, 26) - date(2026, 10, 19)).days
    assert body["plan"]["goal_time_s"] == pytest.approx(870 * 6.2137, abs=1)
    assert body["next"]["date"] >= "2026-10-19"
    # the finished half is still in the list, so adherence history is kept
    assert any(w["kind"] == "race" and w["date"] == "2026-10-18" for w in body["workouts"])


def test_follow_up_warnings_are_labelled_by_plan(env):
    client, _ = env
    body = build_chain(client).get_json()
    assert body["plan"]["warnings"], "the half plan has warnings (compressed build)"
    assert all(w.startswith(("Half marathon:", "Thanksgiving 10K with Dad:")) for w in body["plan"]["warnings"])


def test_ics_covers_both_races_and_keeps_existing_event_ids(env):
    client, _ = env
    client.post("/api/plan", json=HALF)
    before = set(re.findall(r"UID:(\S+)", client.get("/api/plan.ics").get_data(as_text=True)))
    client.post("/api/plan", json=FOLLOW)
    text = client.get("/api/plan.ics?time=06:30").get_data(as_text=True)
    after = re.findall(r"UID:(\S+)", text)
    assert len(after) == len(set(after)), "every event needs a unique id"
    assert before <= set(after), "re-importing must update the half-marathon events, not duplicate them"
    assert "SUMMARY:RACE DAY: Thanksgiving 10K with Dad" in text and "SUMMARY:RACE DAY: Half marathon" in text
    assert "DTSTART:20261126T063000" in text


def test_follow_up_validation(env):
    client, _ = env
    assert client.post("/api/plan", json=FOLLOW).status_code == 400            # nothing to follow yet
    client.post("/api/plan", json=HALF)
    assert client.post("/api/plan", json={**FOLLOW, "race_date": "2026-10-10"}).status_code == 400   # before the half
    assert client.post("/api/plan", json={**FOLLOW, "start_date": "2026-10-10"}).status_code == 400  # starts before it ends
    assert client.post("/api/plan", json={**FOLLOW, "role": "pacer"}).status_code == 400
    assert client.post("/api/plan", json={**FOLLOW, "companion_pace_s": 30}).status_code == 400
    assert len(client.get("/api/plan").get_json()["plan"]["chain"]) == 1       # nothing bad got saved


def test_delete_last_removes_only_the_follow_up(env):
    client, _ = env
    build_chain(client)
    body = client.delete("/api/plan?last=1").get_json()
    assert len(body["plan"]["chain"]) == 1 and body["plan"]["goal"] == "Half marathon"
    assert [w["kind"] for w in body["workouts"] if w["kind"] == "race"] == ["race"]
    build_chain(client)
    assert client.delete("/api/plan").get_json() == {"plan": None}


def test_a_normal_new_plan_still_replaces_the_whole_chain(env):
    client, _ = env
    build_chain(client)
    body = client.post("/api/plan", json={"goal": "5K", "race_date": "2026-12-12", "days_per_week": 4, "long_run_dow": 6}).get_json()
    assert len(body["plan"]["chain"]) == 1 and body["plan"]["goal"] == "5K"


def test_home_shows_the_chain(env):
    client, _ = env
    build_chain(client)
    h = client.get("/api/home").get_json()
    assert [c["goal"] for c in h["plan"]["plan"]["chain"]] == ["Half marathon", "Thanksgiving 10K with Dad"]


def test_starting_weekly_miles_can_be_set_for_the_follow_up(env):
    client, _ = env
    client.post("/api/plan", json=HALF)
    low = client.post("/api/plan", json=FOLLOW).get_json()["plan"]["weeks"]
    client.delete("/api/plan?last=1")
    high = client.post("/api/plan", json={**FOLLOW, "weekly_mi": 24}).get_json()["plan"]["weeks"]
    assert high[-5]["planned_mi"] > low[-5]["planned_mi"]       # a build week in the follow-up block
    assert client.post("/api/plan", json={**FOLLOW, "weekly_mi": 2}).status_code == 400
    assert client.post("/api/plan", json={**FOLLOW, "weekly_mi": 200}).status_code == 400


def test_each_race_knows_its_slice_of_the_plan(env):
    client, _ = env
    body = build_chain(client).get_json()
    chain, workouts, weeks = body["plan"]["chain"], body["workouts"], body["plan"]["weeks"]
    half, ten_k = chain
    assert half["week_from"] == 1 and ten_k["week_from"] == half["week_to"] + 1
    assert ten_k["week_to"] == len(weeks)
    assert half["start_date"] == "2026-10-02" and ten_k["start_date"] == "2026-10-19"
    assert ten_k["days_per_week"] == 4 and isinstance(ten_k["warnings"], list)
    for c in chain:
        mine = [w for w in workouts if w["plan_id"] == c["id"]]
        assert mine and sum(1 for w in mine if w["kind"] == "race") == 1
        assert all(c["week_from"] <= w["week"] <= c["week_to"] for w in mine)
        assert [w for w in mine if w["kind"] == "race"][0]["date"] == c["race_date"]
    assert {w["plan_id"] for w in workouts} == {c["id"] for c in chain}
