"""Everything logged: who did what, and when.

Every action goes to data/actions.jsonl on the laptop straight away. The
record module also copies each entry to the Sheet's Log tab. Secrets never
reach here: callers pass plain descriptions, and scrub() masks anything that
looks like a key or token as a second line of defence.
"""
import datetime
import json
import queue
import re
import threading

from .. import paths

ACTIONS_FILE = paths.DATA / "actions.jsonl"
WHO = ("Sam", "Claude", "Kimi", "ChatGPT", "App")
_lock = threading.Lock()
_listeners = []

_SECRETISH = re.compile(r"([A-Za-z0-9_\-]{32,}|ya29\.[\w\-.]+|1//[\w\-]+)")


def scrub(s: str) -> str:
    return _SECRETISH.sub("[hidden]", s or "")


def now_central() -> str:
    from zoneinfo import ZoneInfo
    return datetime.datetime.now(ZoneInfo("America/Chicago")).strftime(
        "%Y-%m-%d %H:%M")


def on_entry(fn) -> None:
    _listeners.append(fn)


# Listeners (the Sheet's Log tab) run on one background worker, in order, so a
# button click never waits on Google. The laptop file above is written first,
# synchronously, so nothing is lost if the Sheet copy is slow or fails.
_outbox: "queue.Queue[dict]" = queue.Queue()


def _deliver() -> None:
    while True:
        entry = _outbox.get()
        for fn in list(_listeners):
            try:
                fn(entry)
            except Exception:  # noqa: BLE001 - logging must never break an action
                pass


threading.Thread(target=_deliver, daemon=True, name="actionlog-listeners").start()


def log(who: str, what: str, **detail) -> dict:
    if who not in WHO:
        who = "App"
    entry = {"when": now_central(), "who": who, "what": scrub(what)}
    if detail:
        entry["detail"] = {k: scrub(str(v)) for k, v in detail.items()}
    with _lock:
        with open(ACTIONS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")
    if _listeners:
        _outbox.put(entry)
    return entry


def recent(limit: int = 100) -> list[dict]:
    if not ACTIONS_FILE.exists():
        return []
    lines = ACTIONS_FILE.read_text(encoding="utf-8").splitlines()[-limit:]
    out = []
    for ln in lines:
        try:
            out.append(json.loads(ln))
        except ValueError:
            pass
    return list(reversed(out))
