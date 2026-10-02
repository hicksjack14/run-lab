import json
import time

import pytest

import db
from ingest import strava_api
from ingest.strava_api import StravaClient, RateLimited, to_dump

DETAIL = {
    "id": 20385623675, "name": "Thornden run", "type": "Run", "sport_type": "Run",
    "start_date": "2026-09-29T22:23:11Z", "start_date_local": "2026-09-29T18:23:11Z",
    "timezone": "(GMT-05:00) America/New_York",
    "distance": 6934.0, "moving_time": 2642, "elapsed_time": 2981, "total_elevation_gain": 97.2,
    "average_cadence": 84.9315, "suffer_score": 50, "gear_id": "g1",
    "average_heartrate": 155.881, "max_heartrate": 181,
    "laps": [{"distance": 1609.34, "moving_time": 614, "average_heartrate": 137.6, "max_heartrate": 147}],
    "best_efforts": [{"name": "1k", "elapsed_time": 365}, {"name": "5k", "elapsed_time": 2193}, {"name": "weird", "elapsed_time": 9}],
}
STREAMS = {
    "time": {"data": [0, 1, 2]}, "heartrate": {"data": [100, 110, 120]},
    "velocity_smooth": {"data": [0, 2.5, 2.6]}, "cadence": {"data": [0, 80, 82]},
    "distance": {"data": [0, 2.5, 5.1]}, "moving": {"data": [False, True, True]},
    "latlng": {"data": [[43.0, -76.0], [43.001, -76.001], [43.002, -76.002]]},
    "altitude": {"data": [150, 151, 152]},
}


def test_to_dump_maps_api_shapes_to_importer_format():
    d = to_dump(DETAIL, STREAMS)
    assert d["activity"]["id"] == "20385623675"
    assert d["activity"]["start_local"] == "2026-09-29T18:23:11"  # Strava's trailing Z is fake: it is local time
    assert d["activity"]["timezone"] == "America/New_York"
    assert d["activity"]["summary"]["elevation_gain"] == 97.2
    assert d["streams"]["heart_rate"] == [100, 110, 120]
    assert d["streams"]["location"][1] == [43.001, -76.001]
    assert d["performance"]["average_heartrate"] == 155.881
    assert d["performance"]["laps"][0]["avg_hr"] == 137.6
    names = {b["type_value"] for b in d["performance"]["best_efforts"]}
    assert names == {"Fastest1k", "Fastest5k", "weird"}


def test_to_dump_without_streams_or_gps():
    d = to_dump(DETAIL, {"time": {"data": [0, 1]}})
    assert d["streams"] == {"time": [0, 1]}


def test_dump_imports_cleanly_and_sets_timezone(tmp_path):
    from ingest.strava_import import import_dump
    conn = db.connect(tmp_path / "t.db")
    detail = {**DETAIL, "timezone": "(GMT+01:00) Europe/Dublin"}
    import_dump(conn, to_dump(detail, STREAMS))
    run = conn.execute("SELECT tz, start_utc FROM runs").fetchone()
    assert run["tz"] == "Europe/Dublin"
    assert run["start_utc"] == "2026-09-29T17:23:11Z"


class FakeHttp:
    """Records requests and replays canned (status, headers, body) responses by URL substring."""
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, method, url, headers=None, data=None):
        self.calls.append((method, url, data))
        for key, resp in self.routes.items():
            if key in url:
                return resp(url) if callable(resp) else resp
        raise AssertionError(f"unexpected request {url}")


def make_client(tmp_path, http, token=None):
    cfg = {"client_id": "123", "client_secret": "sek"}
    store = tmp_path / "token.json"
    if token:
        store.write_text(json.dumps(token))
    return StravaClient(cfg, store, http=http)


def test_expired_token_is_refreshed_and_saved(tmp_path):
    http = FakeHttp({"oauth/token": (200, {}, {"access_token": "new", "refresh_token": "r2", "expires_at": time.time() + 3600})})
    c = make_client(tmp_path, http, {"access_token": "old", "refresh_token": "r1", "expires_at": time.time() - 10})
    assert c.access_token() == "new"
    assert json.loads((tmp_path / "token.json").read_text())["refresh_token"] == "r2"
    assert "grant_type=refresh_token" in http.calls[0][2]


def test_valid_token_is_not_refreshed(tmp_path):
    http = FakeHttp({})
    c = make_client(tmp_path, http, {"access_token": "ok", "refresh_token": "r", "expires_at": time.time() + 3600})
    assert c.access_token() == "ok"
    assert http.calls == []


def test_missing_token_gives_helpful_error(tmp_path):
    with pytest.raises(SystemExit, match="auth"):
        make_client(tmp_path, FakeHttp({})).access_token()


def test_rate_limit_raises(tmp_path):
    http = FakeHttp({"athlete/activities": (429, {}, {"message": "Rate Limit Exceeded"})})
    c = make_client(tmp_path, http, {"access_token": "ok", "refresh_token": "r", "expires_at": time.time() + 3600})
    with pytest.raises(RateLimited):
        list(c.list_runs())


def test_sync_skips_existing_and_non_runs_and_stops_cleanly(tmp_path):
    activities = [
        {"id": 3, "type": "Ride", "sport_type": "Ride"},
        {"id": 2, "type": "Run", "sport_type": "Run"},
        {"id": 1, "type": "Run", "sport_type": "Run"},
    ]

    def acts(url):
        return (200, {}, activities if url.endswith("&page=1") else [])

    def detail(url):
        return (200, {}, {**DETAIL, "id": 2})

    http = FakeHttp({
        "athlete/activities": acts,
        "activities/2/streams": (200, {}, STREAMS),
        "activities/2": detail,
        "gear/g1": (200, {}, {"name": "Nimbus 26"}),
    })
    conn = db.connect(tmp_path / "t.db")
    conn.execute("INSERT INTO runs (strava_id, start_local, start_utc) VALUES ('1','2026-01-01T00:00:00','2026-01-01T05:00:00Z')")
    conn.commit()
    c = make_client(tmp_path, http, {"access_token": "ok", "refresh_token": "r", "expires_at": time.time() + 3600})
    result = strava_api.sync(conn, c, dump_dir=tmp_path / "dumps")
    assert result == {"imported": ["2"], "skipped": 1, "rate_limited": False}
    assert (tmp_path / "dumps" / "2.json").exists()
    from analysis import fitness
    assert fitness.get_settings(conn)["gear_names"] == {"g1": "Nimbus 26"}
    assert conn.execute("SELECT COUNT(*) FROM runs WHERE strava_id='2'").fetchone()[0] == 1


def test_sync_reports_rate_limit_and_keeps_progress(tmp_path):
    activities = [{"id": 2, "type": "Run", "sport_type": "Run"}, {"id": 1, "type": "Run", "sport_type": "Run"}]

    def detail(url):
        if "activities/1" in url:
            return (429, {}, {})
        return (200, {}, {**DETAIL, "id": 2})

    http = FakeHttp({
        "athlete/activities": lambda url: (200, {}, activities if url.endswith("&page=1") else []),
        "activities/2/streams": (200, {}, STREAMS),
        "activities/": detail,
        "gear/g1": (200, {}, {"name": "Nimbus 26"}),
    })
    conn = db.connect(tmp_path / "t.db")
    c = make_client(tmp_path, http, {"access_token": "ok", "refresh_token": "r", "expires_at": time.time() + 3600})
    result = strava_api.sync(conn, c, dump_dir=tmp_path / "dumps")
    assert result["imported"] == ["2"] and result["rate_limited"] is True


def test_a_failed_shoe_lookup_never_breaks_the_sync(tmp_path):
    http = FakeHttp({
        "athlete/activities": lambda url: (200, {}, [{"id": 2, "type": "Run", "sport_type": "Run"}] if url.endswith("&page=1") else []),
        "activities/2/streams": (200, {}, STREAMS),
        "activities/2": (200, {}, {**DETAIL, "id": 2}),
        "gear/g1": (400, {}, {"message": "Bad Request"}),
    })
    conn = db.connect(tmp_path / "t.db")
    c = make_client(tmp_path, http, {"access_token": "ok", "refresh_token": "r", "expires_at": time.time() + 3600})
    result = strava_api.sync(conn, c, dump_dir=tmp_path / "dumps")
    assert result["imported"] == ["2"] and result["rate_limited"] is False
    from analysis import fitness
    assert fitness.get_settings(conn)["gear_names"] == {"g1": ""}
