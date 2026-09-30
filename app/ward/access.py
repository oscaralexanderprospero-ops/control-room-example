"""Who may talk to the app.

- Sam' browser: gets in through the desktop shortcut, which opens
  /enter?t=<launch key>. That sets a cookie only this laptop's browser holds.
- Agents (Claude, Kimi): send header "X-Agent-Key: <their key>". Each agent has
  its own key in config\\agent_keys.json, which is local and never logged.
- Anything else: gets the Address and a plain notice that access is not
  authorized, and the attempt goes on the Suspicious list.

The server only listens on 127.0.0.1, and the Host header must be local,
so nothing on the network can reach it. The one exception is his paired
phone through Tailscale serve (his ruling, 27 Sep 2026; see phone.py).
"""
import hmac
import json
import secrets

from .. import paths

KEYS_FILE = paths.CONFIG / "agent_keys.json"
LAUNCH_FILE = paths.CONFIG / "launch_key.txt"
COOKIE = "oms_session"
AGENTS = ("claude", "kimi")
LOCAL_HOSTS = {"127.0.0.1", "localhost"}


_keys_cache: dict | None = None


def _load_keys() -> dict:
    global _keys_cache
    if _keys_cache is not None:
        return _keys_cache
    if KEYS_FILE.exists():
        _keys_cache = json.loads(KEYS_FILE.read_text(encoding="utf-8"))
        return _keys_cache
    keys = {a: secrets.token_urlsafe(32) for a in AGENTS}
    KEYS_FILE.write_text(json.dumps(keys, indent=2), encoding="utf-8")
    _keys_cache = keys
    return keys


def launch_key() -> str:
    if not LAUNCH_FILE.exists():
        LAUNCH_FILE.write_text(secrets.token_urlsafe(32), encoding="utf-8")
    return LAUNCH_FILE.read_text(encoding="utf-8").strip()


_SESSION = secrets.token_urlsafe(32)   # new each time the app starts


def session_value() -> str:
    return _SESSION


def agent_for_key(key: str | None) -> str | None:
    if not key:
        return None
    for name, k in _load_keys().items():
        if hmac.compare_digest(k, key):
            return name.capitalize()
    return None


def is_sam(cookie: str | None) -> bool:
    return bool(cookie) and hmac.compare_digest(cookie, _SESSION)


def host_ok(host_header: str | None) -> bool:
    host = (host_header or "").rsplit(":", 1)[0].strip("[]").lower()
    return host in LOCAL_HOSTS


def ensure_keys() -> None:
    _load_keys()
    launch_key()
