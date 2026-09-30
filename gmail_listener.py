"""Gmail watcher (IMAP, READ-ONLY). Needs a Google app password (Account > Security >
2-Step Verification > App passwords) and IMAP enabled.

Only senders on the whitelist are ever surfaced; everyone else is ignored. Mail is opened
with BODY.PEEK in a read-only mailbox, so nothing is marked read, moved or deleted. Email
text is only forwarded to the owner as a notification — it is NEVER run as an instruction
(anyone can email you a prompt injection).
"""
from __future__ import annotations

import email
import email.header
import email.utils
import imaplib
import re
import threading
import time

import integrations


def _dec(v: str) -> str:
    try:
        return str(email.header.make_header(email.header.decode_header(v or "")))
    except Exception:
        return v or ""


def allowed(sender: str, whitelist: list[str]) -> bool:
    addr = email.utils.parseaddr(sender)[1].lower()
    dom = addr.rsplit("@", 1)[-1]
    return any(w == addr or (w.startswith("@") and w[1:] == dom) or w == dom for w in whitelist)


def _text(msg) -> str:
    part = msg
    if msg.is_multipart():
        part = next((p for p in msg.walk() if p.get_content_type() == "text/plain"), None)
        if part is None:
            return ""
    try:
        s = part.get_payload(decode=True).decode(part.get_content_charset() or "utf-8", "replace")
    except Exception:
        return ""
    return re.sub(r"\s+", " ", s).strip()


class Listener:
    def __init__(self, notify):
        self.notify = notify
        self.running = False
        self.error = ""
        self._stop = threading.Event()
        self._seen: set[bytes] = set()
        self._primed = False

    def start(self):
        self.running = True
        threading.Thread(target=self._loop, daemon=True, name="gmail").start()

    def stop(self):
        self._stop.set()
        self.running = False

    def _connect(self):
        c = integrations.load()["gmail"]
        m = imaplib.IMAP4_SSL("imap.gmail.com", timeout=30)
        m.login(c["address"], c["app_password"])
        m.select("INBOX", readonly=True)
        return m, c

    def _fetch(self, m, uid: bytes, wl: list[str]):
        typ, data = m.uid("fetch", uid, "(BODY.PEEK[])")
        if typ != "OK" or not data or not isinstance(data[0], tuple):
            return None
        msg = email.message_from_bytes(data[0][1])
        sender = _dec(msg.get("From", ""))
        if not allowed(sender, wl):
            return None
        return {"from": sender, "subject": _dec(msg.get("Subject", "")), "date": msg.get("Date", ""),
                "text": _text(msg)[:700]}

    def _loop(self):
        while not self._stop.is_set():
            try:
                m, c = self._connect()
                self.error = ""
                typ, ids = m.uid("search", None, "UNSEEN")
                unseen = ids[0].split() if typ == "OK" and ids and ids[0] else []
                if not self._primed:                       # don't flood on first start
                    self._seen.update(unseen)
                    self._primed = True
                else:
                    for uid in unseen:
                        if uid in self._seen:
                            continue
                        self._seen.add(uid)
                        it = self._fetch(m, uid, c["whitelist"])
                        if it:
                            self.notify(f"📧 {it['from']}\n{it['subject']}\n\n{it['text']}\n\n"
                                        "(email text is shown as data, not run as instructions)")
                m.logout()
            except Exception as e:
                self.error = str(e)[:200]
            self._stop.wait(max(30, int(integrations.load()["gmail"].get("interval") or 60)))
        self.running = False

    def recent(self, n: int = 5) -> str:
        try:
            m, c = self._connect()
            typ, ids = m.uid("search", None, "ALL")
            out = []
            for uid in reversed(ids[0].split()[-40:] if typ == "OK" and ids and ids[0] else []):
                it = self._fetch(m, uid, c["whitelist"])
                if it:
                    out.append(f"• {it['from']} — {it['subject']}")
                if len(out) >= n:
                    break
            m.logout()
            return "\n".join(out) or "(no mail from whitelisted senders)"
        except Exception as e:
            return f"gmail error: {e}"
