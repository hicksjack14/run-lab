import json
import time
import urllib.parse
from datetime import datetime, timedelta, timezone

import pytest

import db
from analysis import fitness
from ingest import strava_post
from ingest.strava_api import StravaClient
from ingest.strava_post import HEADER, WriteNotAllowed

START = datetime(2026, 10, 6, 21, 0, tzinfo=timezone.utc)          # a run from 5:00 PM New York time, 40 minutes long
FMT = "%Y-%m-%dT%H:%M:%SZ"


class FakeStrava:
    def __init__(self, description="", put_status=200):
        self.description, self.put_status, self.puts = description, put_status, []

    def __call__(self, method, url, headers=None, data=None):
        if method == "GET":
            return 200, {}, {"id": 1, "description": self.description}
        self.puts.append(urllib.parse.parse_qs(data)["description"][0])
        return self.put_status, {}, {} if self.put_status == 200 else {"message": "Authorization Error"}


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    c.execute("INSERT INTO runs (strava_id, name, start_local, start_utc, distance_m, moving_s, elapsed_s) VALUES ('1','Evening Run','2026-10-06T17:00:00',?,6000,2400,2400)",
              (START.strftime(FMT),))
    for t in range(0, 2401, 10):
        c.execute("INSERT INTO run_streams (strava_id, t_s, hr, speed_mps, distance_m, moving) VALUES ('1',?,150,2.5,?,1)", (t, t * 2.5))
    songs = [("Warmup Song", "Artist A", 0, 200), ("Second Song", None, 200, 400), ("Third Song", "Artist C", 600, 300)]
    for name, artist, off, length in songs:
        s = START + timedelta(seconds=off)
        c.execute("INSERT INTO plays (start_utc, end_utc, ms_played, track, artist, album, spotify_uri, source) VALUES (?,?,?,?,?,?,?, 'live')",
                  (s.strftime(FMT), (s + timedelta(seconds=length)).strftime(FMT), length * 1000, name, artist, "Alb", f"uri:{name}"))
    c.commit()
    return c


def client(tmp_path, http):
    store = tmp_path / "tok.json"
    store.write_text(json.dumps({"access_token": "ok", "refresh_token": "r", "expires_at": time.time() + 3600}))
    return StravaClient({"client_id": "1", "client_secret": "s"}, store, http=http)


def turn_on(conn, since="2026-10-06"):
    fitness.set_setting(conn, "song_posts", {"enabled": True, "since": since, "done": {}})


AFTER = START + timedelta(minutes=40 + 46)        # 46 minutes after the run ended


def test_description_lists_songs_in_order_with_artists():
    text = strava_post.format_description([{"track": "A", "artist": "X"}, {"track": "B", "artist": None}, {"track": "C", "artist": "Z"}])
    assert text == f"{HEADER}\n1. A - X\n2. B\n3. C - Z"


def test_a_very_long_list_is_cut_with_a_count():
    songs = [{"track": f"Song number {i} with a fairly long title", "artist": "Some Artist"} for i in range(200)]
    text = strava_post.format_description(songs)
    assert len(text) < 1800 and text.splitlines()[-1].startswith("+") and text.endswith("more")


def test_nothing_is_posted_until_switched_on(tmp_path, conn):
    http = FakeStrava()
    assert strava_post.post_ready(conn, client(tmp_path, http), now=AFTER) == [] and http.puts == []


def test_posts_the_songs_once_keeping_the_description_already_there(tmp_path, conn):
    turn_on(conn)
    http = FakeStrava(description="Felt great today")
    c = client(tmp_path, http)
    assert strava_post.post_ready(conn, c, now=AFTER, log=lambda *_: None) == ["1"]
    assert http.puts[0] == f"Felt great today\n\n{HEADER}\n1. Warmup Song - Artist A\n2. Second Song\n3. Third Song - Artist C"
    assert strava_post.post_ready(conn, c, now=AFTER, log=lambda *_: None) == [] and len(http.puts) == 1        # not twice


def test_waits_until_45_minutes_after_the_run_ends(tmp_path, conn):
    turn_on(conn)
    http = FakeStrava()
    assert strava_post.post_ready(conn, client(tmp_path, http), now=START + timedelta(minutes=40 + 30)) == [] and http.puts == []


def test_older_runs_and_runs_before_the_switch_date_are_left_alone(tmp_path, conn):
    http = FakeStrava()
    turn_on(conn, since="2026-10-07")                                                         # the run is from the 6th
    assert strava_post.post_ready(conn, client(tmp_path, http), now=AFTER) == []
    turn_on(conn)
    assert strava_post.post_ready(conn, client(tmp_path, http), now=START + timedelta(days=4)) == [] and http.puts == []


def test_a_description_that_already_has_the_list_is_not_touched(tmp_path, conn):
    turn_on(conn)
    http = FakeStrava(description=f"{HEADER}\n1. Old")
    strava_post.post_ready(conn, client(tmp_path, http), now=AFTER, log=lambda *_: None)
    assert http.puts == [] and "1" in fitness.get_settings(conn)["song_posts"]["done"]


def test_runs_with_no_saved_songs_are_retried_later(tmp_path, conn):
    turn_on(conn)
    conn.execute("DELETE FROM plays")
    conn.commit()
    http = FakeStrava()
    assert strava_post.post_ready(conn, client(tmp_path, http), now=AFTER) == [] and http.puts == []
    assert fitness.get_settings(conn)["song_posts"]["done"] == {}


def test_missing_write_permission_gives_a_clear_message(tmp_path, conn):
    turn_on(conn)
    with pytest.raises(WriteNotAllowed, match="auth"):
        strava_post.post_ready(conn, client(tmp_path, FakeStrava(put_status=401)), now=AFTER)
