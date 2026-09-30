"""What's stuck, worked out fresh each time: routines on the laptop that were
due and haven't reported in (or reported a failure), requests nobody has
picked up, and posts past their time. Each comes back as one My day item
marked urgent, with a line he can send to the team.

A routine is only judged once it has reported in at least once, so one that
simply doesn't report yet is never called stuck. Cloud routines can't reach
the laptop at all, so only laptop routines are watched.
"""
import datetime
import json
import re

from . import pacing, paths, record

PASS_RUNS = paths.DATA / "pass_runs.json"
GRACE = datetime.timedelta(hours=2)          # runs can take a while, and start late
REQUEST_STUCK = datetime.timedelta(hours=6)
POST_STUCK = datetime.timedelta(hours=3)
DAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


def _at(s: str):
    try:
        return datetime.datetime.strptime((s or "").strip()[:16], "%Y-%m-%d %H:%M").replace(tzinfo=pacing.CENTRAL)
    except ValueError:
        return None


def when_label(dt: datetime.datetime) -> str:
    today = pacing.now().date()
    day = "today" if dt.date() == today else "yesterday" if dt.date() == today - datetime.timedelta(days=1) \
        else dt.strftime("%a %d %b").replace(" 0", " ")
    return f"{day} {dt.strftime('%I:%M %p').lstrip('0')}"


def _times(text: str) -> list[tuple[int, int]]:
    out = []
    for h, m, ap in re.findall(r"(\d{1,2})(?::(\d{2}))?\s*(am|pm)", text.lower()):
        out.append((int(h) % 12 + (12 if ap == "pm" else 0), int(m or 0)))
    return out


def _runs_on(days: str, day: datetime.date) -> bool:
    days = days.lower()
    if "daily" in days:
        return True
    if "1st of month" in days:
        return day.day == 1
    return any(d in days for d in DAYS) and DAYS[day.weekday()] in days


def slots(central_time: str, days: str, day: datetime.date) -> list[datetime.datetime]:
    """When a routine should start on a given day, from the Tasks tab's words
    ("11:30am, 5:30pm"; "hourly, :05 past, 8am-10pm"; "Mon, Wed, Fri")."""
    if not _runs_on(days, day):
        return []
    t = central_time.lower()
    mk = lambda h, m: datetime.datetime(day.year, day.month, day.day, h, m, tzinfo=pacing.CENTRAL)  # noqa: E731
    if "hourly" in t:
        minute, span = re.search(r":(\d{2})", t), _times(t)
        if not minute or len(span) < 2:
            return []
        return [mk(h, int(minute.group(1))) for h in range(span[0][0], span[1][0] + 1)]
    return [mk(h, m) for h, m in _times(t)]


def _runs() -> dict:
    try:
        return json.loads(PASS_RUNS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def routines(now=None) -> list[dict]:
    """Laptop routines that are stuck: [{name, why}]."""
    now = now or pacing.now()
    runs, out = _runs(), []
    for r in record.rows("Tasks"):
        name, where = r.get("Pass", ""), f"{r.get('Source', '')} {r.get('Notes', '')}".lower()
        if (r.get("State") or "").lower() != "on" or name not in runs:
            continue
        if "desktop scheduled task" not in where and "laptop" not in where:
            continue
        last = runs[name]
        last_at = _at(last.get("when", ""))
        if last.get("outcome") == "failed":
            out.append({"name": name, "why": f"{name} failed {when_label(last_at) if last_at else ''}: "
                                            f"{(last.get('summary') or '')[:120]}"})
            continue
        due = None
        for back in range(0, 35):
            day = now.date() - datetime.timedelta(days=back)
            ok = [s for s in slots(r.get("Central time", ""), r.get("Days", ""), day) if s <= now - GRACE]
            if ok:
                due = max(ok)
                break
        if due and last_at and last_at < due:
            out.append({"name": name, "why": f"{name} was due {when_label(due)} and hasn't reported in "
                                            f"(last: {when_label(last_at)})"})
    return out


def requests(now=None) -> list[dict]:
    """Team requests nobody has picked up, or started and gone quiet."""
    now = now or pacing.now()
    out = []
    for r in record.rows("Requests"):
        st = r.get("Status", "")
        since = _at(r.get("Updated", "")) if st == "working" else _at(r.get("When (Central)", "")) \
            if st == "open" else None
        if since and now - since >= REQUEST_STUCK:
            out.append({"id": r.get("ID", ""), "for": r.get("For", ""), "since": since, "status": st,
                        "what": (r.get("His words (verbatim)") or "")[:70]})
    return out


def posts(jobs: list[dict], now=None) -> int:
    now = now or pacing.now()
    n = 0
    for j in jobs:
        if j.get("status") in ("waiting", "handed to agent", "claimed") and not j.get("held"):
            try:
                if now - datetime.datetime.fromisoformat(j["not_before"]) >= POST_STUCK:
                    n += 1
            except (KeyError, ValueError, TypeError):
                continue
    return n


def items(jobs: list[dict], connected: bool, sheet_error: str, pending: int, defender_ok: bool) -> list[dict]:
    """Everything stuck, as urgent My day items (piles as one item each)."""
    out = []
    # among urgent things: the laptop and Sheet first (nothing works without
    # them), then customers (rank 1, set by the caller), then what the team
    # can take off his hands with one click
    rank = {"Laptop": 0, "Sheet": 0, "Routine": 2, "Routines": 2, "Stuck": 3, "Posts": 3}

    def add(what, link, kind, ask):
        out.append({"what": what, "link": link, "kind": kind, "overdue": False, "soft": False,
                    "urgent": True, "ask": ask, "rank": rank[kind]})
    if not defender_ok:
        add("Windows Defender needs you: the laptop isn't protected right now", "/ward", "Laptop", "")
    if not connected and record.status().get("source") != "demo data":
        add("The app has lost its link to your Sheet. Press Reconnect Google (under Menu)", "/", "Sheet", "")
    elif pending and sheet_error:
        add(f"{pending} change{'s' if pending > 1 else ''} haven't reached your Sheet yet", "/", "Sheet",
            f"{pending} changes are stuck on the laptop and haven't reached the Sheet (error: {sheet_error[:150]}).")
    stuck = routines()
    if len(stuck) == 1:
        add(f"Routine stuck: {stuck[0]['why']}", "/duty", "Routine", stuck[0]["why"])
    elif stuck:
        add(f"{len(stuck)} routines are stuck: " + ", ".join(s["name"] for s in stuck), "/duty", "Routines",
            "; ".join(s["why"] for s in stuck))
    reqs = requests()
    if reqs:
        who = sorted({r["for"] for r in reqs})
        oldest = min(r["since"] for r in reqs)
        add(f"{len(reqs)} request{'s' if len(reqs) > 1 else ''} to {' and '.join(who)} "
            f"{'have' if len(reqs) > 1 else 'has'} gone untouched since {when_label(oldest)}", "/requests",
            "Stuck", "; ".join(f"{r['id']} for {r['for']} ({r['status']} since {when_label(r['since'])}): "
                               f"{r['what']}" for r in reqs))
    n = posts(jobs)
    if n:
        add(f"{n} post{'s are' if n > 1 else ' is'} stuck more than 3 hours past {'their' if n > 1 else 'its'} time",
            "/post", "Posts", f"{n} posting jobs are more than 3 hours past their time and still not done.")
    return out
