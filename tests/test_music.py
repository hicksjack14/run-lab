import json
from datetime import datetime, timedelta

import pytest

import db
from analysis import music_match
from ingest import spotify_import

# --- the real "Extended streaming history" shape (one entry per play; ts is when the play ENDED, in UTC)
EXTENDED = [
    {"ts": "2026-09-29T22:30:00Z", "platform": "iOS", "ms_played": 200_000, "conn_country": "US", "ip_addr": "1.2.3.4",
     "master_metadata_track_name": "Song A", "master_metadata_album_artist_name": "Artist X", "master_metadata_album_album_name": "Album 1",
     "spotify_track_uri": "spotify:track:aaa", "episode_name": None, "episode_show_name": None, "spotify_episode_uri": None,
     "reason_start": "trackdone", "reason_end": "trackdone", "shuffle": True, "skipped": False, "offline": False, "incognito_mode": False},
    {"ts": "2026-09-29T22:33:20Z", "ms_played": 5_000, "master_metadata_track_name": "Skipped", "master_metadata_album_artist_name": "Artist Y",
     "master_metadata_album_album_name": "Album 2", "spotify_track_uri": "spotify:track:skip", "episode_name": None},
    {"ts": "2026-09-29T22:40:00Z", "ms_played": 1_800_000, "master_metadata_track_name": None, "master_metadata_album_artist_name": None,
     "master_metadata_album_album_name": None, "spotify_track_uri": None, "episode_name": "A Podcast", "episode_show_name": "Show"},
]
LEGACY = [{"endTime": "2026-09-29 22:40", "artistName": "Old Artist", "trackName": "Old Song", "msPlayed": 180_000}]


def test_extended_history_import_skips_skips_and_podcasts(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    folder = tmp_path / "export" / "Spotify Extended Streaming History"
    folder.mkdir(parents=True)
    (folder / "Streaming_History_Audio_2026_0.json").write_text(json.dumps(EXTENDED))
    (folder / "Streaming_History_Video_2026.json").write_text(json.dumps([{"ts": "x"}]))   # ignored
    result = spotify_import.import_dir(conn, tmp_path / "export")
    assert result == {"files": 1, "added": 1, "skipped_short": 1, "skipped_other": 1}
    p = conn.execute("SELECT * FROM plays").fetchone()
    assert (p["track"], p["artist"], p["album"]) == ("Song A", "Artist X", "Album 1")
    assert p["end_utc"] == "2026-09-29T22:30:00Z" and p["start_utc"] == "2026-09-29T22:26:40Z"   # end minus ms_played
    assert p["ms_played"] == 200_000


def test_ip_address_is_never_stored(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    (tmp_path / "e").mkdir()
    (tmp_path / "e" / "Streaming_History_Audio_0.json").write_text(json.dumps(EXTENDED))
    spotify_import.import_dir(conn, tmp_path / "e")
    assert "1.2.3.4" not in json.dumps([dict(r) for r in conn.execute("SELECT * FROM plays")])


def test_import_is_idempotent(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    (tmp_path / "e").mkdir()
    (tmp_path / "e" / "Streaming_History_Audio_0.json").write_text(json.dumps(EXTENDED))
    spotify_import.import_dir(conn, tmp_path / "e")
    again = spotify_import.import_dir(conn, tmp_path / "e")
    assert again["added"] == 0 and conn.execute("SELECT COUNT(*) FROM plays").fetchone()[0] == 1


def test_legacy_account_data_format_also_imports(tmp_path):
    conn = db.connect(tmp_path / "t.db")
    (tmp_path / "e").mkdir()
    (tmp_path / "e" / "StreamingHistory0.json").write_text(json.dumps(LEGACY))
    assert spotify_import.import_dir(conn, tmp_path / "e")["added"] == 1
    p = conn.execute("SELECT * FROM plays").fetchone()
    assert (p["track"], p["artist"]) == ("Old Song", "Old Artist") and p["start_utc"] == "2026-09-29T22:37:00Z"


def test_missing_folder_is_a_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError):
        spotify_import.import_dir(db.connect(tmp_path / "t.db"), tmp_path / "nope")


# ---------------------------------------------------------------- matching songs to a run
RUN_START = datetime(2026, 9, 29, 22, 0, 0)


def add_run_with_streams(conn, rid="r1", seconds=1800):
    conn.execute("INSERT INTO runs (strava_id, name, start_local, start_utc, distance_m, moving_s, elapsed_s) VALUES (?,?,?,?,?,?,?)",
                 (rid, "Run", "2026-09-29T18:00:00", "2026-09-29T22:00:00Z", 5000, seconds, seconds))
    # first 15 minutes at 3.0 m/s and 140 bpm, last 15 at 2.0 m/s and 170 bpm
    for t in range(0, seconds + 1, 10):
        first = t < seconds / 2
        conn.execute("INSERT INTO run_streams (strava_id, t_s, hr, speed_mps, cadence_spm, distance_m, moving) VALUES (?,?,?,?,?,?,1)",
                     (rid, t, 140 if first else 170, 3.0 if first else 2.0, 170 if first else 160, t * 2.5))
    conn.commit()


def add_play(conn, start_offset_s, length_s, track, artist="Artist"):
    start = RUN_START + timedelta(seconds=start_offset_s)
    end = start + timedelta(seconds=length_s)
    conn.execute("INSERT INTO plays (start_utc, end_utc, ms_played, track, artist, album, spotify_uri) VALUES (?,?,?,?,?,?,?)",
                 (start.strftime("%Y-%m-%dT%H:%M:%SZ"), end.strftime("%Y-%m-%dT%H:%M:%SZ"), length_s * 1000, track, artist, "Album", f"uri:{track}"))
    conn.commit()


@pytest.fixture
def conn(tmp_path):
    c = db.connect(tmp_path / "t.db")
    add_run_with_streams(c)
    return c


def test_songs_are_placed_on_the_run_timeline_with_their_stats(conn):
    add_play(conn, 60, 240, "Early Song")        # inside the fast first half
    add_play(conn, 1200, 240, "Late Song")       # inside the slow second half
    songs = music_match.songs_for_run(conn, "r1")
    assert [s["track"] for s in songs] == ["Early Song", "Late Song"]
    early, late = songs
    assert (early["start_s"], early["end_s"]) == (60, 300)
    assert early["avg_hr"] == pytest.approx(140) and late["avg_hr"] == pytest.approx(170)
    assert early["avg_pace"] == pytest.approx(1609.344 / 3.0, rel=0.01)
    assert late["avg_pace"] > early["avg_pace"]            # slower later
    assert early["avg_cadence"] == pytest.approx(170)


def test_play_that_started_before_the_run_is_clipped(conn):
    add_play(conn, -100, 220, "Warm Up")         # 100 s before the run, runs 120 s into it
    s = music_match.songs_for_run(conn, "r1")[0]
    assert s["start_s"] == 0 and s["end_s"] == 120


def test_plays_outside_the_run_are_ignored(conn):
    add_play(conn, -1000, 200, "Before")
    add_play(conn, 5000, 200, "After")
    assert music_match.songs_for_run(conn, "r1") == []


def test_tiny_overlaps_are_dropped(conn):
    add_play(conn, -195, 200, "Barely")          # only 5 s overlap
    assert music_match.songs_for_run(conn, "r1") == []


def test_run_without_streams_returns_no_songs(conn):
    conn.execute("INSERT INTO runs (strava_id, name, start_local, start_utc, distance_m, moving_s, elapsed_s) VALUES ('r2','x','2026-09-29T18:00:00','2026-09-29T22:00:00Z',1,1,1)")
    conn.commit()
    assert music_match.songs_for_run(conn, "r2") == []


# ---------------------------------------------------------------- music findings
def test_artist_findings_need_enough_songs_and_report_direction():
    slices = []
    for i in range(10):
        slices.append({"artist": "Booster", "track": f"b{i}", "rel_ef": 0.04 + 0.002 * (i % 3), "seconds": 200, "run_id": f"r{i}"})
        slices.append({"artist": "Dragger", "track": f"d{i}", "rel_ef": -0.04 - 0.002 * (i % 3), "seconds": 200, "run_id": f"r{i}"})
        slices.append({"artist": "Rare", "track": f"x{i}", "rel_ef": 0.5, "seconds": 200, "run_id": "r0"} if i < 2 else {"artist": "Noise", "track": f"n{i}", "rel_ef": (-1) ** i * 0.05, "seconds": 200, "run_id": f"r{i}"})
    out = music_match.music_findings(slices)
    by_kind = {f["kind"]: f for f in out}
    assert "Booster" in by_kind["works"]["title"] and "Dragger" in by_kind["doesnt"]["title"]
    assert all("Rare" not in f["title"] for f in out)                       # only 2 songs: not reported
    assert all(f["confidence"] in ("low", "medium") for f in out)            # music never claims high confidence
