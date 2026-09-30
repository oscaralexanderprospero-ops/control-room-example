"""Stage 3: one-click posting.

Routes per platform:
  direct            posts through the existing uploader (oms_upload.py), run as
                    its own process. The app never reads the uploader's config;
                    it asks the uploader's own "status" command what is set up.
  hand to agent     the job goes to the on-duty agent as a request, with the
                    file path in Upload Today and the approved text.
  needs your click  only Sam can do it; the app gives Show file, Copy file,
                    the page to open, and an "I posted it" box for the link.

Pacing: each platform job waits until its earliest allowed time (the one-hour
floor, 88 minutes preferred when free) and shows when that will be. The
worker in server.py runs due jobs every minute.

Files: job 5 keeps Upload Today holding exactly today's approved files, named
by batch code. Job 6 is Show file / Copy file. Job 7 files each posted file
into done\\<date>\\<batch>\\ and writes where it went into the record.
"""
import datetime
import json
import os
import pathlib
import re
import shutil
import subprocess
import threading
import uuid

from . import approvals, pacing, paths, record
from .ward import actionlog, fences

JOBS = paths.DATA / "post_jobs.json"
DONE_DIR = paths.ROOT / "done"
_lock = threading.Lock()
PY_UPLOADER = pathlib.Path(os.environ.get("APPDATA", "")) / "kimi-desktop" / "daimon-share" / \
    "daimon" / "runtime" / "python" / ".venv" / "Scripts" / "python.exe"
OUTBOX = paths.UPLOADER / "outbox"

# Why each platform has no direct route today (shown to Sam).
REASONS = {
    "YouTube": ("hand", "Uploads through YouTube's API are locked private until the API "
                "project is audited (ledger V2 and the uploader's lock check). The browser "
                "route in Studio works."),
    "YouTube title": ("with", "YouTube"),
    "TikTok": ("hand", "TikTok's API only allows private posts until the app is audited. "
               "The browser route in TikTok Studio works."),
    "Facebook": ("hand", "Meta setup is paused by your ruling (ads balance first). "
                 "Browser route through Business Suite."),
    "Instagram": ("hand", "Meta setup is paused by your ruling. Browser route."),
    "Instagram Story": ("click", "Business Suite's Story composer has had no file input since "
                        "24 Sep: a phone job for you (about 15 seconds)."),
    "Threads": ("hand", "No uploader route; browser route."),
    "Tumblr": ("hand", "No uploader route; browser route."),
    "Etsy": ("click", "Drafts only; Publish is always your click."),
    "Etsy title": ("with", "Etsy"),
}
DIRECT = {"Pixelfed": "pixelfed", "Bluesky": "bluesky"}
UPLOAD_PAGES = {
    "YouTube": "https://studio.youtube.com/channel/YOUR-CHANNEL-ID/videos/upload",
    "TikTok": "https://www.tiktok.com/tiktokstudio/upload",
    "Facebook": "https://business.facebook.com/latest/home?asset_id=YOUR-ASSET-ID&business_id=YOUR-BUSINESS-ID",
    "Instagram Story": "https://business.facebook.com/latest/home?asset_id=YOUR-ASSET-ID&business_id=YOUR-BUSINESS-ID",
    "Etsy": "https://www.etsy.com/your/shops/me/tools/listings",
}
ALT = {  # alt text for approved batches, keyed by batch/clip id (example)
    "A": "A walnut walking stick held up against a green field, showing the oiled grain near the handle.",
}


# ------------------------------------------------------------------ uploader
def uploader_status() -> dict:
    """What the uploader itself says is set up (its 'status' command)."""
    try:
        r = subprocess.run([str(PY_UPLOADER), "oms_upload.py", "status"], cwd=str(paths.UPLOADER),
                           capture_output=True, text=True, timeout=120, errors="replace",
                           creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        out = r.stdout
    except Exception as e:  # noqa: BLE001
        return {"error": str(e)}
    st = {}
    for name in ("youtube", "bluesky", "pixelfed", "meta"):
        m = re.search(rf"^\s*{name}:\s*(.+)$", out, re.M)
        st[name] = bool(m and m.group(1).strip().startswith("stored"))
    return st


def route(platform: str, st: dict | None = None, media: str = "video") -> tuple[str, str]:
    st = st if st is not None else uploader_status()
    if platform in DIRECT and media == "photo":
        return "hand", "Your uploader posts video only, so photo posts go by the browser route."
    if platform in DIRECT:
        if st.get(DIRECT[platform]):
            return "direct", "Posts through your uploader."
        return "hand", f"The uploader isn't set up for {platform} yet."
    r = REASONS.get(platform, ("hand", "No direct route."))
    return r


# ------------------------------------------------------------------ files (jobs 5-7)
def ready_file(d: dict) -> pathlib.Path | None:
    for f in d.get("files", []):
        p = paths.ROOT / f if not pathlib.Path(f).is_absolute() else pathlib.Path(f)
        if p.exists():
            return p
    return None


def ready_files(d: dict) -> list[pathlib.Path]:
    out = []
    for f in d.get("files", []):
        p = paths.ROOT / f if not pathlib.Path(f).is_absolute() else pathlib.Path(f)
        if p.exists():
            out.append(p)
    return out


def stage(d: dict) -> pathlib.Path | None:
    """Job 5: copy the approved files into Upload Today (named by batch code).
    A photo post can carry several; "staged" stays the first, for the uploader."""
    staged = []
    for src in ready_files(d):
        dest = fences.check_writable(paths.UPLOAD_TODAY / src.name)
        if not dest.exists():
            shutil.copy2(src, dest)
            actionlog.log("App", f"Upload Today: staged {src.name}.")
        staged.append(str(dest))
    if not staged:
        return None
    d["staged"] = staged[0]
    d["staged_all"] = staged
    return pathlib.Path(staged[0])


def file_done(d: dict, who: str = "App") -> str | None:
    """Job 7: once every platform is finished, file the staged copies into
    done\\<date>\\<batch>\\ and record where they went."""
    names = d.get("staged_all") or ([d["staged"]] if d.get("staged") else [])
    filed = []
    for s in names:
        staged = pathlib.Path(s)
        if not staged.exists():
            continue
        batch = re.match(r"(\d+)", staged.name)
        dest = fences.check_writable(DONE_DIR / datetime.date.today().isoformat() /
                                     (batch.group(1) if batch else "other") / staged.name)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(staged), str(dest))
        filed.append(dest)
    if not filed:
        return None
    d["filed"] = str(filed[0])
    d["filed_all"] = [str(f) for f in filed]
    q = record.find("Queue", "ID", d.get("queue_id", ""))
    if q:
        record.set_cell("Queue", q["_row"], "Status", "done")
        record.set_cell("Queue", q["_row"], "Notes",
                        (q.get("Notes", "") + f" Filed: {', '.join(str(f) for f in filed)}").strip())
    actionlog.log(who, f"Filed {', '.join(f.name for f in filed)} into {filed[0].parent}.")
    return str(filed[0])


def copy_to_clipboard(path: str) -> bool:
    """Job 6, second half: put the file on the clipboard so Sam can paste it
    into an upload box. UNVERIFIED per site until it has worked on each."""
    p = fences.check_showable(path)
    if not p.is_file():
        return False
    # single quotes doubled so a file name can never break out of the string
    lit = str(p).replace("'", "''")
    r = subprocess.run(["powershell", "-NoProfile", "-Command",
                        f"Set-Clipboard -LiteralPath '{lit}'"],
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return r.returncode == 0


# ------------------------------------------------------------------ jobs
def _jobs() -> list[dict]:
    return json.loads(JOBS.read_text(encoding="utf-8")) if JOBS.exists() else []


def _save_jobs(js: list[dict]) -> None:
    JOBS.write_text(json.dumps(js, indent=2, ensure_ascii=False), encoding="utf-8")


def jobs_for(aid: str) -> list[dict]:
    return [j for j in _jobs() if j["approval"] == aid]


def plan(aid: str, who: str = "Sam") -> list[dict]:
    """The one click: schedule every approved platform of an item."""
    d = approvals.load(aid)
    if not d:
        raise ValueError("no such item")
    stage(d)
    approvals.save(d)
    st = uploader_status()
    js = _jobs()
    already = {(j["approval"], j["platform"]) for j in js}
    made = []
    for plat, p in d["platforms"].items():
        if p.get("status") != "approved" or (aid, plat) in already:
            continue
        r, why = route(plat, st, d.get("media", "video"))
        if r == "with":            # e.g. YouTube title travels with YouTube
            continue
        # the pacing gate applies to every route, not only the uploader's
        when, wait = pacing.next_slot(plat)
        job = {"id": uuid.uuid4().hex[:8], "approval": aid, "platform": plat, "route": r,
               "why": why, "not_before": (when or pacing.now()).isoformat(),
               "held": when is None, "wait": wait, "status": "waiting",
               "result": None, "created": actionlog.now_central()}
        js.append(job)
        made.append(job)
        if r == "hand":
            hand_to_agent(d, plat, why, when, wait)
            job["status"] = "handed to agent"
    _save_jobs(js)
    actionlog.log(who, f"Post {aid}: {len(made)} platform jobs set "
                       f"({', '.join(j['platform'] + ' ' + j['route'] for j in made)}).")
    return made


def hand_to_agent(d: dict, plat: str, why: str, when=None, wait: str = "") -> None:
    duty = record.duty().get("passes") or "Claude"
    text = d["platforms"][plat].get("text", "")
    extra = ""
    if plat == "YouTube" and "YouTube title" in d["platforms"]:
        extra = f" Title: {d['platforms']['YouTube title'].get('text', '')}."
    caps = [str(f.with_suffix(x)) for f in ready_files(d) for x in (".srt", ".vtt")
            if f.with_suffix(x).exists()]
    if caps:
        extra += f" Captions files: {', '.join(caps)} (.srt for YouTube and Facebook, .vtt for Bluesky)."
    if d.get("alt"):
        extra += f" Alt text, his, one per file in order: {' | '.join(d['alt'])}."
    if when is None:
        extra += f" PACING: held. {wait}"
    else:
        extra += (f" PACING: not before {when.strftime('%Y-%m-%d %I:%M %p')} Central. {wait} "
                  f"Re-check the platform's own last post time before posting.")
    record.append("Requests", {
        "ID": record.next_id("Requests", "S-"), "When (Central)": actionlog.now_central(),
        "His words (verbatim)": (f"Post approved item {d['id']} ({d.get('item', '')}) to {plat}. "
                                 f"File{'s' if len(d.get('staged_all') or []) > 1 else ''}: "
                                 f"{', '.join(d.get('staged_all') or [d.get('staged', '')])}.{extra} Approved text: "
                                 f"{text or '(blank by rule)'} — Check pacing first, verify on "
                                 f"the platform, then report the post with POST /api/posts."),
        # "posting job": the upload pass works these (GET /api/uploads/due); the hourly check leaves them
        "About": "posting job", "For": duty, "Status": "open", "Result": "",
        "Updated": f"Handed by the app: {why}"})


def run_due() -> list[dict]:
    """Worker: run every direct job whose time has come."""
    ran = []
    with _lock:
        js = _jobs()
        now = pacing.now()
        for j in js:
            if j["status"] != "waiting" or j["route"] != "direct":
                continue
            if datetime.datetime.fromisoformat(j["not_before"]) > now:
                continue
            # re-check the whole gate right before posting: floor, daily ceiling, untimed posts
            t, wait = pacing.next_slot(j["platform"])
            j["held"], j["wait"] = t is None, wait
            if t is None or t > pacing.now():            # a fresh "now": next_slot returns its own
                if t is not None:
                    j["not_before"] = t.isoformat()
                continue
            j["status"] = "posting"
            _save_jobs(js)
            try:
                j["result"] = _post_direct(j)
                j["status"] = "posted" if j["result"].get("url") else "failed"
            except Exception as e:  # noqa: BLE001
                j["status"], j["result"] = "failed", {"error": str(e)[:400]}
            ran.append(j)
            _save_jobs(js)
            _after(j)
    return ran


def _post_direct(j: dict) -> dict:
    d = approvals.load(j["approval"])
    src = pathlib.Path(d.get("staged") or "")
    if not src.exists():
        src = ready_file(d)
    name = f"{src.stem}--{DIRECT[j['platform']]}"
    vid = fences.check_writable(OUTBOX / f"{name}{src.suffix}")
    shutil.copy2(src, vid)
    # captions made in the app sit next to the ready file; the uploader picks up <video>.srt
    for cand in [src.with_suffix(".srt")] + [f.with_suffix(".srt") for f in ready_files(d)]:
        if cand.exists():
            shutil.copy2(cand, fences.check_writable(vid.with_suffix(".srt")))
            break
    text = d["platforms"][j["platform"]]["text"]
    code = re.match(r"(\d+[A-Z])", src.name)
    spec = {"video": vid.name, "title": d.get("item", src.stem)[:100],
            "alt_text": ALT.get(code.group(1) if code else "", ""),
            "platforms": {DIRECT[j["platform"]]: {"caption": text, "text": text}}}
    sidecar = fences.check_writable(OUTBOX / f"{name}.json")
    sidecar.write_text(json.dumps(spec, ensure_ascii=False, indent=2), encoding="utf-8")
    r = subprocess.run([str(PY_UPLOADER), "-u", "oms_upload.py", "post", str(sidecar)],
                       cwd=str(paths.UPLOADER), capture_output=True, text=True, errors="replace",
                       timeout=1800, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    log = (r.stdout + r.stderr)[-3000:]
    res_file = paths.UPLOADER_DONE / f"{name}.result.json"
    if not res_file.exists():
        res_file = OUTBOX / f"{name}.result.json"
    res = json.loads(res_file.read_text(encoding="utf-8")) if res_file.exists() else {}
    out = res.get(DIRECT[j["platform"]], {})
    return {"url": out.get("url"), "error": out.get("error"), "log": actionlog.scrub(log)}


def _after(j: dict) -> None:
    d = approvals.load(j["approval"])
    plat = j["platform"]
    if j["status"] == "posted":
        n = pacing.now()
        pid = record.next_id("Posts", "P-")
        record.append("Posts", {
            "ID": pid, "Date (Central)": n.strftime("%Y-%m-%d"), "Time (Central)": n.strftime("%H:%M"),
            "Platform": plat, "Item": d.get("item", ""), "URL": j["result"]["url"],
            "Caption as posted": d["platforms"][plat]["text"], "Posted by": "App (uploader)",
            "State": "live", "Source": f"oms_upload.py result, approval {d['id']}",
            "As of": n.strftime("%Y-%m-%d")})
        d["platforms"][plat]["status"] = "posted"
        d["platforms"][plat]["url"] = j["result"]["url"]
        if plat == "YouTube" and "YouTube title" in d["platforms"]:
            d["platforms"]["YouTube title"]["status"] = "posted"
        actionlog.log("App", f"Posted {d['id']} to {plat}: {j['result']['url']}")
    else:
        actionlog.log("App", f"Posting {d['id']} to {plat} failed.",
                      error=(j["result"] or {}).get("error", ""))
    approvals.save(d)
    maybe_finish(d)


def record_manual(aid: str, plat: str, url: str, who: str = "Sam") -> None:
    """'I posted it': Sam (or an agent) posted by hand; record it."""
    d = approvals.load(aid)
    if not d or plat not in d["platforms"]:
        raise ValueError("no such item or platform")
    n = pacing.now()
    record.append("Posts", {
        "ID": record.next_id("Posts", "P-"), "Date (Central)": n.strftime("%Y-%m-%d"),
        "Time (Central)": n.strftime("%H:%M"), "Platform": plat, "Item": d.get("item", ""),
        "URL": url, "Caption as posted": d["platforms"][plat].get("text", ""), "Posted by": who,
        "State": "live", "Source": f"recorded in the Control Room, approval {aid}",
        "As of": n.strftime("%Y-%m-%d")})
    d["platforms"][plat]["status"] = "posted"
    d["platforms"][plat]["url"] = url
    js = _jobs()
    for j in js:
        if j["approval"] == aid and j["platform"] == plat:
            j["status"] = "posted"
            j["result"] = {"url": url, "by": who}
    _save_jobs(js)
    approvals.save(d)
    actionlog.log(who, f"Recorded {aid} {plat} as posted: {url}")
    maybe_finish(d)


# ------------------------------------------------------------------ the upload pass (browser routes)
CLAIM_HOURS = 2


def due_jobs(who: str) -> list[dict]:
    """Browser-route posts whose pacing time has come, for the upload pass.
    Each carries everything the agent needs; none is due twice."""
    from . import surfaces
    out = []
    now = pacing.now()
    for j in _jobs():
        if j["route"] != "hand" or j["status"] not in ("handed to agent", "claimed"):
            continue
        if j.get("claimed_by") and j["claimed_by"] != who and \
                (now - datetime.datetime.fromisoformat(j["claimed_at"])).total_seconds() < CLAIM_HOURS * 3600:
            continue                                  # the other agent has it
        when, wait = pacing.next_slot(j["platform"])
        if when is None or when > pacing.now():       # a fresh "now": next_slot returns its own
            continue
        d = approvals.load(j["approval"])
        if not d:
            continue
        caps = [str(f.with_suffix(x)) for f in ready_files(d) for x in (".srt", ".vtt") if f.with_suffix(x).exists()]
        out.append({"job_id": j["id"], "approval": d["id"], "item": d.get("item", ""), "platform": j["platform"],
                    "text": d["platforms"].get(j["platform"], {}).get("text", ""),
                    "youtube_title": d["platforms"].get("YouTube title", {}).get("text", "") if j["platform"] == "YouTube" else "",
                    "files": d.get("staged_all") or ([d["staged"]] if d.get("staged") else []),
                    "captions": caps, "alt_text": d.get("alt", []), "media": d.get("media", "video"),
                    "why_browser": j.get("why", ""), "upload_page": UPLOAD_PAGES.get(j["platform"], ""),
                    "also_land_in": surfaces.also_land_in(d.get("item", ""), [j["platform"]])})
    return out


def _find_job(job_id: str) -> tuple[list, dict | None]:
    js = _jobs()
    return js, next((j for j in js if j["id"] == job_id), None)


def claim_job(job_id: str, who: str) -> bool:
    with _lock:
        js, j = _find_job(job_id)
        if not j or j["route"] != "hand" or j["status"] == "posted":
            return False
        now = pacing.now()
        if j.get("claimed_by") and j["claimed_by"] != who and \
                (now - datetime.datetime.fromisoformat(j["claimed_at"])).total_seconds() < CLAIM_HOURS * 3600:
            return False
        j.update(status="claimed", claimed_by=who, claimed_at=now.isoformat())
        _save_jobs(js)
    actionlog.log(who, f"Claimed posting job {job_id} ({j['platform']}, {j['approval']}).")
    return True


def finish_job(job_id: str, url: str, who: str) -> bool:
    """The agent posted it and checked it live: record it like his 'It's posted'
    (Posts row, pacing, filing when every platform is done), and close the request."""
    js, j = _find_job(job_id)
    if not j or j.get("claimed_by") not in (who, None):
        return False
    record_manual(j["approval"], j["platform"], url, who)
    for r in record.rows("Requests"):
        if r.get("About") == "posting job" and r.get("Status") in ("open", "working") and \
                f"{j['approval']} " in r.get("His words (verbatim)", "") and \
                f"to {j['platform']}." in r.get("His words (verbatim)", ""):
            record.set_cell("Requests", r["_row"], "Status", "done")
            record.set_cell("Requests", r["_row"], "Result", f"Posted and checked live: {url}")
            record.set_cell("Requests", r["_row"], "Updated", f"{actionlog.now_central()} {who}")
    return True


def fail_job(job_id: str, why: str, who: str) -> bool:
    with _lock:
        js, j = _find_job(job_id)
        if not j:
            return False
        j.update(status="handed to agent", claimed_by=None, claimed_at=None,
                 result={"error": why[:400], "by": who})
        _save_jobs(js)
    actionlog.log(who, f"Posting job {job_id} ({j['platform']}) not done: {why[:200]}")
    return True


def maybe_finish(d: dict) -> None:
    left = [p for p, v in d["platforms"].items()
            if v.get("status") != "posted" and p not in ("YouTube title", "Etsy title")]
    if not left and not d.get("filed"):
        file_done(d)
        approvals.save(d)
        r = record.find("Approvals", "ID", d["id"])
        if r:
            record.set_cell("Approvals", r["_row"], "Status", "posted")


def board() -> list[dict]:
    """Everything approved and not finished, with each platform's route and timing."""
    st = None
    out = []
    for a in record.rows("Approvals"):
        d = approvals.load(a["ID"])
        if not d or a.get("Status") not in ("approved",):
            continue
        st = st if st is not None else uploader_status()
        js = {j["platform"]: j for j in jobs_for(a["ID"])}
        plats = []
        for plat, p in d["platforms"].items():
            r, why = route(plat, st, d.get("media", "video"))
            if r == "with":
                continue
            j = js.get(plat)
            when, wait = pacing.next_slot(plat)
            why = (why + " " + wait).strip() if wait else why
            plats.append({"platform": plat, "route": r, "why": why, "job": j,
                          "status": p.get("status"), "url": p.get("url"),
                          "earliest": ("held: check the platform" if when is None else
                                       when.strftime("%a %I:%M %p").replace(" 0", " ") if when > pacing.now() else "now"),
                          "page": UPLOAD_PAGES.get(plat)})
        from . import surfaces
        out.append({"id": a["ID"], "item": d.get("item"), "staged": d.get("staged"),
                    "file": str(ready_file(d) or ""), "platforms": plats,
                    "planned": bool(js),
                    "also": surfaces.also_land_in(d.get("item", ""), list(d["platforms"]))})
    return out
