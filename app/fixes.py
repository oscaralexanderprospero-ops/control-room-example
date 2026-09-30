"""Fix-it buttons: every problem the dashboard shows carries its fix beside it.

Kinds of fix:
  answer  Sam types or picks an answer; it is recorded as his decision.
  open    opens the exact page where only he (or a platform) can do it.
  app     the app does it itself (e.g. move duplicates, re-check a feed).
  hand    hands it to the agent on duty, as a request in the Requests tab.
If nothing can be done from here, the item says so plainly.
"""
import json
import urllib.request

from . import files, record
from .ward import actionlog

BSKY = ("https://public.api.bsky.app/xrpc/app.bsky.feed.getAuthorFeed?actor="
        "did:plc:YOUR-BLUESKY-DID&limit=30&filter=posts_no_replies")

# Buttons per Approvals row. Rows not listed get buttons from their Kind.
FIXES = {
    "A-01": [("Yes, publish it as planned", "answer", "Yes"), ("No", "answer", "No")],
    "A-02": [("Open the draft", "open", "https://www.etsy.com/your/shops/me/tools/listings"), ("Done", "answer", "Done")],
}

# The things the import could not settle, as answerable items.
QUESTIONS = [
    ("Example question: should the walnut stick also go to Pixelfed?", [("Yes", "answer", "Yes"), ("No", "answer", "No")]),
]


def buttons_for(row: dict) -> list[tuple]:
    if row.get("ID") in FIXES:
        return FIXES[row["ID"]]
    try:
        q = json.loads(row["Fix"]) if row.get("Fix") else None
    except ValueError:
        q = None                        # a hand-typed Fix cell must not break the page
    if q:
        return [tuple(b) for b in q if isinstance(b, list) and len(b) == 3]
    kind = row.get("Kind", "")
    if kind == "decision":
        return [("Yes", "answer", "Yes"), ("No", "answer", "No")]
    if kind == "click":
        return [("Done", "answer", "Done")]
    return []


def seed_questions(who: str = "Claude") -> int:
    """Turn the import's open questions into Approvals rows (once)."""
    have = {r.get("Item") for r in record.rows("Approvals")}
    n = 0
    store = _store()
    for item, btns in QUESTIONS:
        if item in have:
            continue
        aid = record.next_id("Approvals", "A-")
        record.append("Approvals", {
            "ID": aid, "Item": item, "Kind": "question",
            "His one action": "Pick an answer, or hand it to the agent.",
            "Raised": actionlog.now_central()[:10], "Status": "waiting",
            "Source": "Import, 27 Sep 2026 (flagged instead of guessed)"})
        store[aid] = btns
        n += 1
    _save_store(store)
    return n


def _store() -> dict:
    p = record.paths.DATA / "fix_buttons.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _save_store(d: dict) -> None:
    (record.paths.DATA / "fix_buttons.json").write_text(json.dumps(d, indent=2), encoding="utf-8")


def buttons(row: dict) -> list[tuple]:
    st = _store()
    if st.get(row.get("ID")):          # an empty list here falls back to the Kind's buttons
        return [tuple(b) for b in st[row["ID"]] if len(b) == 3]
    return buttons_for(row)


def decide(aid: str, value: str, who: str = "Sam") -> None:
    r = record.find("Approvals", "ID", aid)
    if not r:
        return
    record.set_cell("Approvals", r["_row"], "Decision", value)
    record.set_cell("Approvals", r["_row"], "Decided on", actionlog.now_central())
    record.set_cell("Approvals", r["_row"], "Status", "decided")
    actionlog.log(who, f"Decided {aid}: {value}", item=r.get("Item", "")[:120])


def hand(aid: str, task: str, who: str = "Sam") -> str:
    duty = record.duty().get("passes") or "Claude"
    sid = record.next_id("Requests", "S-")
    record.append("Requests", {
        "ID": sid, "When (Central)": actionlog.now_central(),
        "His words (verbatim)": task, "About": "operations", "For": duty,
        "Status": "open", "Result": "", "Updated": ""})
    r = record.find("Approvals", "ID", aid)
    if r:
        record.set_cell("Approvals", r["_row"], "Status", f"handed to {duty}")
        record.set_cell("Approvals", r["_row"], "Decision", f"Handed to {duty} ({sid})")
        record.set_cell("Approvals", r["_row"], "Decided on", actionlog.now_central())
    actionlog.log(who, f"Handed {aid} to {duty} as {sid}.")
    return sid


def app_fix(aid: str, action: str, who: str = "Sam") -> str:
    if action == "dupes":
        res = files.move_duplicates(who)
        decide(aid, f"Moved {len(res['moved'])} duplicates to _to_delete", who)
        return f"Moved {len(res['moved'])} files. Nothing was deleted."
    if action.startswith(("listing-live:", "listing-gone:")):
        lid = action.split(":", 1)[1]
        row = record.find("Listings", "Etsy listing ID", lid)
        if row:
            today = actionlog.now_central()[:10]
            if action.startswith("listing-live"):
                record.set_cell("Listings", row["_row"], "Last verified", today)
                decide(aid, "Still live (checked by Sam)", who)
            else:
                record.set_cell("Listings", row["_row"], "Status", "not live")
                record.set_cell("Listings", row["_row"], "Last verified", today)
                decide(aid, "Not live (checked by Sam)", who)
        return "Recorded."
    return "Unknown fix."


def still_true(tab: str, key_header: str, key: str, who: str = "Sam") -> None:
    """For a STALE fact: Sam confirms it; the date moves to today."""
    r = record.find(tab, key_header, key)
    if not r:
        return
    col = "As of" if "As of" in r else "Last verified" if "Last verified" in r else None
    if not col:
        return                          # this tab has no date to move
    record.set_cell(tab, r["_row"], col, actionlog.now_central()[:10])
    actionlog.log(who, f"Confirmed still true: {tab} {key}.")


def recheck_platforms(who: str = "App") -> dict:
    """Pull Bluesky posts from the public feed and add any the record lacks."""
    with urllib.request.urlopen(BSKY, timeout=30) as r:
        feed = json.load(r)["feed"]
    have = {p.get("URL", "").rsplit("/", 1)[-1] for p in record.rows("Posts")}
    added = []
    from zoneinfo import ZoneInfo
    import datetime
    for f in feed:
        rkey = f["post"]["uri"].rsplit("/", 1)[-1]
        if rkey in have:
            continue
        ts = datetime.datetime.fromisoformat(f["post"]["record"]["createdAt"].replace("Z", "+00:00"))
        c = ts.astimezone(ZoneInfo("America/Chicago"))
        if (datetime.datetime.now(ZoneInfo("America/Chicago")) - c).days > 3:
            continue
        pid = record.next_id("Posts", "P-")
        record.append("Posts", {
            "ID": pid, "Date (Central)": c.strftime("%Y-%m-%d"), "Time (Central)": c.strftime("%H:%M"),
            "Platform": "Bluesky", "Item": "(found on the platform)",
            "URL": f"https://bsky.app/profile/your-handle.bsky.social/post/{rkey}",
            "Caption as posted": f["post"]["record"].get("text", ""), "Posted by": "",
            "State": "live", "Source": "Bluesky public feed, found by the app",
            "As of": c.strftime("%Y-%m-%d")})
        added.append(pid)
    actionlog.log(who, f"Checked Bluesky's public feed: {len(added)} posts added to the record.")
    return {"added": added}
