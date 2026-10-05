"""Export a read-only snapshot of Run Lab to docs/, ready for GitHub Pages.

    .venv/bin/python -m tools.export_static             # real data, GPS trimmed 400 m at both ends of every route
    .venv/bin/python -m tools.export_static --no-trim   # full routes
    .venv/bin/python -m tools.export_static --demo      # fake demo data (to try the snapshot safely)

The snapshot is produced by running the app's own API over a temporary copy of the database, so every number
matches the live app. Your real database is never modified. The site is plain files: no server needed.
"""
import argparse
import json
import shutil
import sys
import tempfile
from datetime import date, datetime, timezone
from pathlib import Path

import db
from server import WEB_DIR, create_app

ROOT = Path(__file__).resolve().parent.parent
DEFAULT_OUT = ROOT / "docs"
DEFAULT_TRIM_M = 400


def round_floats(obj, places=6):
    """Round every float so the JSON files stay small (6 decimals is about 10 cm of GPS)."""
    if isinstance(obj, float):
        return round(obj, places)
    if isinstance(obj, list):
        return [round_floats(x, places) for x in obj]
    if isinstance(obj, dict):
        return {k: round_floats(v, places) for k, v in obj.items()}
    return obj


def trim_gps(conn, trim_m):
    """Blank out location for the first and last trim_m metres of every run (heart rate, pace, etc. stay)."""
    if trim_m <= 0:
        return
    for (rid,) in conn.execute("SELECT strava_id FROM runs").fetchall():
        total = conn.execute("SELECT MAX(distance_m) FROM run_streams WHERE strava_id = ?", (rid,)).fetchone()[0] or 0
        conn.execute("UPDATE run_streams SET lat = NULL, lng = NULL WHERE strava_id = ? AND (distance_m < ? OR distance_m > ?)",
                     (rid, trim_m, total - trim_m))
    conn.execute("UPDATE runs SET has_gps = EXISTS (SELECT 1 FROM run_streams s WHERE s.strava_id = runs.strava_id AND s.lat IS NOT NULL)")
    conn.commit()


def _write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(round_floats(data), separators=(",", ":")))


def export(source_db, out_dir=DEFAULT_OUT, trim_m=DEFAULT_TRIM_M, today=None):
    source_db, out_dir = Path(source_db), Path(out_dir)
    today = today or date.today()
    with tempfile.TemporaryDirectory() as tmp:
        work = Path(tmp) / source_db.name                  # keeps the "demo.db" name so the demo flag carries over
        shutil.copy(source_db, work)
        conn = db.connect(work)
        trim_gps(conn, trim_m)
        conn.close()

        client = create_app(work, today=lambda: today).test_client()
        if out_dir.exists():
            shutil.rmtree(out_dir)
        shutil.copytree(WEB_DIR, out_dir)
        index = out_dir / "index.html"
        index.write_text(index.read_text().replace('<meta charset="utf-8">', '<meta charset="utf-8">\n<meta name="runlab-static" content="1">', 1))
        (out_dir / ".nojekyll").write_text("")

        meta = client.get("/api/meta").get_json()
        meta.update(static=True, strava_connected=False, today=today.isoformat(),
                    exported_at=datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), trimmed_m=trim_m)
        data = out_dir / "data"
        _write_json(data / "meta.json", meta)
        for name in ("runs", "home", "fitness", "plan", "races", "analytics", "places", "calc"):
            _write_json(data / f"{name}.json", client.get(f"/api/{name}").get_json())
        runs = client.get("/api/runs").get_json()
        for r in runs:
            _write_json(data / "runs" / f"{r['id']}.json", client.get(f"/api/runs/{r['id']}").get_json())
        ics = client.get("/api/plan.ics")
        if ics.status_code == 200:
            (data / "plan.ics").write_bytes(ics.data)
    return {"runs": len(runs), "out": str(out_dir), "trimmed_m": trim_m}


if __name__ == "__main__":
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--demo", action="store_true", help="export the fake demo database")
    ap.add_argument("--no-trim", action="store_true", help="keep the full GPS route (default trims 400 m at both ends)")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output folder (default: docs/)")
    args = ap.parse_args()
    src = db.DEMO_PATH if args.demo else db.DB_PATH
    if not src.exists():
        sys.exit(f"No database at {src}. {'Run: python -m tools.make_demo_data' if args.demo else 'Sync some runs first.'}")
    res = export(src, args.out, trim_m=0 if args.no_trim else DEFAULT_TRIM_M)
    print(f"Exported {res['runs']} run(s) to {res['out']} (GPS trimmed {res['trimmed_m']} m at both ends).")
