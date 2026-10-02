"""Run Lab web server. Local only: binds to 127.0.0.1.

    .venv/bin/python server.py          # real data
    .venv/bin/python server.py --demo   # fake demo data (data/demo.db; make it with python -m tools.make_demo_data)
"""
import json
import os
import re
import sys
import threading
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from flask import Flask, Response, abort, g, jsonify, request, send_from_directory

import db
from analysis import fitness, ics, insights, music_match, places, plans, zones
from analysis.zones import MI

WEB_DIR = Path(__file__).parent / "web"
STREAM_COLUMNS = {
    "t": "t_s", "hr": "hr", "speed": "speed_mps", "cadence": "cadence_spm",
    "dist": "distance_m", "moving": "moving", "lat": "lat", "lng": "lng", "alt": "altitude_m",
}
RUN_FIELDS = ("strava_id AS id, name, start_local, start_utc, tz, distance_m, moving_s, elapsed_s, avg_hr, max_hr, "
              "avg_cadence_spm, elevation_gain_m, effort, gear_id, has_gps")


def route_glyph(c, run_id, n=40):
    """A thin sample of a run's GPS path, for drawing a small route thumbnail."""
    rows = c.execute("SELECT lat, lng FROM run_streams WHERE strava_id = ? AND lat IS NOT NULL ORDER BY t_s", (run_id,)).fetchall()
    if len(rows) < 8:
        return None
    step = max(1, len(rows) // n)
    return [[r[0], r[1]] for r in rows[::step]]


def create_app(db_path=None, today=None):
    app = Flask(__name__, static_folder=None)
    path = db.default_path() if db_path is None else db_path
    get_today = today or date.today
    cache = {}
    sync_state = {"running": False, "imported": [], "error": None, "rate_limited": False, "finished": None}

    @app.after_request
    def always_revalidate_files(resp):
        # this is a local dev-style app: make the browser re-check pages/scripts so an update shows up on the next reload
        if not request.path.startswith("/api/"):
            resp.headers["Cache-Control"] = "no-cache"
        return resp

    def conn():
        if "conn" not in g:
            g.conn = db.connect(path)
        return g.conn

    @app.teardown_appcontext
    def close_conn(_exc):
        c = g.pop("conn", None)
        if c is not None:
            c.close()

    def is_demo():
        return Path(str(path)).name == "demo.db"

    def analytics():
        c = conn()
        stamp = (c.execute("SELECT COUNT(*), COALESCE(MAX(start_local), '') FROM runs").fetchone()[:2],
                 json.dumps(fitness.get_settings(c), sort_keys=True), get_today().isoformat())
        if cache.get("stamp") != stamp:
            cache["stamp"], cache["value"] = stamp, insights.analyze(c, get_today())
        return cache["value"]

    # ------------------------------------------------------------------ meta
    @app.get("/api/meta")
    def meta():
        c = conn()
        token = db.DATA_DIR / "strava_token.json"
        return jsonify({"demo": is_demo(), "today": get_today().isoformat(),
                        "runs": c.execute("SELECT COUNT(*) FROM runs").fetchone()[0],
                        "plays": c.execute("SELECT COUNT(*) FROM plays").fetchone()[0],
                        "strava_connected": token.exists() and not is_demo()})

    # ------------------------------------------------------------------ runs
    @app.get("/api/runs")
    def list_runs():
        rows = conn().execute(f"SELECT {RUN_FIELDS} FROM runs ORDER BY start_utc DESC").fetchall()
        gear = fitness.get_settings(conn()).get("gear_names", {})
        return jsonify([{**dict(r), "has_gps": bool(r["has_gps"]), "gear": gear.get(r["gear_id"])} for r in rows])

    @app.get("/api/runs/<run_id>")
    def get_run(run_id):
        c = conn()
        run = c.execute("SELECT * FROM runs WHERE strava_id = ?", (run_id,)).fetchone()
        if run is None:
            abort(404)
        cols = ", ".join(STREAM_COLUMNS.values())
        rows = c.execute(f"SELECT {cols} FROM run_streams WHERE strava_id = ? ORDER BY t_s", (run_id,)).fetchall()
        streams = {key: [r[col] for r in rows] for key, col in STREAM_COLUMNS.items()}
        streams["moving"] = [None if v is None else bool(v) for v in streams["moving"]]
        laps = c.execute("SELECT idx, distance_m, moving_s, avg_hr, max_hr FROM run_laps WHERE strava_id = ? ORDER BY idx", (run_id,)).fetchall()
        efforts = c.execute("SELECT type, seconds FROM best_efforts WHERE strava_id = ?", (run_id,)).fetchall()
        snap = fitness.snapshot(c, get_today())
        zone_secs = None
        if snap["max_hr"] and rows:
            samples = [(r["t_s"], r["hr"], r["speed_mps"], r["distance_m"], r["moving"]) for r in rows]
            zone_secs = insights._stream_metrics(samples, snap["max_hr"])["zone_secs"]
        prev_id = c.execute("SELECT strava_id FROM runs WHERE start_utc < ? ORDER BY start_utc DESC LIMIT 1", (run["start_utc"],)).fetchone()
        next_id = c.execute("SELECT strava_id FROM runs WHERE start_utc > ? ORDER BY start_utc ASC LIMIT 1", (run["start_utc"],)).fetchone()
        gear = fitness.get_settings(c).get("gear_names", {})
        return jsonify({
            "run": {**dict(run), "id": run["strava_id"], "has_gps": bool(run["has_gps"]), "gear": gear.get(run["gear_id"])},
            "streams": streams, "laps": [dict(r) for r in laps], "best_efforts": [dict(r) for r in efforts],
            "songs": music_match.songs_for_run(c, run_id),
            "zone_secs": zone_secs, "max_hr": snap["max_hr"], "hr_zones": snap["hr_zones"],
            "prev": prev_id[0] if prev_id else None, "next": next_id[0] if next_id else None,
        })

    # ------------------------------------------------------------------ fitness + settings
    @app.get("/api/fitness")
    def get_fitness():
        c = conn()
        snap = fitness.snapshot(c, get_today())
        snap["weekly"] = fitness.weekly_miles(c, get_today(), 12)
        snap["settings"] = fitness.get_settings(c)
        return jsonify(snap)

    @app.post("/api/settings")
    def post_settings():
        body = request.get_json(force=True) or {}
        for key in ("max_hr", "vdot_override"):
            if key in body:
                v = body[key]
                if v is not None:
                    try:
                        v = float(v)
                    except (TypeError, ValueError):
                        return jsonify({"error": f"{key} must be a number"}), 400
                    if not (100 <= v <= 240 if key == "max_hr" else 15 <= v <= 85):
                        return jsonify({"error": f"{key} is out of range"}), 400
                fitness.set_setting(conn(), key, v)
        return get_fitness()

    # ------------------------------------------------------------------ plans
    def active_plan_row():
        return conn().execute("SELECT * FROM plans WHERE active = 1 ORDER BY id DESC LIMIT 1").fetchone()

    def plan_response(row):
        payload = json.loads(row["payload"])
        today = get_today()
        workouts = fitness.adherence(conn(), payload["workouts"], today)
        past = [w for w in workouts if w["status"] in ("done", "partial", "missed")]
        stats = {
            "done": sum(1 for w in workouts if w["status"] == "done"),
            "partial": sum(1 for w in workouts if w["status"] == "partial"),
            "missed": sum(1 for w in workouts if w["status"] == "missed"),
            "upcoming": sum(1 for w in workouts if w["status"] in ("upcoming", "today")),
            "planned_mi_to_date": round(sum(w["distance_mi"] for w in past), 1),
            "actual_mi_to_date": round(sum(w["actual_mi"] for w in past), 1),
            "total": len(workouts),
        }
        nxt = next((w for w in workouts if w["status"] in ("upcoming", "today")), None)
        # goal_time_s comes from the payload: it is the time actually planned for (his goal, or the projection if he gave none)
        return {"plan": {**{k: row[k] for k in ("id", "created_at", "goal", "race_date", "start_date", "days_per_week", "long_run_dow")},
                         **{k: payload[k] for k in ("weeks", "warnings", "vdot", "projected_time_s", "race_distance_m", "goal_time_s")}},
                "workouts": workouts, "stats": stats, "next": nxt,
                "days_to_race": (date.fromisoformat(row["race_date"]) - today).days}

    @app.get("/api/plan")
    def get_plan():
        row = active_plan_row()
        return jsonify(plan_response(row) if row else {"plan": None})

    @app.post("/api/plan")
    def post_plan():
        body = request.get_json(force=True) or {}
        goal = body.get("goal")
        try:
            goal = goal if goal in plans.DISTANCES else float(goal)
            race_date = date.fromisoformat(body["race_date"])
            start = date.fromisoformat(body["start_date"]) if body.get("start_date") else get_today()
            days = int(body.get("days_per_week", 4))
            long_dow = int(body.get("long_run_dow", 6))
            goal_time = float(body["goal_time_s"]) if body.get("goal_time_s") else None
        except (KeyError, TypeError, ValueError):
            return jsonify({"error": "Need a goal (5K, 10K, Half marathon, Marathon), a race date, and valid numbers."}), 400
        if long_dow not in (5, 6):
            return jsonify({"error": "The long run can be on Saturday or Sunday."}), 400
        snap = fitness.snapshot(conn(), get_today())
        vdot = float(body["vdot"]) if body.get("vdot") else snap["vdot"]
        if not vdot:
            return jsonify({"error": "Not enough data to set paces yet.", "needs": snap["needs"]}), 422
        try:
            plan = plans.generate_plan(goal, race_date, start, snap["recent_weekly_mi"], vdot, days_per_week=days,
                                       long_run_dow=long_dow, goal_time_s=goal_time)
        except ValueError as e:
            return jsonify({"error": str(e)}), 400
        c = conn()
        c.execute("UPDATE plans SET active = 0")
        c.execute("INSERT INTO plans (created_at, active, goal, race_date, goal_time_s, start_date, days_per_week, long_run_dow, payload)"
                  " VALUES (?,?,?,?,?,?,?,?,?)",
                  (datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z", 1, plan["goal"], plan["race_date"],
                   goal_time, plan["start_date"], plan["days_per_week"], long_dow, json.dumps(plan)))
        c.commit()
        return jsonify(plan_response(active_plan_row())), 201

    @app.delete("/api/plan")
    def delete_plan():
        conn().execute("UPDATE plans SET active = 0")
        conn().commit()
        return jsonify({"plan": None})

    @app.get("/api/plan.ics")
    def plan_ics():
        row = active_plan_row()
        if not row:
            abort(404)
        time = request.args.get("time", "17:00")
        if not re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", time):
            return jsonify({"error": "time must look like 17:00"}), 400
        payload = json.loads(row["payload"])
        text = ics.to_ics(payload["workouts"], f"Run Lab: {row['goal']} {row['race_date']}", plan_id=f"rl{row['id']}", start_time=time)
        name = f"run-lab-{row['goal'].lower().replace(' ', '-')}-{row['race_date']}.ics"
        return Response(text, mimetype="text/calendar", headers={"Content-Disposition": f'attachment; filename="{name}"'})

    # ------------------------------------------------------------------ places (where he runs)
    @app.get("/api/places")
    def get_places():
        c = conn()
        stamp = ("places", c.execute("SELECT COUNT(*), COALESCE(MAX(start_local), '') FROM runs").fetchone()[:2])
        if cache.get("places_stamp") != stamp:
            rows = c.execute("SELECT strava_id, start_local, distance_m FROM runs WHERE has_gps = 1 ORDER BY start_local").fetchall()
            runs = [{"id": r["strava_id"], "date": date.fromisoformat(r["start_local"][:10]), "dist_mi": r["distance_m"] / MI} for r in rows]
            routes = insights._routes(c, runs, limit=1000, points=120)
            cache["places_stamp"], cache["places"] = stamp, {"routes": routes, **places.analyze(routes)}
        return jsonify(cache["places"])

    # ------------------------------------------------------------------ analytics + home
    @app.get("/api/analytics")
    def get_analytics():
        return jsonify(analytics())

    @app.get("/api/home")
    def home():
        c = conn()
        today = get_today()
        monday = today - timedelta(days=today.weekday())
        weeks = fitness.weekly_miles(c, today, 2)
        runs_this_week = c.execute("SELECT COUNT(*) FROM runs WHERE substr(start_local, 1, 10) >= ?", (monday.isoformat(),)).fetchone()[0]
        recent = c.execute(f"SELECT {RUN_FIELDS} FROM runs ORDER BY start_utc DESC LIMIT 6").fetchall()
        snap = fitness.snapshot(c, today)
        row = active_plan_row()
        plan = plan_response(row) if row else None
        coach = None
        found = analytics()["findings"]
        for kind in ("improve", "works"):
            hit = next((f for f in found if f["kind"] == kind and f["confidence"] != "low"), None)
            if hit:
                coach = hit
                break
        return jsonify({
            "recent": [{**dict(r), "has_gps": bool(r["has_gps"]), "glyph": route_glyph(c, r["id"])} for r in recent],
            "week": {"miles": weeks[-1]["miles"], "last_miles": weeks[-2]["miles"], "runs": runs_this_week, "start": monday.isoformat()},
            "plan": plan, "fitness": {k: snap[k] for k in ("vdot", "paces", "predictions", "prediction_text", "max_hr", "needs")},
            "coach": coach, "today": today.isoformat(),
        })

    # ------------------------------------------------------------------ strava sync (background thread)
    @app.post("/api/sync")
    def start_sync():
        if is_demo():
            return jsonify({"error": "Demo mode: sync is disabled so fake data never mixes with your real runs."}), 400
        if sync_state["running"]:
            return jsonify(sync_state), 202
        from ingest import strava_api
        try:
            client = strava_api.StravaClient(strava_api.load_env())
            client.access_token()
        except SystemExit as e:
            return jsonify({"error": str(e)}), 400

        def work():
            try:
                res = strava_api.sync(db.connect(path), client, log=lambda *_: None)
                sync_state.update(imported=res["imported"], rate_limited=res["rate_limited"], error=None)
            except Exception as e:  # report to the UI instead of dying silently
                sync_state.update(error=str(e))
            finally:
                sync_state.update(running=False, finished=datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds") + "Z")

        sync_state.update(running=True, imported=[], error=None, rate_limited=False, finished=None)
        threading.Thread(target=work, daemon=True).start()
        return jsonify(sync_state), 202

    @app.get("/api/sync")
    def sync_status():
        return jsonify(sync_state)

    # ------------------------------------------------------------------ static
    @app.get("/")
    def index():
        return send_from_directory(WEB_DIR, "index.html")

    @app.get("/<path:filename>")
    def static_files(filename):
        return send_from_directory(WEB_DIR, filename)

    return app


if __name__ == "__main__":
    if "--demo" in sys.argv:
        os.environ["RUNLAB_DB"] = "demo"
        if not db.DEMO_PATH.exists():
            sys.exit("No demo data yet. Run: .venv/bin/python -m tools.make_demo_data")
    create_app().run(host="127.0.0.1", port=5057, debug=False)
