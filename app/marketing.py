"""Seasonal SEO, sales, marketing campaigns and ideas (the Marketing tab).

Season rows are calendar facts (dates of the sabbats, solstices and the big
shopping days). Everything else is his to add. A season's "get ready by" date
is six weeks before it starts, a planning default he can change per row.
"""
import datetime

from . import record
from .ward import actionlog

KINDS = ["Season", "Sale", "SEO change", "Campaign", "Idea"]
STATUSES = ["Idea", "Planned", "Ready", "Running", "Done", "Dropped"]
LEAD_DAYS = 42


def _d(s: str):
    try:
        return datetime.date.fromisoformat(s)
    except (TypeError, ValueError):
        return None


def view() -> dict:
    today = datetime.date.today()
    rows = [r for r in record.rows("Marketing") if r.get("Status") != "Dropped"]
    by = {k: [] for k in KINDS}
    for r in rows:
        r["start_d"], r["end_d"] = _d(r.get("Start")), _d(r.get("End"))
        if r["start_d"]:
            r["days_to"] = (r["start_d"] - today).days
            r["prep_by"] = (r["start_d"] - datetime.timedelta(days=LEAD_DAYS)).isoformat()
            r["prep_late"] = r["days_to"] <= LEAD_DAYS and r.get("Status") not in ("Ready", "Running", "Done")
        # a blank or hand-typed Kind the page has no section for shows under Ideas
        by[r.get("Kind") if r.get("Kind") in KINDS else "Idea"].append(r)
    upcoming = sorted([r for r in rows if r.get("start_d") and (r.get("end_d") or r["start_d"]) >= today],
                      key=lambda r: r["start_d"])[:12]
    for k in by:
        by[k].sort(key=lambda r: r.get("Start") or "9999")
    return {"by": by, "upcoming": upcoming, "kinds": KINDS, "statuses": STATUSES,
            "lead_days": LEAD_DAYS}


def add(kind, title, start, end, platforms, details, who="Sam", why="") -> str:
    mid = record.next_id("Marketing", "M-")
    record.append("Marketing", {
        "ID": mid, "Kind": kind if kind in KINDS else "Idea", "Title": title, "Start": start, "End": end,
        "Platforms": platforms, "Details": details, "Status": "Idea" if kind == "Idea" else "Planned",
        "Owner": who, "Source": f"added by {who}", "As of": actionlog.now_central()[:10],
        "Why it's here": why or "You added it."})
    actionlog.log(who, f"Marketing: added {kind} \"{title[:80]}\".")
    return mid


EDITABLE = ["Title", "Start", "End", "Platforms", "Details", "Why it's here"]


def edit(mid: str, values: dict, who: str = "Sam") -> None:
    r = record.find("Marketing", "ID", mid)
    if not r:
        return
    changed = []
    for f in EDITABLE:
        v = (values.get(f) or "").strip()
        if f in values and v != (r.get(f) or ""):
            record.set_cell("Marketing", r["_row"], f, v)
            changed.append(f)
    if changed:
        record.set_cell("Marketing", r["_row"], "As of", actionlog.now_central()[:10])
        actionlog.log(who, f"Marketing: edited {', '.join(changed)} on \"{r.get('Title', '')[:60]}\".")


def set_status(mid: str, status: str, who: str = "Sam") -> None:
    r = record.find("Marketing", "ID", mid)
    if r and status in STATUSES:
        record.set_cell("Marketing", r["_row"], "Status", status)
        record.set_cell("Marketing", r["_row"], "As of", actionlog.now_central()[:10])
        actionlog.log(who, f"Marketing: {r.get('Title', '')[:60]} is now {status}.")


def hand(mid: str, who: str = "Sam") -> None:
    r = record.find("Marketing", "ID", mid)
    if not r:
        return
    duty = record.duty().get("passes") or "Claude"
    record.append("Requests", {
        "ID": record.next_id("Requests", "S-"), "When (Central)": actionlog.now_central(),
        "His words (verbatim)": (f"Prepare {r.get('Kind', '')}: {r.get('Title', '')} "
                                 f"({r.get('Start', '')} to {r.get('End', '')}, {r.get('Platforms', '')}). "
                                 f"{r.get('Details', '')} Drafts to his Inbox; nothing goes live without his click."),
        "About": "marketing", "For": duty, "Status": "open", "Result": "", "Updated": ""})
    set_status(mid, "Planned", who)
    actionlog.log(who, f"Marketing: handed \"{r.get('Title', '')[:60]}\" to {duty}.")
