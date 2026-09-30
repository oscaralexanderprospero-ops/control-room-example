"""Document studio and capture destinations (from Kimi's Writing tab).

The documents are his writing documents in Drive (CURRENT versions). Before
any read, the Drive fence walks each document's parents and refuses anything
under the private folders. The app only READS these documents: his new text
is saved as a studio draft (here, and in the backup) and sent as a Request to
the agent he picks (Claude, Kimi or ChatGPT), who makes the edit in the Google Doc.
"""
import json
import re
import threading
import time

from . import google_auth, pacing, paths
from .ward import actionlog, fences

DOCS = [
    # (title, Google Doc ID, group). Put your own documents here.
    ("Example document", "YOUR-GOOGLE-DOC-ID", "Examples"),
]
CATEGORIES = ["General", "Blog post", "Notes"]
CACHE = paths.DATA / "doc_sections.json"
DRAFTS = paths.DRAFTS / "studio"
DRAFTS.mkdir(parents=True, exist_ok=True)


def doc(doc_id: str) -> tuple | None:
    d = next((d for d in DOCS if d[1] == doc_id), None)
    if d:
        return d
    from . import library   # any Google Doc in his writing library may be opened
    lib = library.find(doc_id)
    if lib and lib.get("gdoc"):
        return (lib["name"], lib["id"], lib["root"])
    return None


def sections(doc_id: str, max_age: int = 3600) -> list[dict]:
    """Headings of a document, with the words under each (read only)."""
    if not doc(doc_id):
        raise fences.Fenced("not one of the listed writing documents")
    cache = json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {}
    c = cache.get(doc_id)
    if c and time.time() - c["t"] < max_age:
        return c["sections"]
    if not google_auth.connected():
        return c["sections"] if c else []
    fences.check_drive_ancestry(google_auth.drive(), doc_id)      # the privacy fence
    from googleapiclient.discovery import build
    d = build("docs", "v1", credentials=google_auth.credentials(), cache_discovery=False) \
        .documents().get(documentId=doc_id).execute()
    out, cur = [], {"title": "General notes", "text": []}
    for el in d.get("body", {}).get("content", []):
        p = el.get("paragraph")
        if not p:
            continue
        text = "".join(r.get("textRun", {}).get("content", "") for r in p.get("elements", [])).strip()
        style = p.get("paragraphStyle", {}).get("namedStyleType", "")
        if style.startswith("HEADING") or style == "TITLE":
            if cur["text"] or cur["title"] != "General notes":
                out.append(cur)
            cur = {"title": text or "(untitled)", "text": []}
        elif text:
            cur["text"].append(text)
    out.append(cur)
    secs = [{"title": s["title"], "words": sum(len(t.split()) for t in s["text"]),
             "text": "\n\n".join(s["text"])} for s in out]
    cache[doc_id] = {"t": time.time(), "sections": secs}
    CACHE.write_text(json.dumps(cache), encoding="utf-8")
    return secs


def _key(doc_id: str, section: str) -> str:
    # Google doc IDs are letters, digits, - and _ only; anything else is
    # dropped so a doc ID can never point the file outside the drafts folder.
    return re.sub(r"[^A-Za-z0-9_-]", "", doc_id)[:12] + "__" + re.sub(r"[^A-Za-z0-9]+", "-", section)[:60]


def draft(doc_id: str, section: str) -> str:
    f = DRAFTS / f"{_key(doc_id, section)}.txt"
    return f.read_text(encoding="utf-8") if f.exists() else ""


_last_logged: dict[str, float] = {}
LOG_EVERY = 600   # autosave writes every few seconds; the log gets one line per section per 10 min


def save_draft(doc_id: str, section: str, text: str, who: str = "Sam") -> None:
    if not doc(doc_id):
        raise fences.Fenced("not one of the listed writing documents")
    fences.check_writable(DRAFTS)
    key = _key(doc_id, section)
    (DRAFTS / f"{key}.txt").write_text(text, encoding="utf-8")
    set_working(doc_id)
    if time.time() - _last_logged.get(key, 0) >= LOG_EVERY:
        _last_logged[key] = time.time()
        actionlog.log(who, f"Document studio: saved a draft for {doc(doc_id)[0]} / {section} "
                           f"({len(text.split())} words).")


# ------------------------------------------------------------------ his edits become requests
EDITORS = ("Claude", "Kimi", "ChatGPT")
EDIT_REQS = paths.DATA / "studio_edit_requests.json"
_req_lock = threading.Lock()


def edit_request(doc_id: str, section: str, text: str, to: str, who: str = "Sam") -> str | None:
    """Turn his edit of one section into an instruction on the Requests tab,
    for the agent he picked, who makes it in the Google Doc on their next check.
    While that request is still open, later edits to the same section update it
    in place, so there is one instruction per section, not one per keystroke.
    His text goes in verbatim; nothing is reworded here."""
    from . import record
    d = doc(doc_id)
    if not d or to not in EDITORS:
        raise fences.Fenced("not one of the listed writing documents")
    now_text = next((s["text"] for s in sections(doc_id) if s["title"] == section), None)
    if now_text is not None and now_text.strip() == text.strip():
        return None                                  # no change from the doc: nothing to ask
    words = (f"Edit the Google Doc \"{d[0]}\" (https://docs.google.com/document/d/{doc_id}/edit), "
             f"section \"{section}\". Make that section read exactly as his words below. Tidy only "
             f"grammar, punctuation and false starts; never reword. If you can't write to the doc, "
             f"say so in the result.\n\n{text}")[:45000]
    key = _key(doc_id, section)
    with _req_lock:
        try:
            known = json.loads(EDIT_REQS.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            known = {}
        r = record.find("Requests", "ID", known.get(key, "")) if known.get(key) else None
        if r and r.get("Status") == "open":
            record.set_cell("Requests", r["_row"], "His words (verbatim)", words)
            record.set_cell("Requests", r["_row"], "For", to)
            record.set_cell("Requests", r["_row"], "When (Central)", actionlog.now_central())
            return r["ID"]
        sid = record.next_id("Requests", "S-")
        record.append("Requests", {
            "ID": sid, "When (Central)": actionlog.now_central(), "His words (verbatim)": words,
            "About": "writing edit", "For": to, "Status": "open", "Result": "", "Updated": ""})
        known[key] = sid
        EDIT_REQS.write_text(json.dumps(known), encoding="utf-8")
    actionlog.log(who, f"Document studio: edit to {d[0]} / {section} sent to {to} ({sid}).")
    return sid


# ------------------------------------------------------------------ the document he's working on
WORKING = paths.DATA / "studio_working.json"


def working() -> str | None:
    """The document he last opened or wrote in (the pop-up editor opens on it)."""
    try:
        d = json.loads(WORKING.read_text(encoding="utf-8")).get("doc")
    except (OSError, ValueError):
        return None
    return d if d and doc(d) else None


def set_working(doc_id: str) -> None:
    if doc(doc_id) and working() != doc_id:
        WORKING.write_text(json.dumps({"doc": doc_id, "t": time.time()}), encoding="utf-8")


def live(doc_id: str) -> dict:
    """The whole document, ready to edit: every section with what's in the
    Google Doc now and his saved draft. Re-read from Google at most once a minute."""
    d = doc(doc_id)
    if not d:
        raise fences.Fenced("not one of the listed writing documents")
    secs = sections(doc_id, max_age=60)
    return {"doc": doc_id, "name": d[0],
            "link": f"https://docs.google.com/document/d/{doc_id}/edit",
            "sections": [{"title": s["title"], "text": s["text"], "words": s["words"],
                          "draft": draft(doc_id, s["title"])} for s in secs],
            "read_at": pacing.now().strftime("%I:%M %p").lstrip("0")}
