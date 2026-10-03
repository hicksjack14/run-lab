import base64
import hashlib
import json
import sqlite3
import time
from datetime import datetime, timedelta

import pytest

import db
from analysis import fitness
from ingest import spotify_import, spotify_live
from ingest.spotify_live import SpotifyClient, SpotifyRefused, RateLimited

CFG = {"client_id": "cid123"}


class FakeHttp:
    def __init__(self, routes):
        self.routes, self.calls = routes, []

    def __call__(self, method, url, headers=None, data=None):
        self.calls.append((method, url, data))
        for key, resp in self.routes.items():
            if key in url:
                return resp(url) if callable(resp) else resp
        raise AssertionError(f"unexpected request {url}")


def client(tmp_path, http, token=True):
    store = tmp_path / "tok.json"
    if token:
        store.write_text(json.dumps({"access_token": "ok", "refresh_token": "r1", "expires_at": time.time() + 3600}))
    return SpotifyClient(CFG, store, http=http)


def item(track, artist, end, dur_s=200, uri=None, kind="track"):
    return {"played_at": end, "track": {"name": track, "type": kind, "uri": uri or f"spotify:track:{track}", "duration_ms": dur_s * 1000,
                                         "artists": [{"name": artist}], "album": {"name": "Album"}}}


# ---------------------------------------------------------------- sign-in
def test_auth_url_uses_pkce_loopback_redirect_and_the_one_scope(tmp_path):
    c = client(tmp_path, FakeHttp({}), token=False)
    url, verifier = c.auth_url_and_verifier()
    assert "redirect_uri=http%3A%2F%2F127.0.0.1%3A5059%2Fcallback" in url and "localhost" not in url
    assert "scope=user-read-recently-played" in url and "code_challenge_method=S256" in url and "client_id=cid123" in url
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert f"code_challenge={challenge}" in url
    assert 43 <= len(verifier) <= 128


def test_code_exchange_saves_private_token_file(tmp_path):
    http = FakeHttp({"api/token": (200, {}, {"access_token": "a", "refresh_token": "r", "expires_in": 3600})})
    c = client(tmp_path, http, token=False)
    c.exchange_code("thecode", "verifier123")
    saved = json.loads((tmp_path / "tok.json").read_text())
    assert saved["access_token"] == "a" and saved["refresh_token"] == "r" and saved["expires_at"] > time.time()
    body = http.calls[0][2]
    assert "grant_type=authorization_code" in body and "code_verifier=verifier123" in body and "client_secret" not in body
    assert oct((tmp_path / "tok.json").stat().st_mode)[-3:] == "600"


def test_expired_token_refreshes_and_keeps_old_refresh_token_if_none_returned(tmp_path):
    http = FakeHttp({"api/token": (200, {}, {"access_token": "new", "expires_in": 3600})})
    c = client(tmp_path, http, token=False)
    (tmp_path / "tok.json").write_text(json.dumps({"access_token": "old", "refresh_token": "keepme", "expires_at": time.time() - 5}))
    assert c.access_token() == "new"
    assert json.loads((tmp_path / "tok.json").read_text())["refresh_token"] == "keepme"


def test_not_signed_in_gives_a_helpful_message(tmp_path):
    with pytest.raises(SystemExit, match="auth"):
        client(tmp_path, FakeHttp({}), token=False).access_token()


# ---------------------------------------------------------------- polling
@pytest.fixture
def conn(tmp_path):
    return db.connect(tmp_path / "t.db")


def recent(items):
    return lambda url: (200, {}, {"items": items})


def test_poll_stores_songs_as_live_plays_with_start_derived_from_duration(tmp_path, conn):
    items = [item("B", "Artist 2", "2026-10-03T21:10:00.500Z", 180), item("A", "Artist 1", "2026-10-03T21:00:00.000Z", 200)]   # API order: newest first
    c = client(tmp_path, FakeHttp({"recently-played": recent(items)}))
    assert spotify_live.poll(conn, c) == {"added": 2, "rate_limited": False}
    rows = conn.execute("SELECT * FROM plays ORDER BY end_utc").fetchall()
    assert [(r["track"], r["artist"], r["source"]) for r in rows] == [("A", "Artist 1", "live"), ("B", "Artist 2", "live")]
    assert rows[0]["end_utc"] == "2026-10-03T21:00:00Z" and rows[0]["start_utc"] == "2026-10-03T20:56:40Z"   # end minus 200 s
    assert rows[1]["ms_played"] == 180_000


def test_polling_again_adds_nothing_new(tmp_path, conn):
    items = [item("A", "Artist 1", "2026-10-03T21:00:00.000Z")]
    c = client(tmp_path, FakeHttp({"recently-played": recent(items)}))
    spotify_live.poll(conn, c)
    assert spotify_live.poll(conn, c)["added"] == 0
    assert conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0] == 1


def test_a_song_skipped_early_is_clipped_to_when_the_previous_one_ended(tmp_path, conn):
    # B is 240 s long but ended only 60 s after A did, so it can't have started before A ended
    items = [item("B", "X", "2026-10-03T21:04:00.000Z", 240), item("A", "X", "2026-10-03T21:03:00.000Z", 180)]
    spotify_live.poll(conn, client(tmp_path, FakeHttp({"recently-played": recent(items)})))
    b = conn.execute("SELECT * FROM plays WHERE track = 'B'").fetchone()
    assert b["start_utc"] == "2026-10-03T21:03:00Z" and b["ms_played"] == 60_000


def test_episodes_and_empty_tracks_are_ignored(tmp_path, conn):
    items = [item("Podcast", "Show", "2026-10-03T21:00:00.000Z", kind="episode"), {"played_at": "2026-10-03T21:05:00.000Z", "track": None}]
    assert spotify_live.poll(conn, client(tmp_path, FakeHttp({"recently-played": recent(items)})))["added"] == 0


def test_played_at_can_be_switched_to_mean_start(tmp_path, conn):
    fitness.set_setting(conn, "spotify_played_at", "start")
    items = [item("A", "X", "2026-10-03T21:00:00.000Z", 200)]
    spotify_live.poll(conn, client(tmp_path, FakeHttp({"recently-played": recent(items)})))
    p = conn.execute("SELECT * FROM plays").fetchone()
    assert p["start_utc"] == "2026-10-03T21:00:00Z" and p["end_utc"] == "2026-10-03T21:03:20Z"


def test_rate_limit_stops_cleanly(tmp_path, conn):
    c = client(tmp_path, FakeHttp({"recently-played": (429, {"Retry-After": "30"}, {})}))
    assert spotify_live.poll(conn, c) == {"added": 0, "rate_limited": True}


def test_forbidden_explains_premium_and_user_list(tmp_path, conn):
    c = client(tmp_path, FakeHttp({"recently-played": (403, {}, {"error": {"message": "Forbidden"}})}))
    with pytest.raises(SpotifyRefused, match="Premium"):
        spotify_live.poll(conn, c)


def test_expired_login_asks_to_sign_in_again(tmp_path, conn):
    c = client(tmp_path, FakeHttp({"recently-played": (401, {}, {})}))
    with pytest.raises(SystemExit, match="auth"):
        spotify_live.poll(conn, c)


# ---------------------------------------------------------------- live data vs the real export
def test_export_replaces_live_plays_for_the_period_it_covers(tmp_path, conn):
    spotify_live.poll(conn, client(tmp_path, FakeHttp({"recently-played": recent([
        item("OldLive", "X", "2026-09-29T22:30:00.000Z"), item("NewLive", "X", "2026-10-05T12:00:00.000Z")])})))
    folder = tmp_path / "export"
    folder.mkdir()
    (folder / "Streaming_History_Audio_2026_0.json").write_text(json.dumps([
        {"ts": "2026-09-29T22:29:50Z", "ms_played": 200_000, "master_metadata_track_name": "FromExport", "master_metadata_album_artist_name": "X",
         "master_metadata_album_album_name": "Alb", "spotify_track_uri": "spotify:track:fe"},
        {"ts": "2026-09-30T10:00:00Z", "ms_played": 200_000, "master_metadata_track_name": "Second", "master_metadata_album_artist_name": "X",
         "master_metadata_album_album_name": "Alb", "spotify_track_uri": "spotify:track:s2"}]))
    spotify_import.import_dir(conn, folder)
    tracks = {r["track"]: r["source"] for r in conn.execute("SELECT track, source FROM plays")}
    assert tracks == {"FromExport": "export", "Second": "export", "NewLive": "live"}        # the live play inside the export's period is gone; later ones stay


def test_old_databases_get_the_source_column(tmp_path):
    path = tmp_path / "old.db"
    raw = sqlite3.connect(path)
    raw.execute("CREATE TABLE plays (id INTEGER PRIMARY KEY AUTOINCREMENT, start_utc TEXT NOT NULL, end_utc TEXT NOT NULL, ms_played INTEGER NOT NULL, "
                "track TEXT, artist TEXT, album TEXT, spotify_uri TEXT, UNIQUE (end_utc, spotify_uri))")
    raw.execute("INSERT INTO plays (start_utc, end_utc, ms_played, track, artist, album, spotify_uri) VALUES ('a','b',1,'t','x','y','u')")
    raw.commit(); raw.close()
    conn = db.connect(path)
    assert conn.execute("SELECT source FROM plays").fetchone()[0] == "export"        # existing rows count as export data
