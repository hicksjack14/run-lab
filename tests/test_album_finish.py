"""Finished albums: detection, saving album details from Spotify, and telling Crates."""
import json
import urllib.error
from datetime import datetime, timedelta

import pytest

import db
from analysis import albums
from ingest import crates_sync, spotify_live
from ingest.spotify_live import SpotifyClient
from tests.test_spotify_live import FakeHttp, client

BASE = datetime(2026, 10, 6, 20, 0, 0)
FMT = "%Y-%m-%dT%H:%M:%SZ"


def play(album_id="A1", n=1, total=5, end=BASE, frac=1.0, dur=200_000, kind="album", disc=1, album="Album One"):
    return {"album_id": album_id, "album": album, "artist": "Artist", "album_type": kind, "total_tracks": total,
            "track_number": n, "disc_number": disc, "duration_ms": dur, "ms_played": int(dur * frac), "end_utc": end.strftime(FMT)}


def whole(album_id="A1", total=5, start=BASE, step=timedelta(minutes=4), **kw):
    return [play(album_id, n, total, start + step * n, **kw) for n in range(1, total + 1)]


# ---------------------------------------------------------------- detection
def test_a_whole_album_is_finished_at_the_moment_the_last_track_ends():
    out = albums.find_finished_albums(whole())
    assert len(out) == 1 and out[0]["album_id"] == "A1" and out[0]["total_tracks"] == 5
    assert out[0]["finished_at"] == (BASE + timedelta(minutes=20)).strftime(FMT)


def test_order_does_not_matter_so_shuffle_counts():
    plays = whole()
    plays.reverse()
    for i, p in enumerate(plays):                      # same tracks, different play order
        p["end_utc"] = (BASE + timedelta(minutes=4 * (i + 1))).strftime(FMT)
    assert len(albums.find_finished_albums(plays)) == 1


def test_one_track_missing_means_not_finished():
    assert albums.find_finished_albums(whole()[:-1]) == []


def test_a_track_skipped_early_does_not_count_but_80_percent_does():
    plays = whole()
    plays[2] = play("A1", 3, 5, BASE + timedelta(minutes=12), frac=0.79)
    assert albums.find_finished_albums(plays) == []
    plays[2] = play("A1", 3, 5, BASE + timedelta(minutes=12), frac=0.80)
    assert len(albums.find_finished_albums(plays)) == 1


def test_window_is_48_hours_from_the_first_counted_track():
    plays = whole(step=timedelta(hours=11))            # spans 44 h: fine
    assert len(albums.find_finished_albums(plays)) == 1
    plays = whole(step=timedelta(hours=13))            # spans 52 h: too slow
    assert albums.find_finished_albums(plays) == []


def test_repeating_a_track_does_not_complete_the_album():
    plays = whole()[:-1] + [play("A1", 1, 5, BASE + timedelta(minutes=40))]
    assert albums.find_finished_albums(plays) == []


def test_singles_and_short_releases_are_ignored():
    assert albums.find_finished_albums(whole(kind="single")) == []
    assert albums.find_finished_albums(whole(total=3)) == []
    assert albums.find_finished_albums(whole(kind="compilation")) == []


def test_plays_without_album_details_are_ignored():
    old = [{**p, "album_id": None} for p in whole()]
    assert albums.find_finished_albums(old) == []
    assert albums.find_finished_albums([{**p, "track_number": None} for p in whole()]) == []


def test_two_discs_need_every_track_on_both():
    d1 = [play("D", n, 4, BASE + timedelta(minutes=4 * n), disc=1) for n in (1, 2)]
    d2 = [play("D", n, 4, BASE + timedelta(minutes=10 + 4 * n), disc=2) for n in (1, 2)]
    assert len(albums.find_finished_albums(d1 + d2)) == 1
    assert albums.find_finished_albums(d1 + [play("D", n, 4, BASE + timedelta(minutes=10 + 4 * n), disc=1) for n in (1, 2)]) == []


def test_a_full_second_listen_is_a_second_finish_but_plays_are_never_reused():
    first = whole()
    later = whole(start=BASE + timedelta(days=10))
    assert len(albums.find_finished_albums(first + later)) == 2
    replay_same_evening = whole(start=BASE + timedelta(hours=2))
    assert len(albums.find_finished_albums(first + replay_same_evening)) == 2        # five brand-new plays
    # but the first listen's own tracks can't be counted again toward a second finish
    assert len(albums.find_finished_albums(first + first[:2])) == 1


def test_two_albums_are_tracked_separately_and_sorted():
    out = albums.find_finished_albums(whole("B", start=BASE + timedelta(hours=1)) + whole("A1"))
    assert [f["album_id"] for f in out] == ["A1", "B"]


def test_local_date_uses_the_users_timezone():
    assert albums.listened_on("2026-10-06T02:30:00Z", "America/New_York") == "2026-10-05"   # still evening there
    assert albums.listened_on("2026-10-06T15:30:00Z", "America/New_York") == "2026-10-06"


# ---------------------------------------------------------------- saving album details from Spotify
def spotify_item(track, n, end, album_id="ALB1", total=5, dur_s=200):
    return {"played_at": end, "track": {"name": track, "type": "track", "uri": f"spotify:track:{track}", "duration_ms": dur_s * 1000,
            "artists": [{"name": "Artist"}], "track_number": n, "disc_number": 1,
            "album": {"id": album_id, "name": "Album One", "album_type": "album", "total_tracks": total}}}


def test_poll_saves_album_details_and_fills_them_in_for_plays_saved_earlier(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    # an earlier version saved this play without album details
    conn.execute("INSERT INTO plays (start_utc, end_utc, ms_played, track, artist, album, spotify_uri, source) VALUES (?,?,?,?,?,?,?, 'live')",
                 ("2026-10-06T20:00:00Z", "2026-10-06T20:03:20Z", 200000, "t1", "Artist", "Album One", "spotify:track:t1"))
    conn.commit()
    items = [spotify_item("t1", 1, "2026-10-06T20:03:20Z"), spotify_item("t2", 2, "2026-10-06T20:06:40Z")]
    c = client(tmp_path, FakeHttp({"recently-played": (200, {}, {"items": items})}))
    res = spotify_live.poll(conn, c)
    assert res["added"] == 1                                    # only t2 is new
    rows = {r["track"]: dict(r) for r in conn.execute("SELECT * FROM plays")}
    assert rows["t2"]["album_id"] == "ALB1" and rows["t2"]["total_tracks"] == 5 and rows["t2"]["track_number"] == 2
    assert rows["t2"]["duration_ms"] == 200000 and rows["t2"]["album_type"] == "album"
    assert rows["t1"]["album_id"] == "ALB1" and rows["t1"]["track_number"] == 1       # filled in afterwards


def test_existing_databases_gain_the_new_columns_without_losing_data(tmp_path):
    import sqlite3
    path = tmp_path / "old.db"
    old = sqlite3.connect(path)
    old.executescript("CREATE TABLE plays (id INTEGER PRIMARY KEY AUTOINCREMENT, start_utc TEXT NOT NULL, end_utc TEXT NOT NULL, ms_played INTEGER NOT NULL,"
                      " track TEXT, artist TEXT, album TEXT, spotify_uri TEXT, source TEXT NOT NULL DEFAULT 'export', UNIQUE (end_utc, spotify_uri));"
                      "INSERT INTO plays (start_utc, end_utc, ms_played, track) VALUES ('2026-01-01T00:00:00Z','2026-01-01T00:03:00Z',180000,'kept');")
    old.commit(); old.close()
    conn = db.connect(path)
    cols = {r["name"] for r in conn.execute("PRAGMA table_info(plays)")}
    assert {"album_id", "album_type", "total_tracks", "track_number", "disc_number", "duration_ms"} <= cols
    assert conn.execute("SELECT track FROM plays").fetchone()["track"] == "kept"
    assert conn.execute("SELECT COUNT(*) FROM album_finishes").fetchone()[0] == 0


# ---------------------------------------------------------------- recording finishes + telling Crates
def seed_album(conn, album_id="ALB1", total=5, end=BASE):
    for p in whole(album_id, total, start=end):
        conn.execute("INSERT INTO plays (start_utc, end_utc, ms_played, track, artist, album, spotify_uri, source, album_id, album_type,"
                     " total_tracks, track_number, disc_number, duration_ms) VALUES (?,?,?,?,?,?,?, 'live', ?,?,?,?,?,?)",
                     (p["end_utc"], p["end_utc"], p["ms_played"], f"t{p['track_number']}", "Artist", "Album One", f"u{album_id}{p['track_number']}",
                      album_id, "album", total, p["track_number"], 1, p["duration_ms"]))
    conn.commit()


CFG = {"url": "https://crates.example", "token": "x" * 40}
NOW = BASE + timedelta(hours=2)


class Crates:
    def __init__(self, *responses):
        self.responses, self.calls = list(responses), []

    def __call__(self, method, url, headers, data):
        self.calls.append((method, url, headers, json.loads(data)))
        r = self.responses.pop(0) if self.responses else (200, {"status": "logged"})
        if isinstance(r, Exception):
            raise r
        return r


def test_a_finished_album_is_recorded_once_and_sent_once(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    seed_album(conn)
    http = Crates((200, {"status": "logged"}))
    res = crates_sync.run(conn, CFG, http, now=NOW)
    assert res == {"new": 1, "configured": True, "sent": 1, "retry_later": 0, "refused": 0}
    method, url, headers, body = http.calls[0]
    assert (method, url) == ("POST", "https://crates.example/api/runlab/listened")
    assert headers["Authorization"] == "Bearer " + "x" * 40
    assert body == {"albumId": "ALB1", "listenedOn": "2026-10-06", "finishedAt": "2026-10-06T20:20:00Z"}
    again = crates_sync.run(conn, CFG, http, now=NOW)
    assert again["new"] == 0 and again["sent"] == 0 and len(http.calls) == 1        # never re-sent
    row = conn.execute("SELECT * FROM album_finishes").fetchone()
    assert row["synced_at"] and row["crates_status"] == "logged" and row["last_error"] is None


def test_nothing_is_sent_when_crates_is_not_set_up_but_finishes_are_still_recorded(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    seed_album(conn)
    res = crates_sync.run(conn, None, now=NOW)
    assert res["new"] == 1 and res["configured"] is False and res["sent"] == 0
    http = Crates()
    later = crates_sync.run(conn, CFG, http, now=NOW)                                # set up later: the backlog goes out
    assert later["sent"] == 1 and len(http.calls) == 1


def test_network_trouble_and_crates_being_down_are_retried_without_giving_up(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    seed_album(conn)
    for response in (urllib.error.URLError("offline"), (502, {"error": "couldn't look that album up right now"}), (500, "boom")):
        res = crates_sync.run(conn, CFG, Crates(response), now=NOW)
        assert res["retry_later"] == 1 and res["sent"] == 0
    row = conn.execute("SELECT * FROM album_finishes").fetchone()
    assert row["synced_at"] is None and row["attempts"] == 0                         # outages never use up the tries
    assert crates_sync.run(conn, CFG, Crates((200, {"status": "logged"})), now=NOW)["sent"] == 1


def test_a_rate_limit_stops_the_batch(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    seed_album(conn, "ALB1")
    seed_album(conn, "ALB2", end=BASE + timedelta(days=3))
    http = Crates((429, {"error": "slow down"}))
    res = crates_sync.run(conn, CFG, http, now=BASE + timedelta(days=3, hours=2))
    assert res["new"] == 2 and res["retry_later"] == 1 and len(http.calls) == 1


def test_refusals_are_counted_and_eventually_stop_being_retried(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    seed_album(conn)
    for _ in range(crates_sync.MAX_REFUSALS):
        res = crates_sync.run(conn, CFG, Crates((401, {"error": "unauthorized"})), now=NOW)
        assert res["refused"] == 1
    http = Crates()
    assert crates_sync.run(conn, CFG, http, now=NOW)["refused"] == 0 and http.calls == []   # stopped asking
    assert "401" in conn.execute("SELECT last_error FROM album_finishes").fetchone()["last_error"]


def test_two_listens_on_the_same_local_day_are_saved_once_so_crates_is_told_once(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    seed_album(conn)
    for p in whole(start=BASE + timedelta(hours=2)):          # a second full listen that evening
        conn.execute("INSERT INTO plays (start_utc, end_utc, ms_played, track, artist, album, spotify_uri, source, album_id, album_type,"
                     " total_tracks, track_number, disc_number, duration_ms) VALUES (?,?,?,?,?,?,?, 'live', ?,?,?,?,?,?)",
                     (p["end_utc"], p["end_utc"], p["ms_played"], "again", "Artist", "Album One", f"again{p['track_number']}",
                      "ALB1", "album", 5, p["track_number"], 1, p["duration_ms"]))
    conn.commit()
    assert crates_sync.record_finishes(conn, NOW + timedelta(hours=2)) == 1
    assert conn.execute("SELECT COUNT(*) FROM album_finishes").fetchone()[0] == 1


def test_old_plays_outside_the_lookback_are_not_reconsidered(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    seed_album(conn)
    res = crates_sync.run(conn, None, now=BASE + timedelta(days=crates_sync.LOOKBACK_DAYS + 2))
    assert res["new"] == 0


def test_env_loading_requires_https_and_both_values(tmp_path):
    env = tmp_path / ".env"
    assert crates_sync.load_env(env) is None
    env.write_text("CRATES_URL=https://crates.example/\nCRATES_TOKEN=abc\n")
    assert crates_sync.load_env(env) == {"url": "https://crates.example", "token": "abc"}
    env.write_text("CRATES_URL=http://crates.example\nCRATES_TOKEN=abc\n")
    with pytest.raises(SystemExit):
        crates_sync.load_env(env)
    env.write_text("CRATES_URL=http://localhost:3457\nCRATES_TOKEN=abc\n")
    assert crates_sync.load_env(env)["url"] == "http://localhost:3457"
    env.write_text("CRATES_URL=https://crates.example\n")
    assert crates_sync.load_env(env) is None


def test_check_reports_each_kind_of_answer():
    def answer(code):
        return lambda *a, **k: (code, {})
    assert "Connected" in crates_sync.check(CFG, answer(400))
    assert "rejected" in crates_sync.check(CFG, answer(401))
    assert "switched off" in crates_sync.check(CFG, answer(503))
    assert "deploy" in crates_sync.check(CFG, answer(404))
    assert "Not set up" in crates_sync.check(None)
