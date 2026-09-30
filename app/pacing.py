"""Pacing, from KIMI PROCEDURE 01: the one-hour floor (88 minutes preferred)
between any two posts to the same platform, and the daily ceilings.

Counts come from the Posts tab only. A ceiling with no source stays blank.
"""
import datetime
from zoneinfo import ZoneInfo

from . import record, seed

CENTRAL = ZoneInfo("America/Chicago")
FLOOR = datetime.timedelta(minutes=60)
PREFERRED = datetime.timedelta(minutes=88)
NO_FLOOR = {"Instagram Story"}


def now() -> datetime.datetime:
    return datetime.datetime.now(CENTRAL)


def _when(p: dict) -> datetime.datetime | None:
    d, t = (p.get("Date (Central)") or "").strip(), (p.get("Time (Central)") or "").strip()
    if not d or not t:
        return None
    # the Sheet may show a time as 14:05, 14:05:00 or 2:05 PM
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %I:%M %p"):
        try:
            return datetime.datetime.strptime(f"{d} {t}", fmt).replace(tzinfo=CENTRAL)
        except ValueError:
            continue
    return None


def ceilings() -> list[dict]:
    """Ceilings from the Pacing tab (falls back to the imported table)."""
    rows = record.rows("Pacing")
    if rows:
        return [{"platform": r["Platform"], "ceiling": r.get("Daily ceiling", ""),
                 "source": r.get("Ceiling source", ""), "note": r.get("Notes", "")}
                for r in rows]
    return [{"platform": p, "ceiling": str(c), "source": s, "note": n}
            for p, c, s, n in seed.PACING_CEILINGS]


def today() -> list[dict]:
    n = now()
    day = n.strftime("%Y-%m-%d")
    posts = [p for p in record.rows("Posts") if p.get("Date (Central)") == day]
    out = []
    for c in ceilings():
        plat = c["platform"]
        mine = [p for p in posts if p.get("Platform") == plat]
        timed = sorted((w for w in (_when(p) for p in mine) if w), reverse=True)
        # a scheduled post that has not reached its time yet is not "last"
        done = [w for w in timed if w <= n]
        upcoming = sorted(w for w in timed if w > n)
        last = done[0] if done else None
        untimed = [p for p in mine if not _when(p)]
        if plat in NO_FLOOR:
            next_ok, next_pref = None, None
        else:
            # the floor applies around scheduled posts too, not only the last
            # one that went out: earliest() steps past both
            next_ok = earliest(plat)
            next_pref = last + PREFERRED if last else None
            if next_pref and next_pref <= next_ok:
                next_pref = None
        try:
            ceil = int(c["ceiling"]) if str(c["ceiling"]).strip() else None
        except ValueError:
            ceil = None
        count = len(mine)
        out.append({
            "platform": plat,
            "count": count,
            "live": sum(1 for p in mine if p.get("State") != "scheduled"),
            "scheduled": sum(1 for p in mine if p.get("State") == "scheduled"),
            "last": last.strftime("%I:%M %p").lstrip("0") if last else "",
            "upcoming": [u.strftime("%I:%M %p").lstrip("0") for u in upcoming],
            "untimed": len(untimed),
            # earliest() reads the clock again a moment later: within a minute counts as now
            "next_ok": next_ok.strftime("%I:%M %p").lstrip("0") if next_ok and next_ok - n > datetime.timedelta(minutes=1)
            else ("now" if plat not in NO_FLOOR else "no floor"),
            "next_pref": next_pref.strftime("%I:%M %p").lstrip("0") if next_pref and next_pref > n else "",
            "ceiling": ceil,
            "left": max(0, ceil - count) if ceil is not None else None,
            "over": ceil is not None and count > ceil,
            "source": c["source"], "note": c["note"],
            "week": week_count(plat) if plat in WEEKLY else None,
            "week_target": WEEKLY[plat][0] if plat in WEEKLY else None,
            "week_note": f"{WEEKLY[plat][1]} ({PACING_SKILL})" if plat in WEEKLY else "",
            "flag": ("No Story yet today: the skill says a Story every day."
                     if plat == "Instagram Story" and count == 0 and n.hour >= 17 else
                     "A post today has no time recorded: check it on the platform."
                     if untimed and plat not in NO_FLOOR else ""),
        })
    return out


# Weekly numbers from the plug-in's platform-posting-pacing skill (read 27 Sep 2026).
PACING_SKILL = "example-plugin:platform-posting-pacing"
WEEKLY = {
    "Substack": (1, "about 1 a week; the risk named is irregularity"),
    "YouTube": (3, "3 or more a week"),
    "Instagram": (3, "3 to 5 a week, earned feed posts only"),
}
DAY_START = datetime.time(8, 0)       # a post held to tomorrow waits until 8 am Central


def week_count(platform: str) -> int:
    n = now()
    monday = (n - datetime.timedelta(days=n.weekday())).strftime("%Y-%m-%d")
    return sum(1 for p in record.rows("Posts")
               if p.get("Platform") == platform and monday <= (p.get("Date (Central)") or "") <= n.strftime("%Y-%m-%d"))


def next_slot(platform: str) -> tuple[datetime.datetime | None, str]:
    """When a new post to this platform may go, and why, as the pacing skill
    sets it: the floor is a blocking gate for every route; a post today with no
    time recorded blocks until its real time is checked on the platform; a
    full day waits for tomorrow. None means held until someone checks."""
    n = now()
    day = n.strftime("%Y-%m-%d")
    mine = [p for p in record.rows("Posts") if p.get("Platform") == platform and p.get("Date (Central)") == day]
    if platform not in NO_FLOOR and any(not _when(p) for p in mine):
        return None, ("A post to " + platform + " today has no time recorded. Check its real time on "
                      "the platform and put it in the Posts tab; until then this waits.")
    t = earliest(platform)
    row = next((r for r in today() if r["platform"] == platform), None)
    if row and row["ceiling"] is not None and row["count"] >= row["ceiling"]:
        tomorrow = datetime.datetime.combine(n.date() + datetime.timedelta(days=1), DAY_START, CENTRAL)
        return max(t, tomorrow), f"{platform} has had its {row['ceiling']} for today, so this waits for tomorrow."
    if t - n > datetime.timedelta(seconds=30):
        return t, f"The hour between posts to {platform}: not before {t.strftime('%I:%M %p').lstrip('0')}."
    return n, ""


def earliest(platform: str) -> datetime.datetime:
    """Earliest time a new post may go to this platform (floor + upcoming)."""
    n = now()
    if platform in NO_FLOOR:
        return n
    times = [w for w in (_when(p) for p in record.rows("Posts")
                         if p.get("Platform") == platform) if w]
    t = n
    # step past every existing post that sits within an hour of t
    for w in sorted(times):
        if abs((t - w).total_seconds()) < FLOOR.total_seconds():
            t = w + FLOOR
    return t
