"""Run Lab web server. Local only: binds to 127.0.0.1."""
from pathlib import Path

from flask import Flask, abort, jsonify, send_from_directory

import db

WEB_DIR = Path(__file__).parent / "web"
STREAM_COLUMNS = {
    "t": "t_s", "hr": "hr", "speed": "speed_mps", "cadence": "cadence_spm",
    "dist": "distance_m", "moving": "moving", "lat": "lat", "lng": "lng", "alt": "altitude_m",
}


def create_app(db_path=db.DB_PATH):
    app = Flask(__name__, static_folder=None)

    def conn():
        return db.connect(db_path)

    @app.get("/api/runs")
    def list_runs():
        rows = conn().execute(
            """SELECT strava_id AS id, name, start_local, start_utc, tz, distance_m, moving_s,
                      elapsed_s, avg_hr, max_hr, avg_cadence_spm, elevation_gain_m, has_gps
               FROM runs ORDER BY start_utc DESC"""
        ).fetchall()
        return jsonify([dict(r) for r in rows])

    @app.get("/api/runs/<run_id>")
    def get_run(run_id):
        c = conn()
        run = c.execute("SELECT * FROM runs WHERE strava_id = ?", (run_id,)).fetchone()
        if run is None:
            abort(404)
        cols = ", ".join(STREAM_COLUMNS.values())
        rows = c.execute(
            f"SELECT {cols} FROM run_streams WHERE strava_id = ? ORDER BY t_s", (run_id,)
        ).fetchall()
        streams = {key: [r[col] for r in rows] for key, col in STREAM_COLUMNS.items()}
        streams["moving"] = [None if v is None else bool(v) for v in streams["moving"]]
        laps = c.execute(
            "SELECT idx, distance_m, moving_s, avg_hr, max_hr FROM run_laps WHERE strava_id = ? ORDER BY idx",
            (run_id,),
        ).fetchall()
        return jsonify({
            "run": {**dict(run), "id": run["strava_id"], "has_gps": bool(run["has_gps"])},
            "streams": streams,
            "laps": [dict(r) for r in laps],
        })

    @app.get("/")
    def index():
        return send_from_directory(WEB_DIR, "index.html")

    @app.get("/<path:filename>")
    def static_files(filename):
        return send_from_directory(WEB_DIR, filename)

    return app


if __name__ == "__main__":
    create_app().run(host="127.0.0.1", port=5057, debug=False)
