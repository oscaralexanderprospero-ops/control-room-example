"""Kimi Work's four dashboard tabs, copied into the Control Room.

Every widget keeps its rows in the Boards tab of the Sheet (never deleted:
an item is marked done or archived). Numbers carry their source and date;
a blank stays blank. Items copied from Kimi's dashboard carry the date Kimi
showed, so anything older than seven days is flagged STALE.

Widget types:
  tiles      big numbers with caption, source and date
  table      platform rows with numbers (Detail holds "views|sales|followers")
  checklist  tick-off list; Stage can group items (e.g. non-negotiable / core)
  kanban     cards moving through stages
  notes      dated notes, newest first
  log        dated entries with minutes
  tagbank    tags by product line (Stage) and platform
  calendar   built from dated rows across the record (no rows of its own)
  link       points to the app screen that does this job properly
"""
import datetime
import re

from . import record
from .ward import actionlog

KIMI = "Kimi Work dashboard"

# All three boards were removed from the app on 27 Sep 2026 at Sam' request
# (copies of Kimi's tabs that did nothing the rest of the app doesn't do).
# Their rows stay in the Boards tab, marked archived. calendar() below is kept:
# it feeds the 7-day calendar on the Today screen.
BOARDS = {
    "_shop_archived": {
        "title": "Shop and Site",
        "kimi_tab": "Shop and Site Scoreboard",
        "widgets": [
            {"key": "scoreboard", "title": "Shop and Site Scoreboard", "type": "tiles"},
            {"key": "calendar", "title": "Content calendar", "type": "calendar",
             "note": "Rolling seven days, built from what's actually scheduled and due. A plan, not a record."},
            {"key": "focus", "title": "Daily focus: highest priority first", "type": "checklist",
             "groups": ["Non-negotiable", "Core", "Good day"],
             "note": "Rough day: only the non-negotiables. Normal day: add the core. Good day: everything."},
            {"key": "etsy", "title": "Etsy listing pipeline", "type": "kanban",
             "stages": ["Draft", "Needs photos", "Needs SEO", "Needs measurements", "Ready", "Live"]},
            {"key": "media", "title": "Media upload and prep", "type": "link", "href": "/files",
             "note": "Done in Files and Post. Unlike Kimi's widget, the app never crops (your 25 Sep rule)."},
            {"key": "audience", "title": "Publishing and audience", "type": "table",
             "cols": ["Followers", "Note"]},
            {"key": "cadence", "title": "Recurring cadence", "type": "checklist",
             "groups": ["At the bench", "Daily", "Weekly", "Monthly"]},
            {"key": "tasks", "title": "Task checklist", "type": "checklist"},
            {"key": "coach", "title": "Business coach", "type": "notes",
             "note": "Priorities drawn from your Google Docs. Stage holds high / medium / low."},
        ],
    },
    "_stats_archived": {
        "title": "Stats, Tags and SEO",
        "kimi_tab": "Stats, Tags and SEO",
        "widgets": [
            {"key": "stats", "title": "Stats scoreboard", "type": "table",
             "cols": ["Views", "Sales", "Followers"],
             "note": "Filled by hand or by an agent on instruction. A blank is a blank."},
            {"key": "tags", "title": "Keyword and tag bank", "type": "tagbank",
             "stages": ["Canes", "Staves", "Wands", "Pendants"]},
            {"key": "review", "title": "Weekly strategy review", "type": "checklist"},
            {"key": "seo", "title": "SEO task list", "type": "checklist"},
            {"key": "experiments", "title": "Experiment notes", "type": "notes",
             "note": "What you tried, what happened. Corrections keep the original underneath."},
        ],
    },
    # Removed from the app 27 Sep 2026 at his request: the long-form YouTube
    # pipeline it tracked isn't the pipeline in use (shorts run through Files,
    # Inbox and Post). Its rows stay in the Boards tab, marked archived.
    "_video_archived": {
        "title": "Video and Image (archived)",
        "kimi_tab": "Video and Image Pipeline",
        "widgets": [
            {"key": "pipeline", "title": "Production pipeline", "type": "kanban",
             "stages": ["Outlined", "Brief", "Filmed", "Logged", "Cut", "Review", "Published", "Held"]},
            {"key": "upload", "title": "Upload checklist", "type": "checklist"},
            {"key": "ideas", "title": "Video ideas backlog", "type": "notes",
             "note": "Fourteen outlines exist. New ideas go here only if they are not one of them."},
            {"key": "voice", "title": "Voice capture", "type": "link", "href": "/writing#capture",
             "note": "Dictation lives in Writing's Capture box and in Tell the team. Narration is recorded "
                     "in your own voice, never synthesised."},
            {"key": "sessions", "title": "Recording session log", "type": "log",
             "note": "Bench sessions banked toward 10. Seven stills every session: object whole, in hand, "
                     "end grain, stone seat, ferrule or wrap, root or blank, work in progress."},
            {"key": "mediaprep", "title": "Media file prep", "type": "checklist"},
        ],
    },
}


def widget(board: str, key: str) -> dict:
    return next(w for w in BOARDS[board]["widgets"] if w["key"] == key)


def rows(board: str, key: str, include_archived: bool = False) -> list[dict]:
    out = [r for r in record.rows("Boards") if r.get("Board") == board and r.get("Widget") == key]
    if not include_archived:
        out = [r for r in out if r.get("Done") != "archived"]
    return out


def add(board: str, key: str, title: str, who: str = "Sam", **kw) -> str:
    bid = record.next_id("Boards", "B-")
    record.append("Boards", {
        "ID": bid, "Board": board, "Widget": key, "Title": title,
        "Detail": kw.get("detail", ""), "Stage": kw.get("stage", ""), "Owner": kw.get("owner", ""),
        "Platform": kw.get("platform", ""), "Date": kw.get("date", ""), "Done": "",
        "Source": kw.get("source", f"added by {who} in the Control Room"),
        "As of": actionlog.now_central()[:10]})
    actionlog.log(who, f"{BOARDS[board]['title']} / {widget(board, key)['title']}: added \"{title[:80]}\"")
    return bid


def _row(bid: str) -> dict:
    r = record.find("Boards", "ID", bid)
    if not r:
        raise KeyError(bid)
    return r


def toggle(bid: str, who: str = "Sam") -> None:
    r = _row(bid)
    new = "" if r.get("Done") == "yes" else "yes"
    record.set_cell("Boards", r["_row"], "Done", new)
    record.set_cell("Boards", r["_row"], "As of", actionlog.now_central()[:10])
    actionlog.log(who, f"{'Ticked' if new else 'Unticked'}: {r.get('Title', '')[:80]}")


def move(bid: str, step: int, who: str = "Sam") -> None:
    r = _row(bid)
    stages = widget(r["Board"], r["Widget"]).get("stages", [])
    if not stages:
        return
    # a blank or unknown stage counts as "before the first column"
    cur = stages.index(r["Stage"]) if r.get("Stage") in stages else -1
    i = max(0, min(len(stages) - 1, cur + step))
    record.set_cell("Boards", r["_row"], "Stage", stages[i])
    record.set_cell("Boards", r["_row"], "As of", actionlog.now_central()[:10])
    actionlog.log(who, f"Moved \"{r.get('Title', '')[:60]}\" to {stages[i]}")


def set_value(bid: str, field: str, value: str, who: str = "Sam") -> None:
    if field not in ("Detail", "Stage", "Owner", "Date", "Title"):
        raise ValueError(field)
    r = _row(bid)
    record.set_cell("Boards", r["_row"], field, value)
    record.set_cell("Boards", r["_row"], "As of", actionlog.now_central()[:10])
    record.set_cell("Boards", r["_row"], "Source", f"updated by {who} in the Control Room")
    actionlog.log(who, f"Updated {field} of \"{r.get('Title', '')[:60]}\"")


def archive(bid: str, who: str = "Sam") -> None:
    r = _row(bid)
    record.set_cell("Boards", r["_row"], "Done", "archived")
    actionlog.log(who, f"Archived (kept, not deleted): {r.get('Title', '')[:80]}")


def still_true(bid: str, who: str = "Sam") -> None:
    r = _row(bid)
    record.set_cell("Boards", r["_row"], "As of", actionlog.now_central()[:10])
    actionlog.log(who, f"Confirmed still true: {r.get('Title', '')[:80]}")


def calendar(days: int = 7) -> list[dict]:
    """Rolling seven days from today, from real dated rows: scheduled posts,
    writing due dates, and dated board items."""
    from zoneinfo import ZoneInfo
    today = datetime.datetime.now(ZoneInfo("America/Chicago")).date()   # the record's days are Central
    span =[(today + datetime.timedelta(days=i)) for i in range(days)]
    keys = {d.isoformat(): [] for d in span}
    for p in record.rows("Posts"):
        d = p.get("Date (Central)")
        if d in keys and p.get("State") == "scheduled":
            keys[d].append({"kind": p.get("Platform", ""), "text": f"{p.get('Time (Central)', '')} {p.get('Item', '')}"})
    for w in record.rows("Writing"):
        d = w.get("Due")
        st = w.get("Status", "")
        # finished or decided (a bare "no" prefix would also hide "not asked yet")
        closed = st.startswith(("answered", "yes", "drop", "approved", "send back")) or \
            st == "no" or st.startswith(("no (", "no:"))
        if d in keys and not closed and w.get("Kind") != "shipped":
            keys[d].append({"kind": "Writing", "text": w.get("Item", "")[:90]})
    for m in record.rows("Marketing"):
        if m.get("Status") in ("Dropped", "Done"):
            continue
        for field, word in (("Start", "starts"), ("End", "ends")):
            d = m.get(field)
            if d in keys and not (field == "End" and d == m.get("Start")):
                keys[d].append({"kind": "Marketing", "text": f"{m.get('Title', '')[:70]} {word}"})
    for tab, due, label in (("Orders", "Ship or answer by", "Orders"), ("Custom Orders", "Due", "Custom order")):
        for o in record.rows(tab):
            d = (o.get(due) or "")[:10]
            if d in keys and o.get("Status") not in ("Shipped", "Delivered", "Answered", "Closed", "Done", "Declined"):
                keys[d].append({"kind": label, "text": (o.get("Item") or o.get("What") or "")[:70]})
    for t in record.rows("Tasks"):
        days_ = t.get("Days", "").lower()
        words = re.findall(r"[a-z]+", days_)     # whole words: "mon" is not in "month"
        if "daily" in words:
            continue    # daily passes would fill every day and say nothing
        for d in span:
            # the Tasks tab says "Mon, Wed, Fri", "Sat" or "1st of month"
            runs = d.strftime("%a").lower() in words or ("1st of month" in days_ and d.day == 1)
            if t.get("State") == "on" and runs:
                keys[d.isoformat()].append({"kind": t.get("Agent", ""), "text": f"{t.get('Central time', '')} {t.get('Pass', '')}"})
    return [{"date": d, "items": keys[d.isoformat()]} for d in span]
