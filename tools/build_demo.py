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
        "Tasks": seed.TASKS, "Public": seed.PUBLIC_ROWS, "Log": seed.LOG}
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
