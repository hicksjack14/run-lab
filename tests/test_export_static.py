import json
from datetime import date

import pytest

import db
from ingest.strava_import import import_dump
from tools import export_static

TODAY = date(2026, 10, 1)


def long_dump(rid="900", n=21):
    """A 2 km run sampled every 100 m, with GPS, so trimming has something to cut."""
    return {
        "activity": {"id": rid, "name": "Trim test", "sport_type": "Run", "start_local": "2026-09-29T18:00:00", "gear_id": "g1",
                     "summary": {"distance": 2000, "moving_time": 600, "elapsed_time": 600, "elevation_gain": 5, "avg_cadence": 85}},
        "streams": {"time": [i * 30 for i in range(n)], "heart_rate": [150] * n, "velocity_smooth": [3.3] * n, "cadence": [85] * n,
                    "distance": [i * 100 for i in range(n)], "moving": [True] * n,
                    "location": [[43.04 + i * 0.0005, -76.13] for i in range(n)], "altitude": [150] * n},
        "performance": {"average_heartrate": 150, "max_heartrate": 160, "laps": [], "best_efforts": []},
    }


@pytest.fixture
def source(tmp_path):
    path = tmp_path / "src.db"
    conn = db.connect(path)
    import_dump(conn, long_dump())
    conn.close()
    return path


def run_export(source, tmp_path, **kw):
    out = tmp_path / "docs"
    summary = export_static.export(source, out, today=TODAY, **kw)
    return out, summary


def test_writes_the_site_and_data_files(source, tmp_path):
    out, summary = run_export(source, tmp_path, trim_m=0)
    for rel in ("index.html", "js/main.js", "css/base.css", ".nojekyll", "data/meta.json", "data/runs.json", "data/home.json",
                "data/fitness.json", "data/analytics.json", "data/places.json", "data/plan.json", "data/calc.json", "data/runs/900.json"):
        assert (out / rel).exists(), rel
    assert summary["runs"] == 1


def test_index_is_marked_static_and_meta_says_read_only(source, tmp_path):
    out, _ = run_export(source, tmp_path)
    assert 'name="runlab-static" content="1"' in (out / "index.html").read_text()
    meta = json.loads((out / "data/meta.json").read_text())
    assert meta["static"] is True and meta["demo"] is False and meta["strava_connected"] is False and meta["exported_at"]


def test_gps_is_trimmed_at_both_ends_but_stats_survive(source, tmp_path):
    out, _ = run_export(source, tmp_path, trim_m=500)
    s = json.loads((out / "data/runs/900.json").read_text())["streams"]
    assert s["lat"][:5] == [None] * 5 and s["lat"][-5:] == [None] * 5       # first and last 500 m
    assert all(v is not None for v in s["lat"][6:15])
    assert s["hr"][0] == 150 and s["dist"][-1] == 2000                      # everything but location is untouched
    assert json.loads((out / "data/runs/900.json").read_text())["run"]["has_gps"] is True


def test_trimming_reaches_derived_data_too(source, tmp_path):
    out, _ = run_export(source, tmp_path, trim_m=500)
    places = json.loads((out / "data/places.json").read_text())
    start_lat = 43.04
    assert min(p[0] for p in places["routes"][0]["pts"]) > start_lat + 0.0005 * 4   # route no longer starts at the true start
    glyph = json.loads((out / "data/home.json").read_text())["recent"][0]["glyph"]
    assert min(p[0] for p in glyph) > start_lat + 0.0005 * 4


def test_no_trim_keeps_the_full_route(source, tmp_path):
    out, _ = run_export(source, tmp_path, trim_m=0)
    s = json.loads((out / "data/runs/900.json").read_text())["streams"]
    assert all(v is not None for v in s["lat"])


def test_source_database_is_never_modified(source, tmp_path):
    export_static.export(source, tmp_path / "docs", today=TODAY, trim_m=500)
    conn = db.connect(source)
    assert conn.execute("SELECT COUNT(*) FROM run_streams WHERE lat IS NULL").fetchone()[0] == 0


def test_plan_and_calendar_file_are_included_when_a_plan_exists(source, tmp_path):
    from server import create_app
    c = create_app(source, today=lambda: TODAY).test_client()
    assert c.post("/api/plan", json={"goal": "10K", "race_date": "2026-12-12", "goal_time_s": 3600, "vdot": 40}).status_code == 201
    out, _ = run_export(source, tmp_path)
    assert json.loads((out / "data/plan.json").read_text())["plan"]["goal"] == "10K"
    assert (out / "data/plan.ics").read_text().startswith("BEGIN:VCALENDAR")


def test_floats_are_rounded_to_keep_files_small(source, tmp_path):
    out, _ = run_export(source, tmp_path, trim_m=0)
    assert export_static.round_floats({"a": [1.123456789, 2], "b": {"c": 0.1 + 0.2}}) == {"a": [1.123457, 2], "b": {"c": 0.3}}


def test_empty_database_exports_without_crashing(tmp_path):
    path = tmp_path / "empty.db"
    db.connect(path).close()
    out = tmp_path / "docs"
    summary = export_static.export(path, out, today=TODAY)
    assert summary["runs"] == 0 and (out / "data/runs.json").exists()
