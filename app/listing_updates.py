"""Listings that need updating, with a place for Sam to add what's missing.

His values go into the Listing Updates tab. When he marks a listing ready,
the agent on duty applies it on Etsy; changes to a live listing stop at the
edit screen for his Save click, and drafts stay drafts (he clicks Publish).
"""
import re

from . import record
from .ward import actionlog

# His ruling, 27 Sep 2026: "the only dimensions that matter are height, weight on
# canes and staves, and thickness ... The height is most important." Weight comes
# once he finds his scale. The columns renamed in the Sheet the same day:
# Length -> Height, Handle or thickest width -> Thickness.
FIELDS = ["Height", "Thickness", "Weight", "Grip wrap", "Finish", "Species"]
WEIGHT_FOR = re.compile(r"\b(cane|canes|staff|staffs|staves|walking[- ]stick|stick)\b", re.I)
# No longer asked for; kept in the Sheet (never deleted) and shown where filled.
RETIRED = ["Ferrule OD", "Grip length", "Cord or chain length", "Shipping tube length"]


def fields_for(piece: str) -> list[str]:
    return [f for f in FIELDS if f != "Weight" or WEIGHT_FOR.search(piece or "")]


# His ruling, 27 Sep 2026: "only ask for info confirmed missing on listings."
# Confirmed missing = the Missing Specifications Tracker covered the listing and
# the cell is blank ("Blank cell = not yet measured", its own legend), or the
# cell says so outright. A value marked approx / VERIFY / CONFIRM / "in
# description" has an answer already and is not asked for.
ASKED = ["Height", "Thickness", "Weight", "Finish"]
SAYS_MISSING = re.compile(r"\b(UNKNOWN|MEASURE|MISSING|NOT STATED|NO \w+ STATED)\b", re.I)
TRACKED = ("Missing Specifications Tracker", "Shop Listings Ledger")


def missing_fields(r: dict) -> list[str]:
    if "Measurements" not in (r.get("Needs") or "") or not any(t in (r.get("Source") or "") for t in TRACKED):
        return []
    out = []
    for f in ASKED:
        if f == "Weight" and not WEIGHT_FOR.search(r.get("Piece") or ""):
            continue
        v = (r.get(f) or "").strip()
        if not v or SAYS_MISSING.search(v):
            out.append(f)
    return out


def needs(r: dict) -> list[str]:
    """What this listing still needs, with Measurements only if a measurement is confirmed missing."""
    n = [x for x in (r.get("Needs") or "").split("; ") if x]
    if "Measurements" in n and not missing_fields(r):
        n.remove("Measurements")
    return n


def all_rows() -> list[dict]:
    return record.rows("Listing Updates")


def counts(rows: list[dict]) -> dict:
    c = {}
    for r in rows:
        if r.get("Status") == "done":
            continue
        for n in needs(r):
            c[n] = c.get(n, 0) + 1
    return dict(sorted(c.items(), key=lambda kv: -kv[1]))


def save(lid: str, values: dict, notes: str, ready: bool, who: str = "Sam") -> None:
    r = record.find("Listing Updates", "Listing ID", lid)
    if not r:
        return
    changed = []
    # only the fields that were on his form; a field he wasn't asked for is left as it is
    for f in [f for f in fields_for(r.get("Piece", "")) if f in values]:
        v = (values.get(f) or "").strip()
        if v != (r.get(f) or ""):
            record.set_cell("Listing Updates", r["_row"], f, v)
            changed.append(f)
    if notes.strip() and notes.strip() != r.get("His notes (verbatim)", ""):
        record.set_cell("Listing Updates", r["_row"], "His notes (verbatim)", notes.strip())
        changed.append("notes")
    status = "ready for Etsy" if ready else ("his info added" if changed else r.get("Status") or "open")
    record.set_cell("Listing Updates", r["_row"], "Status", status)
    record.set_cell("Listing Updates", r["_row"], "As of", actionlog.now_central()[:10])
    if ready:
        duty = record.duty().get("passes") or "Claude"
        record.append("Requests", {
            "ID": record.next_id("Requests", "S-"), "When (Central)": actionlog.now_central(),
            "His words (verbatim)": (f"Listing {lid} ({r.get('Piece', '')[:80]}) is ready: apply what's in the "
                                     f"Listing Updates tab ({r.get('Needs', '')}). Measurements and his notes as he "
                                     f"gave them. The only dimensions that matter: height (most important), "
                                     f"thickness, and weight on canes and staves. "
                                     f"Wording fixes only from his words. Live listings: stop at the edit "
                                     f"screen for his Save. Drafts stay drafts."),
            "About": "listing", "For": duty, "Status": "open", "Result": "", "Updated": ""})
    actionlog.log(who, f"Listing {lid}: {', '.join(changed) or 'no field changes'}; status {status}.")


def mark_done(lid: str, who: str = "Sam") -> None:
    r = record.find("Listing Updates", "Listing ID", lid)
    if r:
        record.set_cell("Listing Updates", r["_row"], "Status", "done")
        record.set_cell("Listing Updates", r["_row"], "As of", actionlog.now_central()[:10])
        actionlog.log(who, f"Listing {lid} marked done.")
