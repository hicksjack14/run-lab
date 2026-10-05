"""The races log and the goal races (NYC Half, NYC Marathon, Boston)."""
from datetime import date

import pytest

import db
from analysis import goal_races, zones
from server import create_app

TODAY = date(2026, 10, 5)
HALF, MARATHON = 21097.5, 42195.0


def entry(d, dist, t, event=None, nyrr=False, name="Race"):
    return {"race_date": d, "distance_m": dist, "time_s": t, "event": event, "nyrr": nyrr, "name": name}


def goal(key):
    return next(g for g in goal_races.GOALS if g["key"] == key)


# ---------------------------------------------------------------- the requirements data
def test_every_standard_text_matches_its_seconds():
    for g in goal_races.GOALS:
        std = g["standard"]
        for opt in [std] + ([std["alt"]] if std.get("alt") else []):
            h, m, s = (int(x) for x in opt["text"].split(":"))
            assert h * 3600 + m * 60 + s == opt["seconds"], f"{g['key']} {opt['text']}"


def test_the_agreed_men_18_34_standards():
    assert goal("boston-marathon")["standard"]["text"] == "2:55:00"
    assert goal("nyc-marathon")["standard"]["text"] == "2:53:00" and goal("nyc-marathon")["standard"]["alt"]["text"] == "1:21:00"
    assert goal("nyc-half")["standard"]["text"] == "1:21:00"
    assert goal_races.DIVISION["label"] == "Men 18-34"


def test_each_goal_has_routes_sources_and_a_check_date():
    assert goal_races.VERIFIED == "2026-10-05"
    for g in goal_races.GOALS:
        assert g["routes"] and g["sources"] and all(s["url"].startswith("https://") for s in g["sources"])
        assert all(r["title"] and r["detail"] for r in g["routes"])
    assert {g["key"] for g in goal_races.GOALS} == {"nyc-half", "nyc-marathon", "boston-marathon"}


# ---------------------------------------------------------------- evaluation
def test_no_races_means_not_yet_with_a_gap_from_current_fitness():
    p = goal_races.evaluate(goal("boston-marathon"), [], {"Marathon": 4 * 3600, "Half marathon": 6900}, TODAY)
    assert p["status"] == "not_yet" and p["completed"] == [] and p["qualified_with"] is None
    assert p["predicted"]["gap_s"] == 4 * 3600 - 10500 and p["predicted"]["standard_text"] == "2:55:00"
    assert round(p["predicted"]["pace_needed_s"]) == 400                     # 10500 s over 26.22 mi = 6:40.5 per mile


def test_a_fast_enough_marathon_in_the_window_qualifies_but_one_outside_it_does_not():
    fast = entry("2026-04-19", MARATHON, 10400)                              # 2:53:20: beats 2:55:00
    assert goal_races.evaluate(goal("boston-marathon"), [fast], None, TODAY)["status"] == "qualified"
    old = entry("2025-04-19", MARATHON, 10400)                               # before the 2027 window opened (2025-09-13)
    assert goal_races.evaluate(goal("boston-marathon"), [old], None, TODAY)["status"] == "not_yet"
    slow = goal_races.evaluate(goal("boston-marathon"), [entry("2026-04-19", MARATHON, 11000)], None, TODAY)
    assert slow["status"] == "not_yet" and slow["closest"]["gap_s"] == 500


def test_a_half_does_not_count_for_boston_but_does_for_the_nyc_marathon_standard():
    half = entry("2026-03-15", HALF, 4800, name="NYC Half")                 # 1:20:00
    assert goal_races.evaluate(goal("boston-marathon"), [half], None, TODAY)["status"] == "not_yet"
    q = goal_races.evaluate(goal("nyc-marathon"), [half], None, TODAY)
    assert q["status"] == "qualified" and q["qualified_with"]["distance_label"] == "half marathon"


def test_finishing_a_tagged_race_marks_it_completed_and_wins_over_qualified():
    log = [entry("2027-03-21", HALF, 5400, event="nyc-half", nyrr=True)]
    p = goal_races.evaluate(goal("nyc-half"), log, None, date(2027, 4, 1))
    assert p["status"] == "completed" and len(p["completed"]) == 1
    assert goal_races.evaluate(goal("nyc-marathon"), log, None, TODAY)["status"] == "not_yet"


def test_nyrr_counters_count_only_flagged_races_in_the_right_year():
    log = [entry("2026-03-15", HALF, 6000, nyrr=True), entry("2026-05-17", HALF, 6100, nyrr=True),
           entry("2026-06-01", 10000, 2900), entry("2025-11-02", MARATHON, 14000, nyrr=True)]
    half = goal_races.evaluate(goal("nyc-half"), log, None, TODAY)["counters"]
    assert half == [{"title": "4 of 6 program", "have": 2, "need": 4, "year": 2026}]
    nyc = goal_races.evaluate(goal("nyc-marathon"), log, None, TODAY)["counters"]
    assert nyc == [{"title": "9+1 program", "have": 0, "need": 9, "year": 2027}]


def test_window_closing_info():
    p = goal_races.evaluate(goal("nyc-half"), [], None, TODAY)
    assert p["window_closed"] is False and p["days_left"] == 6                 # window ends Oct 11, 2026
    assert goal_races.evaluate(goal("nyc-half"), [], None, date(2026, 10, 12))["window_closed"] is True


# ---------------------------------------------------------------- API
def add_run(conn, rid, day, miles, moving):
    conn.execute(
        "INSERT INTO runs (strava_id, name, start_local, start_utc, distance_m, moving_s, elapsed_s, avg_hr, max_hr, avg_cadence_spm, gear_id, elevation_gain_m, has_gps)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0)",
        (rid, f"Run {rid}", f"{day}T08:00:00", f"{day}T12:00:00Z", miles * 1609.344, moving, moving, 150, 185, 165, "g1", 20))
    conn.execute("INSERT OR IGNORE INTO best_efforts VALUES (?,?,?)", (rid, "Fastest5k", 1680))
    conn.commit()


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "t.db"
    conn = db.connect(path)
    for i, day in enumerate(["2026-09-08", "2026-09-15", "2026-09-22", "2026-09-29", "2026-09-30"]):
        add_run(conn, str(i + 1), day, 4.0, 2400)
    add_run(conn, "half1", "2026-09-27", 13.1, 6900)
    conn.close()
    return create_app(path, today=lambda: TODAY).test_client()


RACE = {"name": "Brooklyn Half", "race_date": "2026-09-27", "distance_m": 21097.5, "time_s": 6900, "event": "nyc-half", "nyrr": True}


def test_empty_log_still_lists_the_goal_races(client):
    r = client.get("/api/races").get_json()
    assert r["log"] == [] and [g["key"] for g in r["goals"]] == ["nyc-half", "nyc-marathon", "boston-marathon"]
    assert r["division"]["label"] == "Men 18-34" and r["verified"] == "2026-10-05" and r["fitness_is_estimate"] is True
    assert r["goals"][0]["progress"]["status"] == "not_yet"
    assert r["goals"][2]["progress"]["predicted"]["gap_s"] > 0              # fitness is nowhere near 2:55 yet


def test_add_a_race_matches_the_run_and_counts_toward_the_goal(client):
    r = client.post("/api/races", json=RACE)
    assert r.status_code == 201
    entry_ = r.get_json()["log"][0]
    assert entry_["name"] == "Brooklyn Half" and entry_["run_id"] == "half1" and entry_["nyrr"] is True and entry_["source"] == "manual"
    half = next(g for g in r.get_json()["goals"] if g["key"] == "nyc-half")
    assert half["progress"]["status"] == "completed" and half["progress"]["counters"][0]["have"] == 1


def test_validation(client):
    bad = [
        {**RACE, "name": " "}, {**RACE, "race_date": "2026-12-01"}, {**RACE, "race_date": "soon"}, {**RACE, "distance_m": 50},
        {**RACE, "time_s": 100}, {**RACE, "time_s": 99999}, {**RACE, "event": "paris"}, {"name": "x"},
    ]
    for body in bad:
        assert client.post("/api/races", json=body).status_code == 400, body
    assert client.get("/api/races").get_json()["log"] == []


def test_time_and_run_are_optional(client):
    r = client.post("/api/races", json={"name": "Turkey Trot", "race_date": "2025-11-27", "distance_m": 8046.72})
    assert r.status_code == 201
    e = r.get_json()["log"][0]
    assert e["time_s"] is None and e["run_id"] is None and e["event"] is None and e["nyrr"] is False


def test_delete_a_race(client):
    rid = client.post("/api/races", json=RACE).get_json()["log"][0]["id"]
    assert client.delete(f"/api/races/{rid}").get_json()["log"] == []
    assert client.delete(f"/api/races/{rid}").status_code == 404


def test_finished_plan_races_appear_in_the_log_by_themselves(tmp_path):
    path = tmp_path / "t.db"
    conn = db.connect(path)
    for i, day in enumerate(["2026-09-08", "2026-09-15", "2026-09-22", "2026-09-29", "2026-09-30"]):
        add_run(conn, str(i + 1), day, 4.0, 2400)
    add_run(conn, "race-day", "2026-10-18", 13.1, 7400)                         # the half marathon he ran
    conn.close()
    clock = {"today": TODAY}
    client = create_app(path, today=lambda: clock["today"]).test_client()
    client.post("/api/plan", json={"goal": "Half marathon", "race_date": "2026-10-18", "start_date": "2026-10-02", "days_per_week": 4, "long_run_dow": 6})
    assert client.get("/api/races").get_json()["log"] == []                    # still ahead of him
    clock["today"] = date(2026, 10, 19)
    log = client.get("/api/races").get_json()["log"]
    assert len(log) == 1 and log[0]["source"] == "plan" and log[0]["name"] == "Half marathon"
    assert log[0]["run_id"] == "race-day" and log[0]["time_s"] == 7400 and log[0]["race_date"] == "2026-10-18"
    # a hand-entered race on the same day replaces the automatic one (it has the official time)
    client.post("/api/races", json={"name": "Hartford Half", "race_date": "2026-10-18", "distance_m": 21097.5, "time_s": 7380})
    log = client.get("/api/races").get_json()["log"]
    assert [e["name"] for e in log] == ["Hartford Half"] and log[0]["source"] == "manual"


def test_races_are_in_the_static_export_list():
    from pathlib import Path
    assert '"races"' in (Path(__file__).resolve().parent.parent / "tools" / "export_static.py").read_text()
