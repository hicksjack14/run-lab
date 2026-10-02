import db
from ingest.strava_import import import_dump, local_to_utc

# Shaped like the real data from the Strava connector (Jack's Sept 29 run, trimmed).
DUMP = {
    "activity": {
        "id": "20385623675",
        "name": "Thornden run",
        "sport_type": "Run",
        "start_local": "2026-09-29T18:23:11",
        "gear_id": "33590599",
        "summary": {
            "distance": 6934, "moving_time": 2642, "elapsed_time": 2981,
            "elevation_gain": 97.2, "avg_cadence": 84.9315, "relative_effort": 50,
        },
    },
    "streams": {
        "time": [2, 101, 158, 214],
        "heart_rate": [101, 126, 135, 137],
        "velocity_smooth": [0, 2.4, 2.592, 2.864],
        "cadence": [0, 82, 78, 84],
        "distance": [0, 136.1, 281.2, 426.5],
        "moving": [False, True, True, True],
        "location": [[43.05, -76.15], [43.0505, -76.1495], [43.051, -76.149], [43.0515, -76.1485]],
        "altitude": [120.0, 120.5, 121.0, 121.5],
    },
    "performance": {
        "average_heartrate": 155.881,
        "max_heartrate": 181,
        "laps": [
            {"distance": 1609.34, "moving_time": 614, "avg_hr": 137.594, "max_hr": 147},
            {"distance": 1609.34, "moving_time": 600, "avg_hr": 155.11, "max_hr": 178},
        ],
        "best_efforts": [
            {"type_value": "Fastest1k", "value": 365},
            {"type_value": "Fastest5k", "value": 2193},
        ],
    },
}


def test_local_to_utc_handles_daylight_time():
    # Sept 29 is EDT (UTC-4)
    assert local_to_utc("2026-09-29T18:23:11", "America/New_York") == "2026-09-29T22:23:11Z"
    # Jan is EST (UTC-5)
    assert local_to_utc("2026-01-15T08:00:00", "America/New_York") == "2026-01-15T13:00:00Z"


def test_import_stores_run_with_utc_and_summary():
    conn = db.connect(":memory:")
    import_dump(conn, DUMP)
    run = conn.execute("SELECT * FROM runs WHERE strava_id = '20385623675'").fetchone()
    assert run["name"] == "Thornden run"
    assert run["start_utc"] == "2026-09-29T22:23:11Z"
    assert run["distance_m"] == 6934
    assert run["avg_hr"] == 155.881
    assert run["max_hr"] == 181
    assert run["has_gps"] == 1


def test_cadence_is_doubled_to_steps_per_minute():
    conn = db.connect(":memory:")
    import_dump(conn, DUMP)
    run = conn.execute("SELECT avg_cadence_spm FROM runs").fetchone()
    assert round(run["avg_cadence_spm"], 1) == 169.9
    rows = conn.execute("SELECT cadence_spm FROM run_streams ORDER BY t_s").fetchall()
    assert [r["cadence_spm"] for r in rows] == [0, 164, 156, 168]


def test_streams_are_aligned_by_index_with_gps():
    conn = db.connect(":memory:")
    import_dump(conn, DUMP)
    rows = conn.execute("SELECT * FROM run_streams ORDER BY t_s").fetchall()
    assert len(rows) == 4
    assert rows[1]["t_s"] == 101 and rows[1]["hr"] == 126 and rows[1]["moving"] == 1
    assert rows[0]["moving"] == 0
    assert (rows[0]["lat"], rows[0]["lng"]) == (43.05, -76.15)


def test_laps_and_best_efforts_saved():
    conn = db.connect(":memory:")
    import_dump(conn, DUMP)
    assert conn.execute("SELECT COUNT(*) FROM run_laps").fetchone()[0] == 2
    be = {r["type"]: r["seconds"] for r in conn.execute("SELECT * FROM best_efforts")}
    assert be == {"Fastest1k": 365, "Fastest5k": 2193}


def test_import_is_idempotent_and_keeps_tz_override():
    conn = db.connect(":memory:")
    import_dump(conn, DUMP)
    conn.execute("UPDATE runs SET tz = 'Europe/Dublin'")
    import_dump(conn, DUMP)
    assert conn.execute("SELECT COUNT(*) FROM runs").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM run_streams").fetchone()[0] == 4
    run = conn.execute("SELECT tz, start_utc FROM runs").fetchone()
    assert run["tz"] == "Europe/Dublin"
    assert run["start_utc"] == "2026-09-29T17:23:11Z"  # Dublin is UTC+1 in September


def test_run_without_gps_is_flagged():
    conn = db.connect(":memory:")
    dump = {**DUMP, "streams": {k: v for k, v in DUMP["streams"].items() if k not in ("location", "altitude")}}
    import_dump(conn, dump)
    assert conn.execute("SELECT has_gps FROM runs").fetchone()["has_gps"] == 0
    assert conn.execute("SELECT lat FROM run_streams LIMIT 1").fetchone()["lat"] is None
