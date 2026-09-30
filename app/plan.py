"""My day: one thing at a time.

His own items (typed or spoken, with an optional time) and what the app
already knows is waiting on him, in one ordered list with a single "Now" at
the top. Kept on the laptop in data\\plan.json, one entry per day. His
unfinished items carry over to the next day, so nothing he wrote down is
lost; nothing is ever deleted, only marked done or dropped.
"""
import datetime
import hashlib
import json
import threading

from . import pacing, paths
from .ward import actionlog

FILE = paths.DATA / "plan.json"
KEEP_DAYS = 60
SOON_MIN = 15          # a timed item joins the list this many minutes before its time
_lock = threading.Lock()


def _load() -> dict:
    try:
        return json.loads(FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {"next": 1, "days": {}}


def _save(d: dict) -> None:
    cutoff = (pacing.now().date() - datetime.timedelta(days=KEEP_DAYS)).isoformat()
    d["days"] = {k: v for k, v in d["days"].items() if k >= cutoff}
    FILE.write_text(json.dumps(d, ensure_ascii=False, indent=1), encoding="utf-8")


def today() -> str:
    return pacing.now().date().isoformat()


def _blank() -> dict:
    return {"mine": [], "done": {}, "later": [], "top": [], "dropped": [], "carried": False}


def _day(d: dict, day: str) -> dict:
    """The day's state, bringing forward his unfinished items from the last
    day he used, the first time a day is opened."""
    st = d["days"].setdefault(day, _blank())
    for k, v in _blank().items():
        st.setdefault(k, v)
    if not st["carried"] and day <= today():
        before = sorted(k for k in d["days"] if k < day)
        if before:
            prev = d["days"][before[-1]]
            have = {m["id"] for m in st["mine"]}
            left = [m for m in prev.get("mine", [])
                    if m["id"] not in prev.get("done", {}) and m["id"] not in prev.get("dropped", [])
                    and m["id"] not in have]
            st["mine"] = [dict(m, **{"from": m.get("from") or before[-1]}) for m in left] + st["mine"]
        st["carried"] = True
    return st


def key_for(kind: str, what: str) -> str:
    return "a-" + hashlib.sha1(f"{kind}|{what}".encode("utf-8")).hexdigest()[:10]


def add(text: str, time: str = "", day: str = "", who: str = "Sam") -> str:
    text = " ".join(text.split())[:300]
    if not text:
        return ""
    day = day or today()
    with _lock:
        d = _load()
        st = _day(d, day)
        mid = f"m-{d.get('next', 1)}"
        d["next"] = d.get("next", 1) + 1
        st["mine"].append({"id": mid, "text": text, "time": time[:5],
                           "added": actionlog.now_central(), "from": ""})
        _save(d)
    actionlog.log(who, f"My day: added \"{text[:80]}\"" + (f" at {time}" if time else "")
                  + ("" if day == today() else f" for {day}"))
    return mid


OPS = ("done", "undo", "later", "now", "drop")


def mark(key: str, op: str, what: str = "", who: str = "Sam") -> None:
    if op not in OPS or not key:
        return
    with _lock:
        d = _load()
        st = _day(d, today())
        mine = {m["id"]: m for m in st["mine"]}
        label = (mine[key]["text"] if key in mine else what)[:300]
        for lst in ("later", "top"):
            if key in st[lst]:
                st[lst].remove(key)
        if op == "done":
            st["done"][key] = {"text": label, "at": pacing.now().strftime("%H:%M")}
        elif op == "undo":
            st["done"].pop(key, None)
        elif op == "later":
            st["later"].append(key)
        elif op == "now":
            st["top"].insert(0, key)
        elif op == "drop" and key in mine and key not in st["dropped"]:
            st["dropped"].append(key)
        _save(d)
    if op in ("done", "drop"):
        actionlog.log(who, f"My day: {'done' if op == 'done' else 'dropped'} \"{label[:80]}\"")


def _mins(hhmm: str) -> int | None:
    try:
        h, m = hhmm.split(":")
        return int(h) * 60 + int(m)
    except (ValueError, AttributeError):
        return None


def view(auto: list[dict]) -> dict:
    """auto: what the app knows is waiting on him, each {what, link, kind,
    overdue, soft}. Returns the Now item, the ordered list, what's put off,
    what's set for later today, what's done, and tomorrow's list so far."""
    with _lock:
        d = _load()
        fresh = not d["days"].get(today(), {}).get("carried")
        st = _day(d, today())
        tomorrow = (pacing.now().date() + datetime.timedelta(days=1)).isoformat()
        tmr = [m for m in d["days"].get(tomorrow, {}).get("mine", [])]
        if fresh:
            _save(d)
    now = pacing.now()
    now_min = now.hour * 60 + now.minute
    items = []
    for i, m in enumerate(st["mine"]):
        if m["id"] in st["dropped"]:
            continue
        t = _mins(m.get("time", ""))
        items.append({"key": m["id"], "what": m["text"], "kind": "Yours", "link": "", "time": m.get("time", ""),
                      "from": m.get("from", ""), "mine": True, "overdue": False, "soft": False,
                      "_t": t, "_i": i, "_waiting": t is not None and t - SOON_MIN > now_min})
    for a in auto:
        items.append(dict(a, key=key_for(a["kind"], a["what"]), mine=False, time="", **{"_t": None, "_i": 0,
                                                                                         "_waiting": False}))

    def bucket(x):
        if x.get("urgent"):                       # needs him now: always first
            return (0, x.get("rank", 1))
        if x["key"] in st["top"]:
            return (1, st["top"].index(x["key"]))
        if x["overdue"]:
            return (2, 0)
        if x["mine"] and x["_t"] is not None:
            return (3, x["_t"])
        if not x["mine"] and not x["soft"]:
            return (4, 0)
        if x["mine"]:
            return (5, x["_i"])
        return (6, 0)

    live = [x for x in items if x["key"] not in st["done"]]
    active = sorted([x for x in live if x["key"] not in st["later"] and not x["_waiting"]], key=bucket)
    waiting = sorted([x for x in live if x["_waiting"] and x["key"] not in st["later"]], key=lambda x: x["_t"])
    later = [x for x in live if x["key"] in st["later"]]
    later.sort(key=lambda x: st["later"].index(x["key"]))
    done = [{"key": k, **v} for k, v in st["done"].items()]
    done.sort(key=lambda x: x["at"], reverse=True)
    return {"now": active[0] if active else None, "next": active[1:], "waiting": waiting, "later": later,
            "done": done, "tomorrow": tmr, "day": today(), "tomorrow_day": tomorrow,
            "urgent": sum(1 for x in active if x.get("urgent"))}


def now_item(auto: list[dict]) -> dict | None:
    return view(auto)["now"]
