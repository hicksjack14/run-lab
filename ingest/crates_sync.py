"""Tell Crates (Jack's album diary) when he has listened to a whole album.

How it works: after each Spotify poll, `run()` looks at recent live plays, records any album that was played all
the way through (analysis/albums.py) in the `album_finishes` table, then sends each new one to Crates over HTTPS
with a secret token. Crates logs it as "listened" (no rating) and takes it off the Queue.

Setup (Jack): put these two lines in .env (never commit it):
    CRATES_URL=https://<your Crates address>
    CRATES_TOKEN=<the same long random value as RUNLAB_TOKEN in Crates' Vercel settings>
Check it with:   python -m ingest.crates_sync check
Run it by hand:  python -m ingest.crates_sync          (also runs after every Spotify poll)
See the list:    python -m ingest.crates_sync status

Safe to run any number of times: a finish is sent until Crates accepts it, then never again. Network trouble and
Crates being down are retried forever on the next run; a refusal (bad token, bad request) is tried a few times.
If CRATES_URL / CRATES_TOKEN are missing, finishes are still recorded and nothing is sent.
"""
import json
import sys
import urllib.error
import urllib.request
from datetime import datetime, timedelta, timezone
from pathlib import Path

import db
from analysis import albums, fitness

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
ENDPOINT = "/api/runlab/listened"
LOOKBACK_DAYS = 14
MAX_REFUSALS = 5          # how many times Crates may say no before we stop asking about one album
FMT = "%Y-%m-%dT%H:%M:%SZ"


def load_env(path=None):
    """Returns {url, token} or None when Crates isn't set up. Exits if the address is unsafe."""
    path = path or ENV_PATH
    cfg = {}
    if Path(path).exists():
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    url, token = cfg.get("CRATES_URL", "").rstrip("/"), cfg.get("CRATES_TOKEN", "")
    if not url or not token:
        return None
    local = url.startswith(("http://localhost", "http://127.0.0.1"))
    if not (url.startswith("https://") or local):
        sys.exit("CRATES_URL must start with https:// (the token is a secret and must not travel unencrypted).")
    return {"url": url, "token": token}


def _http(method, url, headers=None, data=None):
    req = urllib.request.Request(url, data=data.encode() if data else None, headers=headers or {}, method=method)
    try:
        with urllib.request.urlopen(req, timeout=90) as resp:       # Crates may have to look the album up
            return resp.status, json.loads(resp.read() or b"null")
    except urllib.error.HTTPError as e:
        body = e.read()
        try:
            body = json.loads(body)
        except ValueError:
            pass
        return e.code, body


def record_finishes(conn, now=None):
    """Find albums played all the way through recently and save any we haven't seen. Returns how many are new."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    since = (now - timedelta(days=LOOKBACK_DAYS)).strftime(FMT)
    rows = [dict(r) for r in conn.execute(
        "SELECT album_id, album, artist, album_type, total_tracks, track_number, disc_number, duration_ms, ms_played, end_utc"
        " FROM plays WHERE source = 'live' AND album_id IS NOT NULL AND end_utc >= ?", (since,))]
    tz = fitness.get_settings(conn).get("timezone") or albums.DEFAULT_TZ
    new = 0
    for f in albums.find_finished_albums(rows):
        new += conn.execute(
            "INSERT OR IGNORE INTO album_finishes (album_id, album, artist, total_tracks, finished_at, listened_on) VALUES (?,?,?,?,?,?)",
            (f["album_id"], f["album"], f["artist"], f["total_tracks"], f["finished_at"], albums.listened_on(f["finished_at"], tz))).rowcount
    conn.commit()
    return new


def send_pending(conn, cfg, http=_http, now=None):
    """Post every finish Crates hasn't accepted yet. Returns {sent, retry_later, refused}."""
    now = now or datetime.now(timezone.utc).replace(tzinfo=None)
    out = {"sent": 0, "retry_later": 0, "refused": 0}
    pending = conn.execute("SELECT * FROM album_finishes WHERE synced_at IS NULL AND attempts < ? ORDER BY finished_at", (MAX_REFUSALS,)).fetchall()
    for r in pending:
        body = json.dumps({"albumId": r["album_id"], "listenedOn": r["listened_on"], "finishedAt": r["finished_at"]})
        headers = {"Authorization": f"Bearer {cfg['token']}", "Content-Type": "application/json"}
        try:
            status, resp = http("POST", cfg["url"] + ENDPOINT, headers, body)
        except (urllib.error.URLError, OSError, TimeoutError) as e:      # offline, DNS, timeout: try again next time
            conn.execute("UPDATE album_finishes SET last_error=? WHERE id=?", (f"network: {type(e).__name__}", r["id"]))
            out["retry_later"] += 1
            continue
        if status == 200 and isinstance(resp, dict):
            conn.execute("UPDATE album_finishes SET synced_at=?, crates_status=?, last_error=NULL WHERE id=?",
                         (now.strftime(FMT), resp.get("status") or "ok", r["id"]))
            out["sent"] += 1
        elif status == 429 or status >= 500:                              # Crates busy or down: try again later
            conn.execute("UPDATE album_finishes SET last_error=? WHERE id=?", (f"Crates said {status}", r["id"]))
            out["retry_later"] += 1
            if status == 429:
                break                                                     # don't keep knocking
        else:                                                             # 400/401/404/503-disabled: Crates refused it
            msg = resp.get("error") if isinstance(resp, dict) else str(resp)[:80]
            conn.execute("UPDATE album_finishes SET attempts = attempts + 1, last_error=? WHERE id=?", (f"Crates said {status}: {msg}", r["id"]))
            out["refused"] += 1
    conn.commit()
    return out


def run(conn, cfg="auto", http=_http, now=None):
    """Record new finishes, then send them if Crates is set up."""
    cfg = load_env() if cfg == "auto" else cfg
    summary = {"new": record_finishes(conn, now), "configured": cfg is not None}
    summary.update(send_pending(conn, cfg, http, now) if cfg else {"sent": 0, "retry_later": 0, "refused": 0})
    return summary


def status(conn):
    rows = conn.execute("SELECT * FROM album_finishes ORDER BY finished_at DESC LIMIT 15").fetchall()
    if not rows:
        print("No finished albums yet. They show up here after you play every track of an album (80%+ of each, within 2 days).")
    for r in rows:
        state = f"sent ({r['crates_status']})" if r["synced_at"] else (f"waiting: {r['last_error']}" if r["last_error"] else "waiting to send")
        print(f"{r['listened_on']}  {(r['album'] or '?')[:34]:<34} {(r['artist'] or '')[:20]:<20} {state}")


def check(cfg, http=_http):
    """Is the address right and the token accepted? An empty request gets 400 from Crates when the token is good."""
    if not cfg:
        return "Not set up: add CRATES_URL and CRATES_TOKEN to .env."
    status_code, resp = http("POST", cfg["url"] + ENDPOINT, {"Authorization": f"Bearer {cfg['token']}", "Content-Type": "application/json"}, "{}")
    if status_code == 400:
        return "Connected: Crates accepted the token."
    if status_code == 401:
        return "Crates rejected the token. It must match RUNLAB_TOKEN in Crates' Vercel settings exactly."
    if status_code == 503:
        return "Crates has the endpoint switched off: set RUNLAB_TOKEN and RUNLAB_USERNAME in Vercel, then redeploy."
    if status_code == 404:
        return "Crates doesn't have the endpoint yet: deploy the latest Crates first."
    return f"Unexpected answer from Crates: {status_code}."


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "run"
    conn = db.connect()
    if cmd == "status":
        status(conn)
    elif cmd == "check":
        print(check(load_env()))
    elif cmd == "run":
        res = run(conn)
        print(f"Albums: {res['new']} new finish(es), {res['sent']} sent to Crates, {res['retry_later']} to retry, {res['refused']} refused."
              + ("" if res["configured"] else " (Crates isn't set up yet, so nothing was sent.)"))
    else:
        sys.exit("Usage: python -m ingest.crates_sync [run | status | check]")
