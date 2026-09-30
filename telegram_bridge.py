"""Telegram <-> Night Crew. Long-polls the Bot API (no webhook, no open port).

Locked to ONE owner: until paired, the bot only answers `/pair <code>` (code is shown in
Customize > Integrations); afterwards every message/button from any other chat or user is
silently ignored. Chats run through the same /api/chat loop as the desktop UI, so tools,
skills, memory and the approval gate all behave the same — approvals arrive as inline
Approve/Deny buttons unless `auto` is on. Files the agents write are sent back as documents.
"""
from __future__ import annotations

import json
import os
import queue
import re
import subprocess
import sys
import threading
import time

import httpx

import integrations
import tools

API = "https://api.telegram.org"
FILE_EXT = r"png|jpe?g|gif|webp|stl|obj|fbx|glb|blend|scad|rbxlx|rbxl|verse|uasset|py|lua|luau|json|md|txt|csv|pdf|docx|pptx|zip"
FILE_RE = re.compile(rf"[\w./\\-]+\.(?:{FILE_EXT})\b", re.I)
MAX_FILE = 45 * 1024 * 1024


class Bridge:
    def __init__(self, backend):
        self.backend = backend
        self.running = False
        self.error = ""
        self.gmail = None
        self._stop = threading.Event()
        self._jobs: queue.Queue = queue.Queue()
        self._history: list[dict] = []
        self._web = False
        self._model = ""
        self._offset = 0

    # ---- plumbing -----------------------------------------------------------
    def _cfg(self) -> dict:
        return integrations.load()["telegram"]

    def _call(self, method: str, timeout: int = 40, **kw):
        tok = self._cfg()["token"]
        r = httpx.post(f"{API}/bot{tok}/{method}", json=kw, timeout=timeout)
        return r.json()

    def send(self, chat_id: int, text: str, **kw) -> None:
        for i in range(0, max(len(text), 1), 3900):
            try:
                self._call("sendMessage", chat_id=chat_id, text=text[i:i + 3900] or "…", **kw)
            except Exception as e:
                self.error = str(e)[:200]

    def notify_owner(self, text: str) -> None:
        oid = self._cfg()["owner_id"]
        if oid:
            self.send(oid, text)

    def send_file(self, chat_id: int, path: str) -> None:
        tok = self._cfg()["token"]
        with open(path, "rb") as f:
            httpx.post(f"{API}/bot{tok}/sendDocument", data={"chat_id": chat_id},
                       files={"document": (os.path.basename(path), f)}, timeout=120)

    # ---- lifecycle ------------------------------------------------------------
    def start(self):
        self.running = True
        threading.Thread(target=self._poll, daemon=True, name="tg-poll").start()
        threading.Thread(target=self._worker, daemon=True, name="tg-work").start()

    def stop(self):
        self._stop.set()
        self.running = False
        self._jobs.put(None)

    def _poll(self):
        while not self._stop.is_set():
            try:
                r = httpx.post(f"{API}/bot{self._cfg()['token']}/getUpdates",
                               json={"offset": self._offset, "timeout": 30,
                                     "allowed_updates": ["message", "callback_query"]},
                               timeout=45).json()
                if not r.get("ok"):
                    self.error = str(r.get("description", "telegram error"))
                    self._stop.wait(10)
                    continue
                self.error = ""
                for u in r.get("result", []):
                    self._offset = u["update_id"] + 1
                    try:
                        self._handle(u)
                    except Exception as e:
                        self.error = str(e)[:200]
            except Exception as e:
                self.error = str(e)[:200]
                self._stop.wait(5)
        self.running = False

    # ---- owner lock -------------------------------------------------------------
    def _handle(self, u: dict):
        cfg = self._cfg()
        cb = u.get("callback_query")
        msg = u.get("message")
        who = (cb or msg or {}).get("from", {}).get("id")
        chat = ((cb or {}).get("message") or msg or {}).get("chat", {}).get("id")
        if not who or not chat:
            return
        if not cfg["owner_id"]:                                   # unpaired: only /pair works
            text = (msg or {}).get("text", "").strip()
            m = re.match(r"^/pair\s+(\d{6})$", text)
            if m and cfg["pair_code"] and m.group(1) == cfg["pair_code"]:
                integrations.update({"telegram": {"owner_id": who}})
                self.send(chat, "Paired. This bot now only answers you. Say /help.")
            return
        if who != cfg["owner_id"] or chat != cfg["owner_id"]:
            return                                                # stranger: silence
        if cb:
            self._callback(cb)
        elif msg and msg.get("text"):
            self._command(chat, msg["text"].strip())

    def _callback(self, cb: dict):
        m = re.match(r"^a:([0-9a-f]+):([01])$", cb.get("data", ""))
        if m:
            p = self.backend.PENDING.get(m.group(1))
            if p:
                p["allow"] = m.group(2) == "1"
                p["event"].set()
        try:
            self._call("answerCallbackQuery", callback_query_id=cb["id"],
                       text="approved" if cb.get("data", "").endswith(":1") else "denied")
        except Exception:
            pass

    # ---- commands ---------------------------------------------------------------
    def _command(self, chat: int, text: str):
        cmd, _, arg = text.partition(" ")
        arg = arg.strip()
        if cmd in ("/start", "/help"):
            self.send(chat, "/new reset chat · /web on|off · /auto on|off (run tools w/o asking) · "
                            "/model NAME · /files · /open PATH (opens on the PC) · /mail · /status\n"
                            "Anything else goes to the crew.")
        elif cmd == "/new":
            self._history.clear()
            self.send(chat, "fresh chat")
        elif cmd == "/web":
            self._web = arg.lower() == "on"
            self.send(chat, f"web {'on' if self._web else 'off'}")
        elif cmd == "/auto":
            integrations.update({"telegram": {"auto": arg.lower() == "on"}})
            self.send(chat, f"auto-approve {'ON — tools run without asking' if arg.lower() == 'on' else 'off'}")
        elif cmd == "/model":
            self._model = arg
            self.send(chat, f"model: {arg or '(default)'}")
        elif cmd == "/files":
            self.send(chat, self._list_files())
        elif cmd == "/open":
            self.send(chat, self._open(arg))
        elif cmd == "/mail":
            self.send(chat, self.gmail.recent() if self.gmail else "gmail not connected")
        elif cmd == "/status":
            self.send(chat, f"model: {self._pick_model()} · web: {self._web} · "
                            f"workspace: {tools.SANDBOX} · gmail: {'on' if self.gmail else 'off'}")
        elif text.startswith("/"):
            self.send(chat, "unknown command — /help")
        else:
            if self._jobs.qsize() >= 1:
                self.send(chat, "busy — wait for the current task")
            else:
                self._jobs.put(text)

    def _safe_path(self, rel: str) -> str | None:
        root = os.path.realpath(tools.SANDBOX)
        full = os.path.realpath(os.path.join(root, rel))
        return full if (full == root or full.startswith(root + os.sep)) else None

    def _list_files(self) -> str:
        root = tools.SANDBOX
        out = []
        for dp, dn, fn in os.walk(root):
            dn[:] = [d for d in dn if not d.startswith(".")][:20]
            for f in fn:
                out.append(os.path.relpath(os.path.join(dp, f), root))
            if len(out) > 60:
                break
        return "\n".join(sorted(out)[:60]) or "(workspace empty)"

    def _open(self, rel: str) -> str:
        full = self._safe_path(rel)
        if not rel or not full or not os.path.exists(full):
            return "not in workspace"
        if sys.platform == "win32":
            os.startfile(full)                                    # type: ignore[attr-defined]
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", full])
        return f"opened {rel} on the PC"

    def _pick_model(self) -> str:
        return (self._model or self._cfg()["model"] or self.backend.load_branding().get("default_model")
                or "hermes3:8b")

    # ---- run a turn through the real chat loop -----------------------------------
    def _worker(self):
        while not self._stop.is_set():
            text = self._jobs.get()
            if text is None:
                break
            chat = self._cfg()["owner_id"]
            try:
                self._run_turn(chat, text)
            except Exception as e:
                self.send(chat, f"error: {e}")

    def _run_turn(self, chat: int, text: str):
        self._history.append({"role": "user", "content": text})
        self._history[:] = self._history[-12:]
        body = {"model": self._pick_model(), "messages": self._history, "web": self._web,
                "tools": True, "ask": not self._cfg()["auto"]}
        client = self.backend.app.test_client()
        resp = client.post("/api/chat", json=body, buffered=False)
        acc, files, buf = "", [], ""
        for chunk in resp.iter_encoded():
            buf += chunk.decode("utf-8", "replace")
            *blocks, buf = buf.split("\n\n")
            for b in blocks:
                ev = re.search(r"event: (.*)", b)
                dl = re.search(r"data: (.*)", b, re.S)
                if not ev:
                    continue
                data = json.loads(dl.group(1)) if dl else None
                e = ev.group(1)
                if e == "token":
                    acc += data
                elif e == "tool_call":
                    self.send(chat, f"🔧 {data['name']}")
                    if data["name"] == "write_file" and isinstance(data.get("args"), dict):
                        files.append(str(data["args"].get("path", "")))
                elif e == "tool_result":
                    files += FILE_RE.findall(str(data.get("result", "")))
                elif e == "approval":
                    arg = json.dumps(data.get("args", {}))[:300]
                    self.send(chat, f"Allow {data['tool']}?\n{arg}", reply_markup={"inline_keyboard": [[
                        {"text": "✅ Approve", "callback_data": f"a:{data['id']}:1"},
                        {"text": "⛔ Deny", "callback_data": f"a:{data['id']}:0"}]]})
                elif e == "error":
                    self.send(chat, f"error: {data}")
        if acc.strip():
            self._history.append({"role": "assistant", "content": acc})
            self.send(chat, acc.strip())
        sent = set()
        for rel in files:
            full = self._safe_path(rel) if rel and not os.path.isabs(rel) else self._safe_path(os.path.relpath(rel, tools.SANDBOX)) if rel else None
            if full and full not in sent and os.path.isfile(full) and os.path.getsize(full) <= MAX_FILE:
                sent.add(full)
                try:
                    self.send_file(chat, full)
                except Exception as e:
                    self.send(chat, f"could not send {os.path.basename(full)}: {e}")
            if len(sent) >= 5:
                break
