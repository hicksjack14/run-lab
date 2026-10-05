"""Live Spotify capture: save what you play as you go, so songs line up with future runs without another export.

One-time setup (needs the Spotify account that owns the app to have Premium: Spotify's rule for developer apps):
  1. https://developer.spotify.com/dashboard -> Create app. Redirect URI: http://127.0.0.1:5059/callback (exactly; "localhost" is not accepted)
     APIs used: tick "Web API".
  2. Put the Client ID in .env as SPOTIFY_CLIENT_ID=...   (no secret is needed; this uses PKCE)
  3. python -m ingest.spotify_live auth     (opens a browser; click Agree)
Then:  python -m ingest.spotify_live poll   (also runs inside update.sh, and every 30 min if you run install_spotify_poll.sh)

Spotify only returns your last 50 songs, so polling must be more often than every ~3 hours of listening. Plays are stored
with source='live'. When the official export is imported it replaces live rows for the period it covers.
Spotify's played_at is documented loosely (reports say it is sometimes the start, sometimes the end of a play): we treat it as the END
and derive the start from the song length. Flip it with the setting `spotify_played_at` = "start" if comparing with an export shows otherwise.
"""
import base64
import hashlib
import json
import secrets
import sys
import time
import urllib.parse
import webbrowser
from datetime import datetime, timedelta, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import db
from analysis import fitness
from ingest.strava_api import _urllib_http

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"
TOKEN_PATH = ROOT / "data" / "spotify_token.json"
CALLBACK_PORT = 5059                      # not 5060: browsers block it as unsafe
REDIRECT_URI = f"http://127.0.0.1:{CALLBACK_PORT}/callback"
SCOPE = "user-read-recently-played"
FMT = "%Y-%m-%dT%H:%M:%SZ"
MIN_PLAY_MS = 10_000


class RateLimited(Exception):
    pass


class SpotifyRefused(Exception):
    pass


def load_env(path=None):
    path = path or ENV_PATH
    cfg = {}
    if path.exists():
        for line in path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                k, v = line.split("=", 1)
                cfg[k.strip()] = v.strip().strip('"').strip("'")
    if not cfg.get("SPOTIFY_CLIENT_ID"):
        sys.exit("Missing SPOTIFY_CLIENT_ID. Add it to .env (see the setup steps at the top of ingest/spotify_live.py).")
    return {"client_id": cfg["SPOTIFY_CLIENT_ID"]}


class SpotifyClient:
    def __init__(self, config, token_path=TOKEN_PATH, http=_urllib_http):
        self.cfg, self.token_path, self.http = config, Path(token_path), http

    # ----- auth (Authorization Code + PKCE: no client secret) -----
    def auth_url_and_verifier(self):
        verifier = secrets.token_urlsafe(64)[:96]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        q = urllib.parse.urlencode({"client_id": self.cfg["client_id"], "response_type": "code", "redirect_uri": REDIRECT_URI, "scope": SCOPE,
                                    "code_challenge_method": "S256", "code_challenge": challenge, "state": secrets.token_urlsafe(8)})
        return f"https://accounts.spotify.com/authorize?{q}", verifier

    def _save(self, data, old_refresh=None):
        tok = {"access_token": data["access_token"], "refresh_token": data.get("refresh_token") or old_refresh,
               "expires_at": time.time() + int(data.get("expires_in", 3600))}
        self.token_path.parent.mkdir(parents=True, exist_ok=True)
        self.token_path.write_text(json.dumps(tok))
        self.token_path.chmod(0o600)
        return tok

    def _token_request(self, **fields):
        body = urllib.parse.urlencode({"client_id": self.cfg["client_id"], **fields})
        status, _, data = self.http("POST", "https://accounts.spotify.com/api/token", {"Content-Type": "application/x-www-form-urlencoded"}, body)
        if status != 200:
            sys.exit(f"Spotify rejected the sign-in ({status}): {data}. Run: python -m ingest.spotify_live auth")
        return data

    def exchange_code(self, code, verifier):
        return self._save(self._token_request(grant_type="authorization_code", code=code, redirect_uri=REDIRECT_URI, code_verifier=verifier))

    def access_token(self):
        if not self.token_path.exists():
            sys.exit("Not signed in to Spotify yet. Run: python -m ingest.spotify_live auth")
        tok = json.loads(self.token_path.read_text())
        if tok["expires_at"] < time.time() + 60:
            tok = self._save(self._token_request(grant_type="refresh_token", refresh_token=tok["refresh_token"]), old_refresh=tok["refresh_token"])
        return tok["access_token"]

    def recently_played(self):
        status, headers, body = self.http("GET", "https://api.spotify.com/v1/me/player/recently-played?limit=50", {"Authorization": f"Bearer {self.access_token()}"})
        if status == 429:
            raise RateLimited()
        if status == 401:
            sys.exit("Spotify says the login expired. Run: python -m ingest.spotify_live auth")
        if status == 403:
            raise SpotifyRefused("Spotify refused access. Developer apps need the app owner to have an active Premium subscription, "
                                 "and your account must be allowed on the app (Dashboard > Settings > User management).")
        if status != 200:
            raise RuntimeError(f"Spotify returned {status}: {body}")
        return body.get("items", [])


def _utc(ts):
    return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(timezone.utc).replace(tzinfo=None, microsecond=0)


def poll(conn, client):
    """Save any songs in Spotify's last-50 list that we do not have yet."""
    try:
        items = client.recently_played()
    except RateLimited:
        return {"added": 0, "rate_limited": True}
    means_start = fitness.get_settings(conn).get("spotify_played_at") == "start"
    added = 0
    for it in sorted(items, key=lambda i: i["played_at"]):
        t = it.get("track")
        if not t or t.get("type") != "track" or not t.get("name"):
            continue
        dur = timedelta(milliseconds=t.get("duration_ms") or 0)
        played = _utc(it["played_at"])
        end = played + dur if means_start else played
        start = end - dur
        prev = conn.execute("SELECT MAX(end_utc) FROM plays WHERE end_utc <= ?", (end.strftime(FMT),)).fetchone()[0]
        if prev:
            prev_end = datetime.strptime(prev, FMT)
            if start < prev_end < end:            # skipped early: it can't have started before the last song ended
                start = prev_end
        ms = int((end - start).total_seconds() * 1000)
        if ms < MIN_PLAY_MS:
            continue
        artists = t.get("artists") or [{}]
        album = t.get("album") or {}
        # album details let analysis/albums.py tell when a whole album has been played
        details = (album.get("id"), album.get("album_type"), album.get("total_tracks"), t.get("track_number"), t.get("disc_number"), t.get("duration_ms"))
        inserted = conn.execute("INSERT OR IGNORE INTO plays (start_utc, end_utc, ms_played, track, artist, album, spotify_uri, source,"
                                " album_id, album_type, total_tracks, track_number, disc_number, duration_ms) VALUES (?,?,?,?,?,?,?, 'live', ?,?,?,?,?,?)",
                                (start.strftime(FMT), end.strftime(FMT), ms, t["name"], artists[0].get("name"), album.get("name"), t.get("uri"), *details)).rowcount
        added += inserted
        if not inserted:     # saved by an earlier poll, before we kept these details: fill them in
            conn.execute("UPDATE plays SET album_id=?, album_type=?, total_tracks=?, track_number=?, disc_number=?, duration_ms=?"
                         " WHERE end_utc=? AND spotify_uri=? AND source='live' AND album_id IS NULL",
                         (*details, end.strftime(FMT), t.get("uri")))
    conn.commit()
    return {"added": added, "rate_limited": False}


def run_auth(client):
    result = {}

    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result["code"], result["error"], result["state"] = q.get("code", [None])[0], q.get("error", [None])[0], q.get("state", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.end_headers()
            self.wfile.write(b"Run Lab is connected to Spotify. You can close this tab.")

        def log_message(self, *a):
            pass

    url, verifier = client.auth_url_and_verifier()
    server = HTTPServer(("127.0.0.1", CALLBACK_PORT), Handler)
    print("Opening Spotify in your browser. If it does not open, paste this URL:\n" + url)
    webbrowser.open(url)
    server.handle_request()
    server.server_close()
    expected = urllib.parse.parse_qs(urllib.parse.urlparse(url).query)["state"][0]
    if not result.get("code") or result.get("state") != expected:
        sys.exit(f"Spotify did not return a valid code ({result.get('error') or 'cancelled'}).")
    client.exchange_code(result["code"], verifier)
    print("Connected. Now run: python -m ingest.spotify_live poll")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else ""
    if cmd == "recent":                      # sanity check: your latest saved plays, in your local time
        for r in db.connect().execute("SELECT track, artist, start_utc, end_utc, source FROM plays ORDER BY end_utc DESC LIMIT 6"):
            local = lambda ts: datetime.strptime(ts, FMT).replace(tzinfo=timezone.utc).astimezone().strftime("%a %H:%M:%S")
            print(f"{r['track'][:34]:<34} {(r['artist'] or '')[:20]:<20} {local(r['start_utc'])} to {local(r['end_utc'])}  ({r['source']})")
        sys.exit(0)
    if cmd == "set-played-at":               # flip how Spotify's timestamp is read, if "recent" shows it is backwards
        which = sys.argv[2] if len(sys.argv) > 2 else ""
        if which not in ("start", "end"):
            sys.exit("Usage: python -m ingest.spotify_live set-played-at start|end")
        fitness.set_setting(db.connect(), "spotify_played_at", which)
        sys.exit(f"Okay: Spotify's played_at will now be treated as the {which} of each play (applies to plays saved from now on).")
    if cmd not in ("auth", "poll"):
        sys.exit("Usage: python -m ingest.spotify_live auth | poll | recent | set-played-at start|end")
    spotify = SpotifyClient(load_env())
    if cmd == "auth":
        run_auth(spotify)
    else:
        conn = db.connect()
        try:
            res = poll(conn, spotify)
        except SpotifyRefused as e:
            sys.exit(str(e))
        print(f"Saved {res['added']} new play(s)." + (" Hit Spotify's rate limit; will retry next time." if res["rate_limited"] else ""))
        try:                                 # tell Crates about albums played all the way through; never let this break the poll
            from ingest import crates_sync
            albums_res = crates_sync.run(conn)
            if albums_res["new"] or albums_res["sent"] or albums_res["retry_later"] or albums_res["refused"]:
                print(f"Albums: {albums_res['new']} new finish(es), {albums_res['sent']} sent to Crates, "
                      f"{albums_res['retry_later']} to retry, {albums_res['refused']} refused.")
        except (Exception, SystemExit) as e:
            print(f"Album sync skipped: {e}")
