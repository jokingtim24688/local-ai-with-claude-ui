"""'Sign in with Google' for the Gmail watcher — OAuth 2.0 for installed apps, PKCE,
loopback redirect on 127.0.0.1 (works the same on Windows and macOS).

Night Crew never sees your Google password. It stores only a revocable refresh token in
the OS keychain (vault.py). Scope: gmail.readonly (+ email, to show which account).

One-time setup (Google requires it for every desktop app): console.cloud.google.com ->
new project -> enable "Gmail API" -> OAuth consent screen (External; add yourself as a
test user, or publish to avoid 7-day token expiry) -> Credentials -> Create OAuth client
-> "Desktop app" -> paste Client ID (+ secret) into Customize > Integrations.
"""
from __future__ import annotations

import base64
import hashlib
import http.server
import secrets
import threading
import time
import urllib.parse
import webbrowser

import httpx

import integrations
import vault

AUTH = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN = "https://oauth2.googleapis.com/token"
REVOKE = "https://oauth2.googleapis.com/revoke"
USERINFO = "https://openidconnect.googleapis.com/v1/userinfo"
SCOPE = "https://www.googleapis.com/auth/gmail.readonly openid email"
RT = "google.refresh_token"

STATE = {"status": "idle", "error": "", "url": ""}          # idle | waiting | done | error
_CACHE = {"token": "", "exp": 0.0}
_LOCK = threading.Lock()


def signed_in() -> bool:
    return bool(vault.get(RT))


def _creds() -> tuple[str, str]:
    g = integrations.load()["gmail"]
    return g["client_id"].strip(), g["client_secret"].strip()


def start_signin(timeout: int = 300) -> dict:
    cid, csec = _creds()
    if not cid:
        return {"ok": False, "error": "paste your Google OAuth Client ID first"}
    if STATE["status"] == "waiting":
        return {"ok": True, "url": STATE["url"]}
    verifier = base64.urlsafe_b64encode(secrets.token_bytes(48)).rstrip(b"=").decode()
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    got: dict = {}
    done = threading.Event()

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            if "code" not in q and "error" not in q:
                self.send_response(404); self.end_headers(); return
            ok = q.get("state", [""])[0] == state and "code" in q
            got.update({"code": q.get("code", [""])[0], "error": q.get("error", [""])[0]} if ok
                       else {"error": q.get("error", ["state mismatch"])[0]})
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write(("<html><body style='font:16px sans-serif;background:#14121c;color:#eee;"
                              "text-align:center;padding-top:15vh'><h2>"
                              + ("Signed in — you can close this tab." if ok else "Sign-in failed.")
                              + "</h2></body></html>").encode())
            done.set()

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    redirect = f"http://127.0.0.1:{srv.server_address[1]}"
    url = AUTH + "?" + urllib.parse.urlencode({
        "client_id": cid, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
        "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
        "access_type": "offline", "prompt": "consent"})
    STATE.update(status="waiting", error="", url=url)

    def run():
        try:
            threading.Thread(target=srv.serve_forever, daemon=True).start()
            webbrowser.open(url)
            if not done.wait(timeout):
                raise RuntimeError("sign-in timed out")
            if got.get("error") or not got.get("code"):
                raise RuntimeError(got.get("error") or "no code returned")
            data = {"client_id": cid, "code": got["code"], "code_verifier": verifier,
                    "redirect_uri": redirect, "grant_type": "authorization_code"}
            if csec:
                data["client_secret"] = csec
            r = httpx.post(TOKEN, data=data, timeout=20).json()
            if "refresh_token" not in r:
                raise RuntimeError(r.get("error_description") or r.get("error") or "no refresh token")
            vault.put(RT, r["refresh_token"])
            _CACHE.update(token=r.get("access_token", ""), exp=time.time() + int(r.get("expires_in", 0)) - 60)
            try:
                me = httpx.get(USERINFO, headers={"Authorization": f"Bearer {r['access_token']}"}, timeout=15).json()
                integrations.update({"gmail": {"account": me.get("email", "")}})
            except Exception:
                pass
            STATE.update(status="done", error="")
        except Exception as e:
            STATE.update(status="error", error=str(e)[:200])
        finally:
            srv.shutdown()
            srv.server_close()

    threading.Thread(target=run, daemon=True, name="google-signin").start()
    return {"ok": True, "url": url}


def access_token() -> str:
    """A valid access token, refreshed when needed. Raises RuntimeError if not signed in."""
    with _LOCK:
        if _CACHE["token"] and time.time() < _CACHE["exp"]:
            return _CACHE["token"]
        rt = vault.get(RT)
        if not rt:
            raise RuntimeError("not signed in to Google")
        cid, csec = _creds()
        data = {"client_id": cid, "refresh_token": rt, "grant_type": "refresh_token"}
        if csec:
            data["client_secret"] = csec
        r = httpx.post(TOKEN, data=data, timeout=20).json()
        if "access_token" not in r:
            if r.get("error") == "invalid_grant":             # revoked / expired (7-day test mode)
                vault.delete(RT)
                STATE.update(status="error", error="Google session expired — sign in again")
            raise RuntimeError(r.get("error_description") or r.get("error") or "token refresh failed")
        _CACHE.update(token=r["access_token"], exp=time.time() + int(r.get("expires_in", 3600)) - 60)
        return _CACHE["token"]


def sign_out() -> None:
    rt = vault.get(RT)
    if rt:
        try:
            httpx.post(REVOKE, params={"token": rt}, timeout=10)
        except Exception:
            pass
    vault.delete(RT)
    _CACHE.update(token="", exp=0.0)
    STATE.update(status="idle", error="", url="")
    integrations.update({"gmail": {"account": ""}})
