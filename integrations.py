"""Telegram + Gmail wiring. Secrets live in NightCrew-data/integrations.json (gitignored,
chmod 600 where supported) — never in the repo, never returned by the API in full.

    telegram: token, owner_id (0 = not paired), pair_code, model, auto (approve tools from phone)
    gmail:    address, app_password (Google *app password*, not your login), whitelist[]
"""
from __future__ import annotations

import json
import os
import secrets
import threading

import paths

_LOCK = threading.Lock()
DEFAULTS = {
    "telegram": {"enabled": False, "token": "", "owner_id": 0, "pair_code": "", "model": "", "auto": False},
    "gmail": {"enabled": False, "address": "", "app_password": "", "whitelist": [], "interval": 60},
}
SECRET_KEYS = {"telegram": ("token",), "gmail": ("app_password",)}


def _path() -> str:
    return paths.data("integrations.json")


def load() -> dict:
    d = json.loads(json.dumps(DEFAULTS))
    try:
        with open(_path(), encoding="utf-8") as f:
            saved = json.load(f)
        for sec in d:
            d[sec].update({k: v for k, v in (saved.get(sec) or {}).items() if k in d[sec]})
    except Exception:
        pass
    return d


def save(d: dict) -> None:
    with _LOCK:
        with open(_path(), "w", encoding="utf-8") as f:
            json.dump(d, f, indent=2)
        try:
            os.chmod(_path(), 0o600)
        except Exception:
            pass


def update(upd: dict) -> dict:
    """Merge a partial update. An empty/`***` secret means 'keep the stored one'."""
    d = load()
    for sec, vals in (upd or {}).items():
        if sec not in d or not isinstance(vals, dict):
            continue
        for k, v in vals.items():
            if k not in d[sec]:
                continue
            if k in SECRET_KEYS.get(sec, ()) and (not v or str(v).startswith("*")):
                continue
            if k == "whitelist":
                v = [x.strip().lower() for x in (v if isinstance(v, list) else str(v).replace(",", "\n").split()) if x.strip()]
            if k in ("owner_id", "interval"):
                try:
                    v = int(v)
                except Exception:
                    continue
            d[sec][k] = v
    t = d["telegram"]
    if t["token"] and not t["owner_id"] and not t["pair_code"]:
        t["pair_code"] = f"{secrets.randbelow(10**6):06d}"          # /pair <code> in the bot chat
    if t["owner_id"]:
        t["pair_code"] = ""
    save(d)
    return d


def masked() -> dict:
    d = load()
    for sec, keys in SECRET_KEYS.items():
        for k in keys:
            d[sec][k] = "***" if d[sec][k] else ""
    return d


# ---- lifecycle --------------------------------------------------------------
_RUN = {"tg": None, "gm": None}


def status() -> dict:
    return {"telegram": bool(_RUN["tg"] and _RUN["tg"].running),
            "gmail": bool(_RUN["gm"] and _RUN["gm"].running),
            "telegram_error": getattr(_RUN["tg"], "error", ""),
            "gmail_error": getattr(_RUN["gm"], "error", "")}


def start_all(backend) -> None:
    """(Re)start whatever is enabled. Safe to call repeatedly."""
    for k in ("tg", "gm"):
        if _RUN[k]:
            _RUN[k].stop()
            _RUN[k] = None
    cfg = load()
    import telegram_bridge
    import gmail_listener
    if cfg["telegram"]["enabled"] and cfg["telegram"]["token"]:
        _RUN["tg"] = telegram_bridge.Bridge(backend)
        _RUN["tg"].start()
    if cfg["gmail"]["enabled"] and cfg["gmail"]["address"] and cfg["gmail"]["app_password"]:
        notify = _RUN["tg"].notify_owner if _RUN["tg"] else (lambda text: None)
        _RUN["gm"] = gmail_listener.Listener(notify)
        _RUN["gm"].start()
        if _RUN["tg"]:
            _RUN["tg"].gmail = _RUN["gm"]
