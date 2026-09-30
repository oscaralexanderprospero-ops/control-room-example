"""His phone, through Tailscale (his ruling, 27 Sep 2026: the full Control
Room on his phone).

The app still listens only on 127.0.0.1. Tailscale's own "serve" passes
requests from his tailnet (his devices, signed in to his Tailscale account)
to that local address over HTTPS, and stamps each one with the Tailscale
login it came from. A request gets in by the phone door only when all of
these hold:
  - the phone door is switched on (it is, once he pairs a phone),
  - the Host is this laptop's Tailscale name,
  - it arrived through Tailscale serve (from 127.0.0.1) carrying his login,
  - it carries a paired phone's cookie.
Pairing is a one-time code shown as a QR on the laptop screen (10 minutes,
used once). Only a hash of each phone's token is kept. "Forget my phone"
closes the door again.
"""
import datetime
import hashlib
import hmac
import json
import os
import secrets
import shutil
import subprocess
import threading
import time

from .. import paths

CONFIG = paths.CONFIG / "phone.json"
COOKIE = "oms_phone"
COOKIE_DAYS = 180
PAIR_MINUTES = 10
_lock = threading.Lock()
# The one live pairing code is kept (as a hash, with its expiry) in phone.json,
# so an app restart while he is scanning doesn't cancel it.


def _exe() -> str | None:
    for p in (shutil.which("tailscale"), r"C:\Program Files\Tailscale\tailscale.exe"):
        if p and os.path.exists(p):
            return p
    return None


def _load() -> dict:
    try:
        return json.loads(CONFIG.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"enabled": False, "host": "", "login": "", "devices": {}}


def _save(c: dict) -> None:
    CONFIG.write_text(json.dumps(c, indent=2), encoding="utf-8")


def _run(*args, timeout=15) -> tuple[int, str]:
    exe = _exe()
    if not exe:
        return 127, ""
    r = subprocess.run([exe, *args], capture_output=True, text=True, timeout=timeout,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode, r.stdout


_cache = {"t": 0.0, "v": None}


def tailscale() -> dict:
    """What Tailscale says about this laptop (read only), cached 30 s."""
    if time.time() - _cache["t"] < 30 and _cache["v"]:
        return _cache["v"]
    out = {"installed": bool(_exe()), "running": False, "host": "", "login": "", "serving": False}
    if out["installed"]:
        try:
            code, txt = _run("status", "--json")
            s = json.loads(txt) if code == 0 and txt.strip() else {}
            out["running"] = s.get("BackendState") == "Running"
            me = s.get("Self") or {}
            out["host"] = (me.get("DNSName") or "").rstrip(".").lower()
            user = (s.get("User") or {}).get(str(me.get("UserID")), {})
            out["login"] = user.get("LoginName", "")
            # without HTTPS certificates on his tailnet, serve is plain http;
            # the link itself is still WireGuard-encrypted end to end
            out["scheme"] = "https" if s.get("CertDomains") else "http"
            code, txt = _run("serve", "status", "--json")
            out["serving"] = code == 0 and os.environ.get("CONTROL_ROOM_PORT", "8765") in txt
        except (OSError, ValueError, subprocess.TimeoutExpired):
            pass
    _cache.update(t=time.time(), v=out)
    return out


def status() -> dict:
    c, t = _load(), tailscale()
    if not t["installed"]:
        step = "Tailscale isn't installed on this laptop yet."
    elif not t["running"]:
        step = "Tailscale is installed but not signed in on this laptop."
    elif not t["serving"]:
        step = "Tailscale is on. Claude still has to connect it to the Control Room."
    elif not c.get("devices"):
        step = "Ready to link your phone."
    else:
        step = "Your phone is linked."
    return {"step": step, "ts": t, "enabled": c.get("enabled", False),
            "phones": len(c.get("devices", {})), "host": c.get("host") or t["host"],
            "ready": t["running"] and t["serving"]}


# ------------------------------------------------------------------ the door
def host() -> str:
    c = _load()
    return c.get("host", "") if c.get("enabled") else ""


def host_ok(host_header: str | None) -> bool:
    h = host()
    return bool(h) and (host_header or "").split(":")[0].lower() == h


def login_ok(header: str | None) -> bool:
    c = _load()
    return bool(c.get("login")) and hmac.compare_digest((header or "").lower(), c["login"].lower())


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def is_phone(cookie: str | None) -> bool:
    if not cookie:
        return False
    return _hash(cookie) in _load().get("devices", {})


# ------------------------------------------------------------------ pairing
def start_pairing() -> str | None:
    """A one-time code for the QR on the laptop screen. Also opens the
    phone door for this laptop's Tailscale name and his login."""
    t = tailscale()
    if not (t["running"] and t["serving"] and t["host"] and t["login"]):
        return None
    with _lock:
        c = _load()
        code = secrets.token_urlsafe(24)
        c.update(enabled=True, host=t["host"], login=t["login"], scheme=t.get("scheme", "https"),
                 pairing={"hash": _hash(code), "expires": time.time() + PAIR_MINUTES * 60})
        c.setdefault("devices", {})
        _save(c)
    return f"{c['scheme']}://{t['host']}/pair?c={code}"


def scheme() -> str:
    return _load().get("scheme", "https")


def pair(code: str, device: str) -> str | None:
    """Use a pairing code once; returns the phone's new token."""
    with _lock:
        c = _load()
        p = c.pop("pairing", None) or {}
        if not code or not hmac.compare_digest(p.get("hash", ""), _hash(code)) or p.get("expires", 0) < time.time():
            if p and p.get("expires", 0) >= time.time():
                c["pairing"] = p          # a wrong code doesn't use up the real one
            return None
        token = secrets.token_urlsafe(32)
        c.setdefault("devices", {})[_hash(token)] = {
            "added": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"), "device": device[:120]}
        _save(c)
    return token


def forget() -> None:
    with _lock:
        c = _load()
        c.update(enabled=False, devices={})
        c.pop("pairing", None)
        _save(c)


def qr_svg(url: str) -> str:
    import segno
    import io
    buf = io.BytesIO()
    segno.make(url, error="m").save(buf, kind="svg", scale=6, border=2, dark="#000", light="#fff")
    return buf.getvalue().decode()
