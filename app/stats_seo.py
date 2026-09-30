"""Stats and SEO.

Stats: one row per reading in the Stats tab, so the history stays and the
page can show the change since the last reading. Bluesky and Pixelfed publish
their counts openly, so the app reads them itself; other platforms get a
reading from Sam or from an agent's pass. A number with no source is never
shown.

SEO: the keyword and tag bank (by product line and platform) and the SEO
to-do list, in the SEO tab. Title and tag problems on specific listings live
in Listing Updates; seasonal SEO changes live in Marketing.
"""
import json
import urllib.request

from . import record
from .ward import actionlog

PLATFORMS = ["Etsy", "Facebook", "Instagram", "TikTok", "YouTube", "Bluesky", "Pixelfed", "Threads",
             "Tumblr", "Substack", "WordPress", "Ko-fi", "Discord", "Website"]
METRICS = ["Followers", "Views", "Sales", "Active listings", "Favorites", "Subscribers", "Visits"]
LINES = ["All pieces", "Canes", "Staves", "Wands", "Pendants", "Books", "Other"]
AUTO = {
    "Bluesky": "https://public.api.bsky.app/xrpc/app.bsky.actor.getProfile?actor=did:plc:dknkphwpxtygu3igd2ijeua5",
    "Pixelfed": "https://pixelfed.social/api/v1/accounts/lookup?acct=ExampleMaker",
}


def add_reading(platform: str, metric: str, value: str, source: str, who: str = "Sam", date: str = "") -> None:
    record.append("Stats", {"Date": date or actionlog.now_central()[:10], "Platform": platform,
                            "Metric": metric, "Value": value.strip(), "Source": source or f"entered by {who}"})
    actionlog.log(who, f"Stats: {platform} {metric} = {value}")


def refresh_auto(who: str = "App") -> dict:
    """Read the public counts for Bluesky and Pixelfed; add a reading only if
    the number changed (or none exists yet today)."""
    got = {}
    today = actionlog.now_central()[:10]
    latest = latest_readings()
    for plat, url in AUTO.items():
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "Control-Room"}),
                                        timeout=20) as r:
                d = json.load(r)
            n = d.get("followersCount", d.get("followers_count"))
            if n is None:
                continue
            prev = latest.get((plat, "Followers"))
            # a new row only when the number moved, so the history stays readable
            if not prev or prev.get("Value") != str(n):
                add_reading(plat, "Followers", str(n), f"{plat} public profile, read by the app", who, today)
            got[plat] = n
        except Exception as e:  # noqa: BLE001 - leave that platform for next time
            got[plat] = f"error: {str(e)[:80]}"
    return got


def latest_readings() -> dict:
    """(platform, metric) -> the most recent reading (later rows win ties)."""
    out = {}
    for r in record.rows("Stats"):
        k = (r.get("Platform"), r.get("Metric"))
        if k not in out or r.get("Date", "") >= out[k].get("Date", ""):
            out[k] = r
    return out


def table() -> list[dict]:
    """Per platform and metric: latest value, date, source, and the previous
    reading for the change."""
    hist = {}
    for r in record.rows("Stats"):
        hist.setdefault((r.get("Platform"), r.get("Metric")), []).append(r)
    rows = []
    for (plat, metric), rs in hist.items():
        rs.sort(key=lambda x: x.get("Date", ""))
        last = rs[-1]
        prev = rs[-2] if len(rs) > 1 else None
        change = ""
        try:
            if prev:
                a = float(prev["Value"].replace(",", ""))
                b = float(last["Value"].replace(",", ""))
                change = f"{'+' if b >= a else ''}{b - a:,.0f} since {prev['Date']}"
        except (ValueError, AttributeError):
            pass
        rows.append({"platform": plat, "metric": metric, "value": last.get("Value"), "date": last.get("Date"),
                     "source": last.get("Source"), "change": change, "auto": plat in AUTO and metric == "Followers",
                     "history": [(x.get("Date"), x.get("Value")) for x in rs[-6:]]})
    order = {p: i for i, p in enumerate(PLATFORMS)}
    rows.sort(key=lambda r: (order.get(r["platform"], 99), r["metric"]))
    return rows


def seo() -> dict:
    rows = [r for r in record.rows("SEO") if r.get("Status") != "archived"]
    tags = [r for r in rows if r.get("Kind") == "Tag"]
    tasks = [r for r in rows if r.get("Kind") == "Task"]
    by_line = {ln: [t for t in tags if t.get("Product line") == ln] for ln in LINES}
    return {"by_line": by_line, "tasks": tasks}


def add_seo(kind: str, text: str, line: str, platforms: str, why: str, who: str = "Sam") -> str:
    sid = record.next_id("SEO", "K-" if kind == "Tag" else "T-")
    record.append("SEO", {"ID": sid, "Kind": kind, "Product line": line, "Text": text, "Platforms": platforms,
                          "Status": "active" if kind == "Tag" else "to do", "Why": why,
                          "Source": f"added by {who}", "As of": actionlog.now_central()[:10]})
    actionlog.log(who, f"SEO: added {kind.lower()} \"{text[:80]}\"")
    return sid


def set_status(sid: str, status: str, who: str = "Sam") -> None:
    if status not in ("active", "to do", "done", "archived"):
        raise ValueError(status)
    r = record.find("SEO", "ID", sid)
    if r:
        record.set_cell("SEO", r["_row"], "Status", status)
        record.set_cell("SEO", r["_row"], "As of", actionlog.now_central()[:10])
        actionlog.log(who, f"SEO: {r.get('Text', '')[:60]} is now {status}.")


def hand(sid: str, who: str = "Sam") -> None:
    r = record.find("SEO", "ID", sid)
    if not r:
        return
    duty = record.duty().get("passes") or "Claude"
    record.append("Requests", {
        "ID": record.next_id("Requests", "S-"), "When (Central)": actionlog.now_central(),
        "His words (verbatim)": f"SEO task {sid}: {r.get('Text', '')} ({r.get('Platforms', '')}). Anything that "
                                f"changes a live listing or profile stops for his click.",
        "About": "marketing", "For": duty, "Status": "open", "Result": "", "Updated": ""})
    actionlog.log(who, f"SEO: handed \"{r.get('Text', '')[:60]}\" to {duty}.")
