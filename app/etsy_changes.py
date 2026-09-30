"""Approved Etsy changes, for the Etsy changes routine (his request, 28 Sep 2026).

Two sources, both already approved by him:
  - Inbox items with an "Etsy" (text to add to the description) or "Etsy title"
    (the new title) platform, once approved;
  - Listing Updates rows he marked "ready for Etsy" (his measurements and notes).

The routine fills each change into the listing's edit screen in his Chrome.
Live listings stop there for his Save click (his rule); drafts stay drafts and
may be saved. Each change moves: approved -> on edit screen (waiting for his
Save) -> saved (checked on the live listing) or failed.
"""
import re

from . import approvals, record
from .ward import actionlog

ETSY_PLATS = ("Etsy", "Etsy title")
LISTING = re.compile(r"\b(\d{9,11})\b")
STATES = {"staged": "on edit screen, waiting for his Save", "saved": "saved", "failed": "approved"}


def _ids(item: str) -> list[str]:
    """Listing IDs named in an item; the first is the one the change is for.
    'Approving adds it to both' items name the live copy too."""
    return list(dict.fromkeys(LISTING.findall(item or "")))


def pending() -> list[dict]:
    out = []
    listings = {r.get("Etsy listing ID"): r for r in record.rows("Listings")}
    for a in record.rows("Approvals"):
        if a.get("Status") not in ("approved", "posted"):
            continue
        d = approvals.load(a["ID"])
        if not d:
            continue
        for plat in ETSY_PLATS:
            p = d["platforms"].get(plat)
            if not p or p.get("status") not in ("approved", "on edit screen, waiting for his Save"):
                continue
            ids = _ids(d.get("item", ""))
            out.append({"source": "approval", "id": d["id"], "platform": plat, "listing_ids": ids,
                        "state": p["status"],
                        "change": ("Replace the title with exactly this" if plat == "Etsy title"
                                   else "Add these lines to the end of the description, exactly as written"),
                        "text": p.get("text", ""),
                        # only a listing the record shows as a draft may be saved by the routine
                        "drafts": [i for i in ids if (listings.get(i) or {}).get("Status") == "draft"],
                        "item": d.get("item", "")})
    covered = {i for c in out for i in c["listing_ids"][:1]}     # an approved Inbox change already carries it
    for r in record.rows("Listing Updates"):
        if r.get("Listing ID") in covered:
            continue
        if r.get("Status") in ("ready for Etsy", "on edit screen, waiting for his Save"):
            from .listing_updates import FIELDS
            vals = {f: r.get(f) for f in FIELDS if r.get(f)}
            out.append({"source": "listing update", "id": r["Listing ID"], "platform": "Etsy",
                        "listing_ids": [r["Listing ID"]], "state": r.get("Status"),
                        "change": ("Add his measurements and details to the description as he gave them, "
                                   "and fix wording only from his notes (cut, never reword)"),
                        "text": "\n".join(f"{k}: {v}" for k, v in vals.items()),
                        "his_notes": r.get("His notes (verbatim)", ""),
                        "needs": r.get("Needs", ""),
                        "drafts": [r["Listing ID"]] if r.get("Active or Draft") == "Draft" else [],
                        "item": r.get("Piece", "")})
    return out


def mark(source: str, cid: str, platform: str, state: str, note: str, who: str) -> bool:
    if state not in STATES:
        return False
    label = STATES[state]
    if source == "approval":
        d = approvals.load(cid)
        if not d or platform not in d["platforms"]:
            return False
        d["platforms"][platform]["status"] = label
        if note:
            d["platforms"][platform]["etsy_note"] = note[:400]
        d.setdefault("history", []).append({"when": actionlog.now_central(), "who": who,
                                            "what": f"Etsy {platform}: {label}. {note[:200]}"})
        approvals.save(d)
    elif source == "listing update":
        r = record.find("Listing Updates", "Listing ID", cid)
        if not r:
            return False
        record.set_cell("Listing Updates", r["_row"], "Status",
                        "done" if state == "saved" else "ready for Etsy" if state == "failed" else label)
        record.set_cell("Listing Updates", r["_row"], "As of", actionlog.now_central()[:10])
    else:
        return False
    actionlog.log(who, f"Etsy change {source} {cid} ({platform}): {label}. {note[:200]}")
    return True
