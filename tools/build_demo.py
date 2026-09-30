"""Write the demo record (data/record_cache.json) from app/seed.py.
No Google, no internet. Run once before starting the app."""
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import schema, seed  # noqa: E402

data = {"Queue": seed.QUEUE, "Posts": seed.POSTS, "Listings": seed.LISTINGS,
        "Approvals": seed.APPROVALS, "Reviews": seed.REVIEWS,
        "Tasks": seed.TASKS, "Public": seed.PUBLIC_ROWS, "Log": seed.LOG,
        "Writing": seed.WRITING, "Team": seed.TEAM, "Requests": seed.REQUESTS}
tabs = {}
for tab, headers in schema.TABS.items():
    if tab == "Duty":
        tabs[tab] = ([headers] + [list(map(str, r)) for r in seed.DUTY_CELLS]
                     + [[]] + [schema.DUTY_HISTORY_HEADERS]
                     + [list(map(str, r)) for r in seed.DUTY_HISTORY])
    elif tab == "Pacing":
        tabs[tab] = [headers] + [[str(r[0]), "", "", "", str(r[1]), "", r[2], r[3]]
                                 for r in seed.PACING_CEILINGS]
    else:
        tabs[tab] = [headers] + [[str(v) for v in r] for r in data.get(tab, [])]
out = ROOT / "data"
out.mkdir(exist_ok=True)
(out / "record_cache.json").write_text(json.dumps(
    {"tabs": tabs, "pulled_at": None, "source": "demo data"},
    ensure_ascii=False), encoding="utf-8")
print("wrote", out / "record_cache.json")

# Inbox drafts and writing drafts (files the app reads from drafts/)
ap = ROOT / "drafts" / "approvals"
ap.mkdir(parents=True, exist_ok=True)
for aid, d in seed.INBOX_DRAFTS.items():
    d = dict(d, id=aid)
    d["platforms"] = {k: {"text": v, "status": "pending"} for k, v in d["platforms"].items()}
    d["history"] = [{"when": "2026-01-15 08:00", "who": d["by"], "what": "Drafted"}]
    (ap / f"{aid}.json").write_text(json.dumps(d, ensure_ascii=False, indent=2), encoding="utf-8")
wr = ROOT / "drafts" / "writing"
wr.mkdir(parents=True, exist_ok=True)
(wr / "W-01.txt").write_text(
    "What I learned oiling my first walnut piece\n\n"
    "Walnut drinks the first coat. I waited a full day before the second one.\n\n"
    "(Example draft. Everything on this page is made up.)\n", encoding="utf-8")
(wr / "W-02.txt").write_text(
    "Why I still make spoons by hand\n\n"
    "A good straight knife, before anything else.\n\n"
    "(Example draft. Everything on this page is made up.)\n", encoding="utf-8")
print("wrote drafts")
