"""Writing and publishing (the Kimi Work "Writing and Publishing" tab,
rebuilt here). State lives in the Writing tab of the Sheet.

His answers to position prompts are saved word for word; the essay built
from them is Claude's lane, and goes to his Inbox for approval.
"""
import json
import time
import urllib.request
import xml.etree.ElementTree as ET

from . import paths, record
from .ward import actionlog

SITEMAP = "https://example.com/sitemap.xml"
CACHE = paths.DATA / "site_pages.json"
RULES = [
    "Everything Sam writes is free on the site; what he makes is for sale.",
    "Every writing must be new: old pieces are raw material, never reposted.",
    "Pieces are built only from positions he has actually stated; no stated position, no piece.",
    "An AI Attribution Note ends every AI-drafted piece, naming the AI.",
    "Every figure is checked against its primary source before it goes up.",
    "Never print a correction to one of his positions: print it if supported, leave it out if not.",
    "Nothing from the private folders is ever drawn on.",
]


def site_pages(max_age: int = 6 * 3600) -> dict:
    """Pages live on his site, read from its sitemap (cached a few hours)."""
    if CACHE.exists():
        d = json.loads(CACHE.read_text(encoding="utf-8"))
        if time.time() - d.get("t", 0) < max_age:
            return d
    try:
        with urllib.request.urlopen(SITEMAP, timeout=30) as r:
            root = ET.fromstring(r.read())
        ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
        pages = []
        for u in root.findall("s:url", ns):
            loc = u.find("s:loc", ns).text
            mod = u.find("s:lastmod", ns)
            pages.append({"url": loc, "path": loc.split(".com", 1)[-1] or "/",
                          "lastmod": (mod.text[:10] if mod is not None and mod.text else "")})
        d = {"t": time.time(), "checked": actionlog.now_central(), "pages": pages,
             "source": SITEMAP}
        CACHE.write_text(json.dumps(d), encoding="utf-8")
        return d
    except Exception as e:  # noqa: BLE001
        return {"pages": [], "checked": None, "error": str(e)[:200], "source": SITEMAP}


def by_kind() -> dict:
    out = {}
    for r in record.rows("Writing"):
        if str(r.get("Status", "")).startswith("deleted"):
            continue            # deleted from the app; the row stays in the Sheet
        out.setdefault(r.get("Kind", ""), []).append(r)
    return out


def answer(wid: str, words: str, who: str = "Sam") -> None:
    """Save his answer verbatim, close the prompt, hand the build to Claude."""
    r = record.find("Writing", "ID", wid)
    if not r:
        return
    record.set_cell("Writing", r["_row"], "His words (verbatim)", words)
    record.set_cell("Writing", r["_row"], "Status", f"answered {actionlog.now_central()}")
    record.append("Requests", {
        "ID": record.next_id("Requests", "S-"), "When (Central)": actionlog.now_central(),
        "His words (verbatim)": (f"His answer to prompt {wid} ({r.get('Item', '')[:120]}) is in the "
                                 f"Writing tab, word for word. Build the scheduled piece only from his "
                                 f"words and send it to his Inbox."),
        "About": "writing", "For": "Claude", "Status": "open", "Result": "", "Updated": ""})
    actionlog.log(who, f"Answered writing prompt {wid} in his own words; handed the build to Claude.")


# Context for each position prompt, so he knows what he is answering and
# where his answer goes. Taken from 00 KIMI STATE, Publishing Schedule
# (A2, A3, A5, A7, A8), read 27 Sep 2026. Each line says which part it is from.
LEDGER = "example ledger"
PROMPT_WHY = ("Pieces are built only from positions you have stated; where there is no stated position, "
              "nothing can be built. Your answer is saved word for word and the piece is stitched from it.",
              f"{LEDGER} A2 (your 10 Sep rule)")
PROMPT_CONTEXT = {}   # per-prompt notes, keyed by prompt ID (example: none)


def prompt_context(pid: str) -> list[tuple]:
    return [(t, f"{LEDGER} {src}") for t, src in PROMPT_CONTEXT.get(pid, [])]


# What he writes about, in his own site's sections (00 SITE CHANNEL v2, Site
# facts, 24 Sep 2026), plus the books, the fiction and the shop.
TOPICS = [
    ("Craft", ["The bench", "Working with AI"]),
    ("Books", ["Spoon carving guide"]),
    ("Other", ["Personal note", "Something else"]),
]

# Library folders -> writing areas, the world as it is first.
AREAS = [
    ("Essays", "Standalone Essays"),
    ("Book: Spoon carving guide", "Spoon Carving Guide"),
    ("Listing copy", "Listing Copy"),
    ("Publishing plans", "Publishing Plans"),
]


def area_of(folder: str) -> str:
    for name, key in AREAS:
        if key in folder:
            return name
    return "Other writing"


def grouped_docs(docs: list[dict]) -> list[tuple]:
    """Current Google Docs from the library, grouped by writing area, newest first."""
    groups = {name: [] for name, _ in AREAS}
    groups["Other writing"] = []
    for d in docs:
        if d.get("gdoc") and d.get("state") != "superseded":
            groups[area_of(d.get("folder", ""))].append(d)
    return [(k, v) for k, v in groups.items() if v]


QUEUE_STATUSES = ["Idea", "Drafting", "Queued", "Scheduled", "Published"]
QUEUE_PLATFORMS = ["Blog", "Substack", "Facebook", "Book"]


def capture(text: str, doc_title: str, section: str, category: str, who: str = "Sam") -> str:
    """Capture & staging: his words, verbatim, routed to a document section."""
    cid = record.next_id("Writing", "K-")
    record.append("Writing", {
        "ID": cid, "Kind": "capture", "Item": f"{doc_title} / {section} / {category}",
        "Owner": who, "Due": "", "Status": "staged", "His words (verbatim)": text,
        "Source": "Capture box in the Control Room", "As of": actionlog.now_central()[:10]})
    actionlog.log(who, f"Captured {len(text.split())} words for {doc_title} / {section}.")
    return cid


def approve_capture(cid: str, who: str = "Sam") -> None:
    r = record.find("Writing", "ID", cid)
    if not r:
        return
    record.set_cell("Writing", r["_row"], "Status", f"approved {actionlog.now_central()}")
    item = r.get("Item", "")
    if item.startswith("New piece"):
        what = (f"Start a new piece from approved capture {cid} ({item}). His words are in the Writing tab, "
                f"verbatim: build only from them, file a new Google Doc in the matching folder of the Drive map "
                f"(essays by subject, books, fiction), add it to the publishing queue, and send the draft to his Inbox.")
    else:
        what = (f"Merge approved capture {cid} into {item}. His words are in the Writing tab, verbatim: "
                f"tidy only grammar, punctuation and false starts.")
    record.append("Requests", {
        "ID": record.next_id("Requests", "S-"), "When (Central)": actionlog.now_central(),
        "His words (verbatim)": what,
        "About": "writing", "For": "Claude", "Status": "open", "Result": "", "Updated": ""})
    actionlog.log(who, f"Approved capture {cid}; merge handed to Claude.")


def queue_add(title: str, platform: str, category: str, who: str = "Sam") -> str:
    qid = record.next_id("Writing", "Q-")
    record.append("Writing", {
        "ID": qid, "Kind": "queue", "Item": title, "Owner": platform, "Due": category,
        "Status": "Idea", "His words (verbatim)": "", "Source": f"added by {who}",
        "As of": actionlog.now_central()[:10]})
    actionlog.log(who, f"Publishing queue: added \"{title[:80]}\" ({platform}).")
    return qid


def queue_status(qid: str, status: str, who: str = "Sam") -> None:
    if status not in QUEUE_STATUSES:
        return
    r = record.find("Writing", "ID", qid)
    if r:
        record.set_cell("Writing", r["_row"], "Status", status)
        record.set_cell("Writing", r["_row"], "As of", actionlog.now_central()[:10])
        actionlog.log(who, f"Publishing queue: {r.get('Item', '')[:60]} is now {status}.")


def shipped_add(date: str, what: str, who: str = "Sam") -> None:
    record.append("Writing", {
        "ID": record.next_id("Writing", "S-"), "Kind": "shipped", "Item": what, "Owner": who,
        "Due": date, "Status": "live", "His words (verbatim)": "", "Source": f"added by {who}",
        "As of": actionlog.now_central()[:10]})
    actionlog.log(who, f"What shipped: {date} {what[:80]}")


# ------------------------------------------------------------------ open a draft or capture to edit
ITEM_DRAFTS = paths.DRAFTS / "writing"
ITEM_DRAFTS.mkdir(parents=True, exist_ok=True)
ITEM_REQS = paths.DATA / "writing_item_requests.json"
EDITORS = ("Claude", "Kimi", "ChatGPT")


def _item_file(wid: str):
    import re
    return ITEM_DRAFTS / (re.sub(r"[^A-Za-z0-9-]", "", wid)[:20] + ".txt")


def item(wid: str) -> dict | None:
    """A draft (W-) or capture (K-) row, with the text to edit: his saved
    edit if there is one, else the capture's words, else (for a draft whose
    text isn't in Drive or here) nothing, and a note saying so."""
    r = record.find("Writing", "ID", wid)
    if not r or r.get("Kind") not in ("draft", "capture"):
        return None
    f = _item_file(wid)
    saved = f.read_text(encoding="utf-8") if f.exists() else None
    text = saved if saved is not None else r.get("His words (verbatim)", "")
    note = ""
    if r["Kind"] == "draft" and not text:
        note = ("This draft's text isn't in your Drive or the Control Room yet "
                f"(record says: {r.get('Source', '')}). Paste it here and press Save.")
    return {"id": wid, "kind": r["Kind"], "name": r.get("Item", "")[:200], "text": text,
            "status": r.get("Status", ""), "note": note, "where": where(r)}


def capture_parts(item_text: str) -> dict:
    """A capture's Item is "<document> / <section> / <topic>" (or
    "New piece / <title> / <topic>"); the document name may itself hold " / "."""
    parts = item_text.split(" / ")
    if len(parts) < 3:
        return {"doc": item_text, "section": "", "topic": ""}
    return {"doc": " / ".join(parts[:-2]), "section": parts[-2], "topic": parts[-1]}


def where(r: dict) -> str:
    """Plain words for where a piece of text belongs."""
    if r.get("Kind") == "capture":
        p = capture_parts(r.get("Item", ""))
        if p["doc"] == "New piece":
            return f"Capture {r['ID']} · for a new piece, working title \"{p['section']}\" · topic: {p['topic']}"
        return f"Capture {r['ID']} · goes into \"{p['doc']}\", section \"{p['section']}\" · topic: {p['topic']}"
    if r.get("Kind") == "draft":
        due = f" · public date {r['Due']}" if r.get("Due") else ""
        return f"Draft {r['ID']}{due} · from: {r.get('Source', '')}"
    return r.get("ID", "")


def save_item(wid: str, text: str, send: bool, to: str, who: str = "Sam") -> str | None:
    """Keep his edit on the laptop; on Save, put it where it belongs:
    a capture's words are replaced in the Writing tab (they are his words),
    and the agent he picked gets one instruction per item, updated in place
    while it is still open."""
    from .ward import fences
    r = record.find("Writing", "ID", wid)
    if not r or r.get("Kind") not in ("draft", "capture") or to not in EDITORS:
        raise ValueError("not a draft or capture")
    fences.check_writable(ITEM_DRAFTS)
    _item_file(wid).write_text(text, encoding="utf-8")
    if not send:
        return None
    if r["Kind"] == "capture":
        record.set_cell("Writing", r["_row"], "His words (verbatim)", text)
        if r.get("Status", "").startswith("staged"):
            actionlog.log(who, f"Edited capture {wid} before approving it ({len(text.split())} words).")
            return None             # still staged: nothing to hand over until he approves
        words = (f"He edited approved capture {wid} ({r.get('Item', '')[:120]}). Use his new words, "
                 f"below and in the Writing tab, instead of the old ones. Tidy only grammar, "
                 f"punctuation and false starts.\n\n{text}")
    else:
        words = (f"He edited draft {wid} ({r.get('Item', '')[:160]}) in the Control Room. Make the "
                 f"draft read exactly as below: keep his edits word for word, never reword them.\n\n{text}")
    words = words[:45000]
    try:
        known = json.loads(ITEM_REQS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        known = {}
    req = record.find("Requests", "ID", known[wid]) if known.get(wid) else None
    if req and req.get("Status") == "open":
        record.set_cell("Requests", req["_row"], "His words (verbatim)", words)
        record.set_cell("Requests", req["_row"], "For", to)
        record.set_cell("Requests", req["_row"], "When (Central)", actionlog.now_central())
        return req["ID"]
    sid = record.next_id("Requests", "S-")
    record.append("Requests", {
        "ID": sid, "When (Central)": actionlog.now_central(), "His words (verbatim)": words,
        "About": "writing edit", "For": to, "Status": "open", "Result": "", "Updated": ""})
    known[wid] = sid
    ITEM_REQS.write_text(json.dumps(known), encoding="utf-8")
    actionlog.log(who, f"Saved his edit of {wid}; sent to {to} ({sid}).")
    return sid


def add_draft(item: str, text: str, source: str, owner: str = "Claude", due: str = "",
              who: str = "Claude") -> str:
    """Register a piece of already-written prose (a blog post draft and
    anything similar) as a Writing draft, with its text already in place —
    so it shows up on the Writing screen ready for him to open, edit and
    decide on, not just a note that passed through the Inbox."""
    wid = record.next_id("Writing", "W-")
    record.append("Writing", {
        "ID": wid, "Kind": "draft", "Item": item[:200], "Owner": owner, "Due": due,
        "Status": "waiting", "His words (verbatim)": "", "Source": source[:300],
        "As of": actionlog.now_central()[:10]})
    save_item(wid, text[:100000], False, owner if owner in EDITORS else "Claude", who=who)
    actionlog.log(who, f"Added {wid} to Writing, ready to edit: {item[:80]}")
    return wid


def delete(wid: str, who: str = "Sam") -> bool:
    """His Delete button on a draft or capture. His standing rule is that
    nothing is truly deleted, so the row stays in the Sheet marked deleted
    (recoverable there) and leaves every screen."""
    r = record.find("Writing", "ID", wid)
    if not r or r.get("Kind") not in ("draft", "capture"):
        return False
    record.set_cell("Writing", r["_row"], "Status",
                    f"deleted {actionlog.now_central()} (was: {r.get('Status', '')})")
    actionlog.log(who, f"Deleted {r['Kind']} {wid} from the app (kept in the Sheet, marked deleted).")
    return True


def is_deleted(r: dict) -> bool:
    return str(r.get("Status", "")).startswith("deleted")


def decide(wid: str, decision: str, who: str = "Sam") -> None:
    r = record.find("Writing", "ID", wid)
    if not r:
        return
    record.set_cell("Writing", r["_row"], "Status", f"{decision} ({actionlog.now_central()})")
    if wid.startswith("W-") and (decision.startswith("send back") or decision == "yes"):
        record.append("Requests", {
            "ID": record.next_id("Requests", "S-"), "When (Central)": actionlog.now_central(),
            "His words (verbatim)": f"Writing {wid}: {decision}. {r.get('Item', '')[:160]}",
            "About": "writing", "For": "Claude", "Status": "open", "Result": "", "Updated": ""})
    actionlog.log(who, f"Writing {wid}: {decision}")
