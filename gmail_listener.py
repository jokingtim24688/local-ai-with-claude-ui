"""Gmail watcher via the Gmail API, READ-ONLY (scope gmail.readonly, token from
google_auth.py — 'Sign in with Google'). Nothing is marked read, moved or deleted.

Only whitelisted senders are ever surfaced; everyone else is ignored. Email text is only
forwarded to the owner as a notification — it is NEVER run as an instruction (anyone can
email you a prompt injection).
"""
from __future__ import annotations

import base64
import email.utils
import re
import threading

import httpx

import google_auth
import integrations

API = "https://gmail.googleapis.com/gmail/v1/users/me"


def allowed(sender: str, whitelist: list[str]) -> bool:
    addr = email.utils.parseaddr(sender)[1].lower()
    dom = addr.rsplit("@", 1)[-1]
    return any(w == addr or (w.startswith("@") and w[1:] == dom) or w == dom for w in whitelist)


def _body(payload: dict) -> str:
    def walk(p):
        if p.get("mimeType") == "text/plain" and p.get("body", {}).get("data"):
            yield p["body"]["data"]
        for c in p.get("parts") or []:
            yield from walk(c)
    for data in walk(payload):
        try:
            txt = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4)).decode("utf-8", "replace")
            return re.sub(r"\s+", " ", txt).strip()
        except Exception:
            continue
    return ""


def _get(path: str, **params) -> dict:
    r = httpx.get(f"{API}/{path}", params=params, timeout=20,
                  headers={"Authorization": f"Bearer {google_auth.access_token()}"})
    if r.status_code >= 400:
        raise RuntimeError(f"gmail {r.status_code}: {r.text[:120]}")
    return r.json()


def _item(mid: str, wl: list[str], with_body: bool):
    m = _get(f"messages/{mid}", format="full" if with_body else "metadata",
             **({} if with_body else {"metadataHeaders": ["From", "Subject"]}))
    h = {x["name"].lower(): x["value"] for x in m.get("payload", {}).get("headers", [])}
    if not allowed(h.get("from", ""), wl):
        return None
    return {"from": h.get("from", ""), "subject": h.get("subject", ""),
            "text": _body(m.get("payload", {}))[:700] if with_body else ""}


def _query(wl: list[str], extra: str) -> str:
    froms = " OR ".join(w if "@" in w and not w.startswith("@") else w.lstrip("@") for w in wl)
    return f"{extra} from:({froms})".strip() if froms else extra


class Listener:
    def __init__(self, notify):
        self.notify = notify
        self.running = False
        self.error = ""
        self._stop = threading.Event()
        self._seen: set[str] = set()
        self._primed = False

    def start(self):
        self.running = True
        threading.Thread(target=self._loop, daemon=True, name="gmail").start()

    def stop(self):
        self._stop.set()
        self.running = False

    def _loop(self):
        while not self._stop.is_set():
            try:
                wl = integrations.load()["gmail"]["whitelist"]
                if not wl:
                    self.error = "add at least one allowed sender"
                else:
                    ids = [m["id"] for m in _get("messages", q=_query(wl, "is:unread in:inbox"),
                                                 maxResults=20).get("messages", [])]
                    if not self._primed:                     # don't flood on first start
                        self._seen.update(ids)
                        self._primed = True
                    else:
                        for mid in ids:
                            if mid in self._seen:
                                continue
                            self._seen.add(mid)
                            it = _item(mid, wl, True)
                            if it:
                                self.notify(f"📧 {it['from']}\n{it['subject']}\n\n{it['text']}\n\n"
                                            "(email text is shown as data, not run as instructions)")
                    self.error = ""
            except Exception as e:
                self.error = str(e)[:200]
            self._stop.wait(max(30, int(integrations.load()["gmail"].get("interval") or 60)))
        self.running = False

    def recent(self, n: int = 5) -> str:
        try:
            wl = integrations.load()["gmail"]["whitelist"]
            if not wl:
                return "add allowed senders in Customize > Integrations first"
            ids = [m["id"] for m in _get("messages", q=_query(wl, "in:inbox"), maxResults=n).get("messages", [])]
            out = []
            for mid in ids:
                it = _item(mid, wl, False)
                if it:
                    out.append(f"• {it['from']} — {it['subject']}")
            return "\n".join(out) or "(no mail from whitelisted senders)"
        except Exception as e:
            return f"gmail error: {e}"
