"""The approval inbox (Stage 2).

Each item's detail lives in drafts\\approvals\\<ID>.json: his source words,
the drafted text per platform, the files, and every decision made. The
Approvals tab holds the one-line summary and status.

Sam' buttons: Approve, Cut (remove whole sentences; there is no rewriting
box), Ask ChatGPT to review (queues it for ChatGPT's next read, with a plain
note), Send back. Each decision is logged. Nothing here edits his words.
"""
import json
import re

from . import checks, paths, record
from .ward import actionlog

DIR = paths.DRAFTS / "approvals"
DIR.mkdir(parents=True, exist_ok=True)
SENT = re.compile(r"(?<=[.!?—])\s+(?=[A-Z“\"])")


def path(aid: str):
    return DIR / f"{aid}.json"


def load(aid: str) -> dict | None:
    p = path(aid)
    if not p.exists():
        return None
    d = json.loads(p.read_text(encoding="utf-8"))
    d.setdefault("platforms", {})
    d.setdefault("history", [])
    return d


def save(d: dict) -> None:
    path(d["id"]).write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")


def pieces(text: str) -> list[str]:
    """His text as cuttable pieces: each line, and each sentence in a line."""
    out = []
    for line in (text or "").split("\n"):
        if not line.strip():
            out.append("")
            continue
        out.extend(s for s in SENT.split(line) if s)
    return out


def view(aid: str) -> dict | None:
    d = load(aid)
    if not d:
        return None
    src = d.get("source_dictation", "")
    for plat, p in d["platforms"].items():
        p["pieces"] = pieces(p.get("text", ""))
        p["html"] = checks.highlight(p.get("text", ""), src)
        p["checks"] = checks.run(plat, p.get("text", ""), src,
                                 ai_written=d.get("ai_written", False),
                                 is_sale_clip=d.get("is_sale_clip", False))
        p["all_ok"] = all(c["ok"] for c in p["checks"])
    return d


def _row(aid: str) -> dict | None:
    return record.find("Approvals", "ID", aid)


def _set_status(aid: str, status: str, decision: str) -> None:
    r = _row(aid)
    if r:
        record.set_cell("Approvals", r["_row"], "Status", status)
        record.set_cell("Approvals", r["_row"], "Decision", decision)
        record.set_cell("Approvals", r["_row"], "Decided on", actionlog.now_central())


def _history(d: dict, who: str, what: str) -> None:
    d["history"].append({"when": actionlog.now_central(), "who": who, "what": what})


def approve(aid: str, platform: str | None, who: str = "Sam") -> None:
    d = load(aid)
    if not d or (platform and platform not in d["platforms"]):
        return
    plats = [platform] if platform else list(d["platforms"])
    for p in plats:
        d["platforms"][p]["status"] = "approved"
    _history(d, who, "Approved " + (platform or "all platforms"))
    save(d)
    left = [p for p, v in d["platforms"].items() if v.get("status") != "approved"]
    if not left:
        _set_status(aid, "approved", "Approved, all platforms")
        q = record.find("Queue", "ID", d.get("queue_id", ""))
        if q:
            record.set_cell("Queue", q["_row"], "Status", "approved")
        # Full approval is his click; it should be enough on its own to become a
        # posting job (AGENT-API.md already promises this). Before this, the only
        # path to posting.plan() was an unwired "post" bulk op the Inbox page never
        # showed a button for, so approved items silently went nowhere.
        from . import posting
        posting.plan(aid, who)
    actionlog.log(who, f"Approved {aid} ({platform or 'all platforms'}).")


def cut(aid: str, platform: str, index: int, who: str = "Sam") -> None:
    """Remove one whole piece (sentence or line). Nothing else changes."""
    d = load(aid)
    if not d or platform not in d["platforms"]:
        return
    p = d["platforms"][platform]
    parts = pieces(p.get("text", ""))
    if not 0 <= index < len(parts) or not parts[index]:
        return      # a stale page or a blank line: nothing to cut
    removed = parts[index]
    rebuilt, i = [], 0
    for line in p["text"].split("\n"):
        if not line.strip():
            rebuilt.append(line)
            i += 1
            continue
        sents = [s for s in SENT.split(line) if s]
        keep = [s for j, s in enumerate(sents) if i + j != index]
        i += len(sents)
        if keep:
            rebuilt.append(" ".join(keep))
        elif sents:
            continue
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(rebuilt)).strip()
    p.setdefault("cuts", []).append(removed)
    p["text"] = text
    p["status"] = "pending"
    _history(d, who, f"Cut from {platform}: {removed}")
    save(d)
    actionlog.log(who, f"Cut a sentence from {aid} {platform}.", removed=removed[:120])


def ask_chatgpt(aid: str, note: str, who: str = "Sam") -> str:
    d = load(aid)
    if not d:
        return ""
    rid = record.next_id("Reviews", "R-")
    what = note.strip() or "Check the drafts against his words and the rules; flag anything, change nothing."
    record.append("Reviews", {
        "ID": rid, "Date": actionlog.now_central()[:10], "By": "Sam (request)",
        "About": f"{aid}: {d.get('item', '')}",
        "Note (verbatim)": "REQUEST FOR CHATGPT: " + what +
                           " Drafts are in the Approvals tab row " + aid +
                           ". Flag problems only; never rewrite his words.",
        "Chat link": "", "Status": "WAITING FOR CHATGPT", "Sam decided": "", "Decided on": ""})
    _set_status(aid, "with ChatGPT", "Asked ChatGPT to review: " + what)
    _history(d, who, f"Asked ChatGPT ({rid}): {what}")
    save(d)
    actionlog.log(who, f"Asked ChatGPT to review {aid} ({rid}).", note=what)
    return rid


def chatgpt_packet(aid: str) -> str:
    """Plain text Sam can paste into ChatGPT if ChatGPT can't read the Sheet."""
    d = load(aid)
    lines = [f"ChatGPT, please review approval item {aid}: {d.get('item', '')}.",
             "Flag problems only. Never rewrite his words. Reply with your notes.",
             "", "HIS SOURCE WORDS:", d.get("source_dictation", ""), ""]
    for plat, p in d["platforms"].items():
        lines += [f"DRAFT FOR {plat.upper()}:", p.get("text", "") or "(blank)", ""]
    return "\n".join(lines)


def send_back(aid: str, reason: str, who: str = "Sam") -> None:
    d = load(aid)
    if not d:
        return
    duty = record.duty().get("passes") or "Claude"
    _set_status(aid, "sent back", "Sent back: " + (reason.strip() or "no reason given"))
    _history(d, who, "Sent back: " + reason)
    save(d)
    q = record.find("Queue", "ID", d.get("queue_id", ""))
    if q:
        record.set_cell("Queue", q["_row"], "Status", "sent back")
    record.append("Requests", {
        "ID": record.next_id("Requests", "S-"), "When (Central)": actionlog.now_central(),
        "His words (verbatim)": f"Sent back {aid}: {reason}", "About": "upload",
        "For": duty, "Status": "open", "Result": "", "Updated": ""})
    actionlog.log(who, f"Sent back {aid} to {duty}.", reason=reason)


def create(item: str, queue_id: str, source: str, platforms: dict, by: str,
           files: list | None = None, ai_written: bool = False,
           is_sale_clip: bool = False, kind: str = "draft") -> str:
    aid = record.next_id("Approvals", "A-")
    record.append("Approvals", {
        "ID": aid, "Item": item, "Kind": kind,
        "His one action": "Approve, cut, ask ChatGPT, or send back.",
        "Raised": actionlog.now_central()[:10], "Status": "waiting",
        "Source": f"{by}; queue {queue_id}" if queue_id else by})
    save({"id": aid, "item": item, "queue_id": queue_id, "by": by,
          "source_dictation": source, "ai_written": ai_written,
          "is_sale_clip": is_sale_clip, "files": files or [],
          "platforms": {k: {"text": v, "status": "pending"} for k, v in platforms.items()},
          "history": [{"when": actionlog.now_central(), "who": by, "what": "Drafted"}]})
    actionlog.log(by if by in actionlog.WHO else "App", f"Draft for approval {aid}: {item}")
    return aid
