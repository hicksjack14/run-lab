import pytest

import db
from ingest.strava_import import import_dump
from server import create_app
from tests.test_strava_import import DUMP


@pytest.fixture
def client(tmp_path):
    path = tmp_path / "test.db"
    conn = db.connect(path)
    import_dump(conn, DUMP)
    conn.close()
    return create_app(path).test_client()


def test_list_runs_newest_first_with_summary(client):
    runs = client.get("/api/runs").get_json()
    assert len(runs) == 1
    assert runs[0]["id"] == "20385623675"
    assert runs[0]["distance_m"] == 6934
    assert runs[0]["has_gps"] == 1


def test_run_detail_has_aligned_stream_columns(client):
    body = client.get("/api/runs/20385623675").get_json()
    s = body["streams"]
    assert body["run"]["has_gps"] is True
    assert s["t"] == [2, 101, 158, 214]
    assert s["hr"] == [101, 126, 135, 137]
    assert s["moving"] == [False, True, True, True]
    assert s["lat"][0] == 43.05 and s["lng"][0] == -76.15
    assert len({len(v) for v in s.values()}) == 1
    assert len(body["laps"]) == 2


def test_unknown_run_is_404(client):
    assert client.get("/api/runs/nope").status_code == 404
