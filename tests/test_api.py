from datetime import date

import pytest

import db
from analysis import fitness
from server import create_app

TODAY = date(2026, 10, 1)


def add_run(conn, rid, day, miles=4.0, moving=2400, hr=150, max_hr=185, efforts=(("Fastest5k", 1680),), gear="g1"):
    conn.execute(
        "INSERT INTO runs (strava_id, name, start_local, start_utc, distance_m, moving_s, elapsed_s, avg_hr, max_hr, avg_cadence_spm, gear_id, elevation_gain_m, has_gps)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?,?,0)",
        (rid, f"Run {rid}", f"{day}T17:00:00", f"{day}T21:00:00Z", miles * 1609.344, moving, moving, hr, max_hr, 165, gear, 20))
    for t, s in efforts:
        conn.execute("INSERT INTO best_efforts VALUES (?,?,?)", (rid, t, s))
    conn.commit()


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "t.db"
    conn = db.connect(path)
    for i, day in enumerate(["2026-09-08", "2026-09-15", "2026-09-22", "2026-09-29", "2026-09-30"]):
        add_run(conn, str(i + 1), day, efforts=[("Fastest5k", 1680)] if i == 0 else [])
    conn.close()
    return create_app(path, today=lambda: TODAY).test_client()


def test_meta_flags_demo_and_counts(client):
    m = client.get("/api/meta").get_json()
    assert m["demo"] is False and m["runs"] == 5 and m["today"] == "2026-10-01"


def test_demo_database_is_flagged(tmp_path):
    path = tmp_path / "demo.db"
    db.connect(path).close()
    assert create_app(path).test_client().get("/api/meta").get_json()["demo"] is True


def test_fitness_has_paces_and_zones(client):
    f = client.get("/api/fitness").get_json()
    assert f["vdot"] > 30 and f["paces"]["easy"]["text"] and len(f["hr_zones"]) == 5
    assert len(f["weekly"]) == 12


def test_settings_override_and_validation(client):
    f = client.post("/api/settings", json={"vdot_override": 45, "max_hr": 200}).get_json()
    assert f["vdot"] == 45 and f["max_hr"] == 200
    assert client.post("/api/settings", json={"max_hr": 50}).status_code == 400
    assert client.post("/api/settings", json={"vdot_override": "fast"}).status_code == 400
    f = client.post("/api/settings", json={"vdot_override": None}).get_json()
    assert f["vdot_source"] == "data"


def test_runs_list_and_detail_with_neighbors(client):
    runs = client.get("/api/runs").get_json()
    assert [r["id"] for r in runs][:2] == ["5", "4"]
    d = client.get("/api/runs/3").get_json()
    assert d["prev"] == "2" and d["next"] == "4"
    assert d["best_efforts"] == []
    assert client.get("/api/runs/nope").status_code == 404


PLAN = {"goal": "Half marathon", "race_date": "2027-01-16", "goal_time_s": 7800, "days_per_week": 4, "long_run_dow": 6}


def test_create_plan_then_read_with_adherence(client):
    r = client.post("/api/plan", json=PLAN)
    assert r.status_code == 201
    body = r.get_json()
    assert body["plan"]["goal"] == "Half marathon" and body["days_to_race"] == (date(2027, 1, 16) - TODAY).days
    assert body["workouts"][-1]["kind"] == "race"
    assert body["stats"]["total"] == len(body["workouts"])
    again = client.get("/api/plan").get_json()
    assert again["plan"]["id"] == body["plan"]["id"]
    assert again["next"] is not None


def test_new_plan_replaces_old_one(client):
    first = client.post("/api/plan", json=PLAN).get_json()["plan"]["id"]
    second = client.post("/api/plan", json={**PLAN, "goal": "10K", "race_date": "2026-12-12"}).get_json()["plan"]["id"]
    assert second != first
    assert client.get("/api/plan").get_json()["plan"]["goal"] == "10K"


def test_plan_validation(client):
    assert client.post("/api/plan", json={"goal": "Half marathon"}).status_code == 400
    assert client.post("/api/plan", json={**PLAN, "race_date": "2026-09-01"}).status_code == 400
    assert client.post("/api/plan", json={**PLAN, "long_run_dow": 2}).status_code == 400


def test_plan_needs_data_for_paces(tmp_path):
    path = tmp_path / "empty.db"
    db.connect(path).close()
    r = create_app(path, today=lambda: TODAY).test_client().post("/api/plan", json=PLAN)
    assert r.status_code == 422 and r.get_json()["needs"]


def test_ics_download(client):
    assert client.get("/api/plan.ics").status_code == 404
    client.post("/api/plan", json=PLAN)
    r = client.get("/api/plan.ics?time=06:30")
    assert r.status_code == 200 and r.mimetype == "text/calendar"
    assert "attachment" in r.headers["Content-Disposition"] and ".ics" in r.headers["Content-Disposition"]
    text = r.get_data(as_text=True)
    assert text.startswith("BEGIN:VCALENDAR") and "T063000" in text
    assert client.get("/api/plan.ics?time=25:99").status_code == 400


def test_delete_plan(client):
    client.post("/api/plan", json=PLAN)
    assert client.delete("/api/plan").get_json() == {"plan": None}
    assert client.get("/api/plan").get_json() == {"plan": None}


def test_home_and_analytics_work_on_small_data(client):
    h = client.get("/api/home").get_json()
    assert len(h["recent"]) == 5 and h["week"]["runs"] >= 1 and h["plan"] is None
    a = client.get("/api/analytics").get_json()
    assert a["summary"]["runs"] == 5 and "enough" in a["status"].lower()


def test_sync_refused_in_demo_mode(tmp_path):
    path = tmp_path / "demo.db"
    db.connect(path).close()
    r = create_app(path).test_client().post("/api/sync")
    assert r.status_code == 400 and "demo" in r.get_json()["error"].lower()


def test_sync_without_credentials_is_a_clear_error(client, monkeypatch, tmp_path):
    import ingest.strava_api as sa
    monkeypatch.setattr(sa, "ENV_PATH", tmp_path / "missing.env")
    r = client.post("/api/sync")
    assert r.status_code == 400 and "STRAVA_CLIENT_ID" in r.get_json()["error"]


def test_places_endpoint_handles_runs_without_gps(client):
    body = client.get("/api/places").get_json()
    assert body["routes"] == [] and body["home"] is None


def test_analytics_runs_carry_explorer_fields(client):
    run = client.get("/api/analytics").get_json()["series"]["runs"][0]
    for key in ("moving_s", "max_hr", "elev_ft", "zone_secs", "dominant", "start", "gear"):
        assert key in run


def test_static_files_are_always_revalidated(client):
    assert client.get("/js/main.js").headers["Cache-Control"] == "no-cache"
    assert "Cache-Control" not in client.get("/api/meta").headers or client.get("/api/meta").headers["Cache-Control"] != "no-cache"


def test_race_result_sets_fitness_and_is_validated(client):
    f = client.post("/api/settings", json={"race_result": {"distance_m": 5000, "seconds": 1620, "label": "5K"}}).get_json()
    assert f["vdot_source"] == "race" and f["vdot"] > 30
    assert client.post("/api/settings", json={"race_result": {"distance_m": 5000, "seconds": 300}}).status_code == 400   # a 5-minute 5K
    assert client.post("/api/settings", json={"race_result": {"distance_m": "far", "seconds": 1620}}).status_code == 400
    assert client.post("/api/settings", json={"race_result": None}).get_json()["vdot_source"] == "data"
