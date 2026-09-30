"""Secret storage: Windows Credential Manager / macOS Keychain via `keyring`.

Falls back to NightCrew-data/vault.json (chmod 600, plaintext) ONLY if no OS keyring
works (e.g. headless Linux) — backend() says which one is in use so the UI can show it.
"""
from __future__ import annotations

import json
import os
import sys

import paths

SERVICE = "NightCrew"
_kr = None
try:
    import keyring
    from keyring.errors import KeyringError, PasswordDeleteError
    _kr = keyring
except Exception:                                   # keyring missing
    KeyringError = PasswordDeleteError = Exception  # type: ignore


def _file() -> str:
    return paths.data("vault.json")


def _fload() -> dict:
    try:
        with open(_file(), encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _fsave(d: dict) -> None:
    with open(_file(), "w", encoding="utf-8") as f:
        json.dump(d, f)
    try:
        os.chmod(_file(), 0o600)
    except Exception:
        pass


_OK: list = []


def _os_ok() -> bool:
    """Only Windows Credential Manager / macOS Keychain are trusted; elsewhere use the file."""
    if not _OK:
        ok = False
        if _kr is not None and sys.platform in ("win32", "darwin"):
            try:
                ok = not any(x in type(_kr.get_keyring()).__name__.lower()
                             for x in ("fail", "null", "plaintext", "chainer"))
            except BaseException:                      # broken backend plugins can even panic
                ok = False
        _OK.append(ok)
    return _OK[0]


def backend() -> str:
    return "os-keychain" if _os_ok() else "file (no OS keychain found)"


def get(name: str) -> str:
    if _os_ok():
        try:
            return _kr.get_password(SERVICE, name) or ""
        except BaseException:
            pass
    return _fload().get(name, "")


def put(name: str, value: str) -> None:
    if not value:
        return delete(name)
    if _os_ok():
        try:
            _kr.set_password(SERVICE, name, value)
            return
        except Exception:
            pass
    d = _fload()
    d[name] = value
    _fsave(d)


def delete(name: str) -> None:
    if _os_ok():
        try:
            _kr.delete_password(SERVICE, name)
        except Exception:
            pass
    d = _fload()
    if name in d:
        del d[name]
        _fsave(d)
