"""Orders and messages, custom orders and repairs, and customer reviews.

Etsy has no API route for this app yet, so the agent's Etsy check (a
scheduled pass) reads orders, messages and reviews in the browser and reports
them here through the agent API; Sam can also add or update anything by
hand. Replies to reviews and messages are his words; an agent may draft from
his words only, and nothing is sent without his click.
"""
import datetime
from zoneinfo import ZoneInfo

from . import record
from .ward import actionlog

CENTRAL = ZoneInfo("America/Chicago")

TABS = {
    "Orders": {
        "prefix": "O-",
        "kinds": ["Order", "Message"],
        "statuses": ["New", "Making", "Packed", "Shipped", "Delivered", "Answered", "Problem", "Closed"],
        "fields": ["Kind", "Received (Central)", "Customer", "Item", "Listing ID", "Price",
                   "Ship or answer by", "Tracking", "Notes"],
    },
    "Custom Orders": {
        "prefix": "C-",
        "kinds": ["Custom piece", "Repair", "Video commission"],
        "statuses": ["Asked", "Quoted", "Deposit paid", "Making", "Ready", "Shipped", "Done", "Declined"],
        "fields": ["Kind", "Customer", "What", "Materials", "Price", "Deposit", "Due", "Channel",
                   "His notes (verbatim)"],
    },
    "Customer Reviews": {
        "prefix": "V-",
        "kinds": [],
        "statuses": ["Needs reply", "Reply drafted", "Replied", "No reply needed"],
        "fields": ["Date", "Stars", "Listing", "Reviewer", "Review (verbatim)", "Reply"],
    },
}
STATUS_COL = {"Orders": "Status", "Custom Orders": "Status", "Customer Reviews": "Reply status"}
OPEN = {"Orders": ("New", "Making", "Packed", "Problem"), "Custom Orders": ("Asked", "Quoted", "Deposit paid", "Making", "Ready"),
        "Customer Reviews": ("Needs reply", "Reply drafted")}
# His 17 Sep 2026 monthly limits for custom orders (kept on record for Etsy;
# not active anywhere yet) and the one Ko-fi commission cap.
SLOT_LIMITS = [("Staves", 3), ("Jewelry", 7), ("Wands", 9), ("Canes", 3), ("Video commission (Ko-fi)", 5)]
# Words that put a custom order in a slot. "Staves" alone would miss "staff",
# and "Jewelry" would miss a pendant.
SLOT_WORDS = {"Staves": ("stave", "staff"), "Jewelry": ("jewel", "pendant", "necklace", "amulet"),
              "Wands": ("wand",), "Canes": ("cane", "walking stick"),
              "Video commission (Ko-fi)": ("video",)}
SLOT_SOURCE ="His 17 Sep 2026 limits (00 KIMI STATE, Ko-fi section): kept on record, not yet active on Etsy"


def _due(s: str):
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.datetime.strptime(s.strip(), fmt).replace(tzinfo=CENTRAL)
        except (ValueError, AttributeError):
            continue
    return None


def view() -> dict:
    now = datetime.datetime.now(CENTRAL)
    out = {}
    for tab, cfg in TABS.items():
        rows = list(reversed(record.rows(tab)))
        for r in rows:
            d = _due(r.get("Ship or answer by") or r.get("Due") or "")
            r["_open"] = r.get(STATUS_COL[tab], "") in OPEN[tab]
            if d and r["_open"]:
                hrs = (d - now).total_seconds() / 3600
                r["_left"] = ("overdue" if hrs < 0 else f"{int(hrs)} h left" if hrs < 48 else f"{int(hrs // 24)} days left")
                r["_urgent"] = hrs < 24
        out[tab] = rows
    month = now.strftime("%Y-%m")
    slots = []
    for name, lim in SLOT_LIMITS:
        words = SLOT_WORDS.get(name, (name.split(" ")[0].lower().rstrip("s"),))
        used = sum(1 for r in out["Custom Orders"]
                   if (r.get("As of", "")[:7] == month)
                   and any(w in (r.get("What", "") + " " + r.get("Kind", "")).lower() for w in words)
                   and r.get("Status") not in ("Declined",))
        slots.append({"name": name, "limit": lim, "used": used})
    return {"tabs": out, "cfg": TABS, "status_col": STATUS_COL, "slots": slots, "slot_source": SLOT_SOURCE}


def counts() -> dict:
    v = view()["tabs"]
    return {
        "to_ship": sum(1 for r in v["Orders"] if r.get("Kind") == "Order" and r["_open"]),
        "messages": sum(1 for r in v["Orders"] if r.get("Kind") == "Message" and r["_open"]),
        "urgent": sum(1 for r in v["Orders"] if r.get("_urgent")),
        "customs": sum(1 for r in v["Custom Orders"] if r["_open"]),
        "reviews": sum(1 for r in v["Customer Reviews"] if r["_open"]),
    }


def add(tab: str, values: dict, who: str = "Sam", source: str = "") -> str:
    cfg = TABS[tab]
    if values.get("status") and values["status"] not in cfg["statuses"]:
        raise ValueError(values["status"])
    rid = record.next_id(tab, cfg["prefix"])
    row = {"ID": rid, "Source": source or f"added by {who}", "As of": actionlog.now_central()[:10]}
    for f in cfg["fields"]:
        row[f] = (values.get(f) or "").strip()
    row[STATUS_COL[tab]] = values.get("status") or cfg["statuses"][0]
    record.append(tab, row)
    actionlog.log(who, f"{tab}: added {rid} ({row.get('Kind') or ''} {row.get('Item') or row.get('What') or row.get('Listing') or ''})".strip())
    return rid


def update(tab: str, rid: str, field: str, value: str, who: str = "Sam") -> bool:
    """Change one field. False if there is no such row."""
    cfg = TABS[tab]
    if field not in cfg["fields"] + [STATUS_COL[tab]]:
        raise ValueError(field)
    if field == STATUS_COL[tab] and value not in cfg["statuses"]:
        raise ValueError(value)
    r = record.find(tab, "ID", rid)
    if not r:
        return False
    record.set_cell(tab, r["_row"], field, value)
    record.set_cell(tab, r["_row"], "As of", actionlog.now_central()[:10])
    actionlog.log(who, f"{tab} {rid}: {field} set.")
    return True


def hand(tab: str, rid: str, what: str, who: str = "Sam") -> None:
    r = record.find(tab, "ID", rid)
    duty = record.duty().get("passes") or "Claude"
    record.append("Requests", {
        "ID": record.next_id("Requests", "S-"), "When (Central)": actionlog.now_central(),
        "His words (verbatim)": f"{tab} {rid}: {what}. Details are in the {tab} tab. Replies only from his words; "
                                f"nothing is sent to a customer without his click.",
        "About": "operations", "For": duty, "Status": "open", "Result": "", "Updated": ""})
    actionlog.log(who, f"Handed {tab} {rid} to {duty}: {what[:80]}")
