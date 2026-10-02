import sqlite3
from pathlib import Path

DB_PATH = Path(__file__).parent / "data" / "runlab.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs (
    strava_id        TEXT PRIMARY KEY,
    name             TEXT,
    start_local      TEXT NOT NULL,
    tz               TEXT NOT NULL DEFAULT 'America/New_York',
    start_utc        TEXT NOT NULL,
    distance_m       REAL,
    moving_s         INTEGER,
    elapsed_s        INTEGER,
    elevation_gain_m REAL,
    avg_hr           REAL,
    max_hr           REAL,
    avg_cadence_spm  REAL,
    effort           INTEGER,
    gear_id          TEXT,
    has_gps          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS run_streams (
    strava_id    TEXT NOT NULL REFERENCES runs(strava_id) ON DELETE CASCADE,
    t_s          INTEGER NOT NULL,
    hr           REAL,
    speed_mps    REAL,
    cadence_spm  REAL,
    distance_m   REAL,
    moving       INTEGER,
    lat          REAL,
    lng          REAL,
    altitude_m   REAL,
    PRIMARY KEY (strava_id, t_s)
);

CREATE TABLE IF NOT EXISTS run_laps (
    strava_id   TEXT NOT NULL REFERENCES runs(strava_id) ON DELETE CASCADE,
    idx         INTEGER NOT NULL,
    distance_m  REAL,
    moving_s    INTEGER,
    avg_hr      REAL,
    max_hr      REAL,
    PRIMARY KEY (strava_id, idx)
);

CREATE TABLE IF NOT EXISTS best_efforts (
    strava_id  TEXT NOT NULL REFERENCES runs(strava_id) ON DELETE CASCADE,
    type       TEXT NOT NULL,
    seconds    INTEGER NOT NULL,
    PRIMARY KEY (strava_id, type)
);

CREATE TABLE IF NOT EXISTS plays (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    start_utc   TEXT NOT NULL,
    end_utc     TEXT NOT NULL,
    ms_played   INTEGER NOT NULL,
    track       TEXT,
    artist      TEXT,
    album       TEXT,
    spotify_uri TEXT,
    UNIQUE (end_utc, spotify_uri)
);

CREATE INDEX IF NOT EXISTS idx_runs_start_utc ON runs(start_utc);
CREATE INDEX IF NOT EXISTS idx_plays_start_utc ON plays(start_utc);
"""


def connect(path=DB_PATH):
    """Open the database (creating it and its tables if needed)."""
    path = Path(path) if str(path) != ":memory:" else path
    if path != ":memory:":
        path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
