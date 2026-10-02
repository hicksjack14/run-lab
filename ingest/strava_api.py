"""Direct Strava API sync (no Claude needed).

One-time setup:
  1. Create a free API app at https://www.strava.com/settings/api
     - Authorization Callback Domain: localhost
  2. Put the Client ID + Client Secret in ~/run-lab/.env (see .env.example)
  3. python -m ingest.strava_api auth     (opens a browser; click Authorize)
  4. python -m ingest.strava_api sync     (safe to re-run; skips runs already imported)

Strava allows ~100 requests / 15 min and 1000 / day. Each new run costs 2 requests plus one
list call per 100 runs, so a big backfill stops cleanly at the limit: just run sync again later.
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import db
from ingest.strava_import import DUMP_DIR, import_dump

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
TOKEN_PATH = ROOT / "data" / "strava_token.json"
API = "https://www.strava.com/api/v3"
OAUTH = "https://www.strava.com/oauth"
CALLBACK_PORT = 5058
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}/callback"
RUN_TYPES = {"Run", "TrailRun", "VirtualRun"}
STREAM_KEYS = "time,heartrate,velocity_smooth,cadence,distance,moving,latlng,altitude"

# Strava's best_effort names -> the names the importer/analysis use
BEST_EFFORT_NAMES = {
    "400m": "Fastest400", "1/2 mile": "FastestHalfMile", "1k": "Fastest1k", "1 mile": "FastestMile",
    "2 mile": "Fastest2Mile", "5k": "Fastest5k", "10k": "Fastest10k", "15k": "Fastest15k",
    "10 mile": "Fastest10Mile", "20k": "Fastest20k", "Half-Marathon": "FastestHalfMarathon",
    "30k": "Fastest30k", "Marathon": "FastestMarathon",
}


class RateLimited(Exception):
    pass


def _urllib_http(method, url, headers=None, data=None):
    req = urllib.request.Request(url, data=data.encode() if data else None, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, dict(resp.headers), json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            body = json.loads(body)
        except ValueError:
            pass
        return e.code, dict(e.headers), body


def load_env(path=None):
    path = path or ENV_PATH
    cfg = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    cid, secret = cfg.get("STRAVA_CLIENT_ID"), cfg.get("STRAVA_CLIENT_SECRET")
    if not cid or not secret:
        sys.exit("Missing STRAVA_CLIENT_ID / STRAVA_CLIENT_SECRET. Copy .env.example to .env and fill them in.")
    return {"client_id": cid, "client_secret": secret}


class StravaClient:
    def __init__(self, config, token_path=TOKEN_PATH, http=_urllib_http):
        self.cfg, self.token_path, self.http = config, Path(token_path), http

    # ----- auth -----
    def auth_url(self):
        q = urllib.parse.urlencode({
            "client_id": self.cfg["client_id"], "redirect_uri": REDIRECT_URI, "response_type": "code",
            "approval_prompt": "auto", "scope": "read,activity:read_all",
        })
        return f"{OAUTH}/authorize?{q}"

    def _token_request(self, **fields):
        body = urllib.parse.urlencode({"client_id": self.cfg["client_id"], "client_secret": self.cfg["client_secret"], **fields})
        status, _, data = self.http("POST", f"{OAUTH}/token", {"Content-Type": "application/x-www-form-urlencoded"}, body)
        if status != 200:
            sys.exit(f"Strava rejected the token request ({status}): {data}")
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        keep = {k: data[k] for k in ("access_token", "refresh_token", "expires_at") if k in data}
        self.token_path.write_text(json.dumps(keep))
        self.token_path.chmod(0o600)
        return keep

    def exchange_code(self, code):
        return self._token_request(code=code, grant_type="authorization_code")

    def access_token(self):
        if not self.token_path.exists():
            sys.exit("Not signed in to Strava yet. Run: python -m ingest.strava_api auth")
        tok = json.loads(self.token_path.read_text())
        if tok["expires_at"] < time.time() + 60:
            tok = self._token_request(grant_type="refresh_token", refresh_token=tok["refresh_token"])
        return tok["access_token"]

    # ----- requests -----
    def get(self, path, **params):
        url = f"{API}{path}"
        if params:
            url += "?" + urllib.parse.urlencode(params)
        status, headers, body = self.http("GET", url, {"Authorization": f"Bearer {self.access_token()}"})
        if status == 429:
            raise RateLimited()
        if status == 401:
            sys.exit("Strava says the token is not valid. Run: python -m ingest.strava_api auth")
        if status != 200:
            raise RuntimeError(f"Strava {path} returned {status}: {body}")
        return body

    def list_runs(self):
        """Yield run summaries, newest first."""
        page = 1
        while True:
            batch = self.get("/athlete/activities", per_page=100, page=page)
            if not batch:
                return
            for a in batch:
                if (a.get("sport_type") or a.get("type")) in RUN_TYPES:
                    yield a
            page += 1

    def gear_name(self, gear_id):
        g = self.get(f"/gear/{gear_id}")
        return g.get("name") or " ".join(x for x in (g.get("brand_name"), g.get("model_name")) if x) or None

    def fetch_run(self, run_id):
        detail = self.get(f"/activities/{run_id}")
        streams = self.get(f"/activities/{run_id}/streams", keys=STREAM_KEYS, key_by_type="true")
        return to_dump(detail, streams)


def to_dump(detail, streams):
    """Convert Strava API responses into the dump format ingest.strava_import understands."""
    tz = detail.get("timezone", "")
    iana = tz.split(") ", 1)[1] if ") " in tz else None
    activity = {
        "id": str(detail["id"]),
        "name": detail.get("name"),
        "sport_type": detail.get("sport_type") or detail.get("type"),
        # Strava's *_local timestamps carry a bogus trailing Z; the wall-clock time is local
        "start_local": detail["start_date_local"].rstrip("Z"),
        "gear_id": detail.get("gear_id"),
        "summary": {
            "distance": detail.get("distance"), "moving_time": detail.get("moving_time"),
            "elapsed_time": detail.get("elapsed_time"), "elevation_gain": detail.get("total_elevation_gain"),
            "avg_cadence": detail.get("average_cadence"), "relative_effort": detail.get("suffer_score"),
        },
    }
    if iana:
        activity["timezone"] = iana
    rename = {"time": "time", "heartrate": "heart_rate", "velocity_smooth": "velocity_smooth", "cadence": "cadence",
              "distance": "distance", "moving": "moving", "latlng": "location", "altitude": "altitude"}
    out_streams = {rename[k]: v["data"] for k, v in streams.items() if k in rename and isinstance(v, dict)}
    performance = {
        "average_heartrate": detail.get("average_heartrate"), "max_heartrate": detail.get("max_heartrate"),
        "laps": [
            {"distance": l.get("distance"), "moving_time": l.get("moving_time"),
             "avg_hr": l.get("average_heartrate"), "max_hr": l.get("max_heartrate")}
            for l in detail.get("laps", [])
        ],
        "best_efforts": [
            {"type_value": BEST_EFFORT_NAMES.get(b["name"], b["name"]), "value": b["elapsed_time"]}
            for b in detail.get("best_efforts", [])
        ],
    }
    return {"activity": activity, "streams": out_streams, "performance": performance}


def sync(conn, client, dump_dir=DUMP_DIR, limit=None, log=print):
    """Import runs not already in the database. Resumable: stops cleanly on Strava's rate limit."""
    have = {r[0] for r in conn.execute("SELECT strava_id FROM runs")}
    dump_dir = Path(dump_dir)
    dump_dir.mkdir(parents=True, exist_ok=True)
    imported, skipped = [], 0
    try:
        for summary in client.list_runs():
            rid = str(summary["id"])
            if rid in have:
                skipped += 1
                continue
            if limit is not None and len(imported) >= limit:
                break
            dump = client.fetch_run(rid)
            (dump_dir / f"{rid}.json").write_text(json.dumps(dump, separators=(",", ":")))
            import_dump(conn, dump)
            imported.append(rid)
            log(f"  imported {rid}  {dump['activity']['start_local'][:10]}  {dump['activity']['name']}")
        _fill_gear_names(conn, client)
    except RateLimited:
        return {"imported": imported, "skipped": skipped, "rate_limited": True}
    return {"imported": imported, "skipped": skipped, "rate_limited": False}


def _fill_gear_names(conn, client):
    """Look up a readable name for each shoe id we have not named yet (1 request each)."""
    from analysis import fitness
    names = fitness.get_settings(conn).get("gear_names", {})
    for (gid,) in conn.execute("SELECT DISTINCT gear_id FROM runs WHERE gear_id IS NOT NULL").fetchall():
        if gid not in names:
            names[gid] = client.gear_name(gid) or gid
            fitness.set_setting(conn, "gear_names", names)


def run_auth(client):
    """Open Strava's authorize page and catch the redirect on a one-shot local server."""
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result["code"], result["error"] = q.get("code", [None])[0], q.get("error", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Run Lab is connected to Strava. You can close this tab.")

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", CALLBACK_PORT), Handler)
    url = client.auth_url()
    print("Opening Strava in your browser. If it does not open, paste this URL:\n" + url)
    webbrowser.open(url)
    server.handle_request()
    server.server_close()
    if not result.get("code"):
        sys.exit(f"Strava did not return a code ({result.get('error') or 'cancelled'}).")
    client.exchange_code(result["code"])
    print("Connected. Now run: python -m ingest.strava_api sync")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd not in ("auth", "sync"):
        sys.exit("Usage: python -m ingest.strava_api auth | sync [--limit N]")
    strava = StravaClient(load_env())
    if cmd == "auth":
        run_auth(strava)
    else:
        limit = int(sys.argv[sys.argv.index("--limit") + 1]) if "--limit" in sys.argv else None
        res = sync(db.connect(), strava, limit=limit)
        print(f"Imported {len(res['imported'])} new run(s); {res['skipped']} already had.")
        if res["rate_limited"]:
            print("Hit Strava's rate limit. Run sync again in ~15 minutes; it picks up where it left off.")
