"""Video and photo pipelines, start to finish, on one page (his request,
27 Sep 2026). Each step reuses what the app already had:

  1. Get the files     Drive folder -> Batches\\<code>\\originals (files.drive_download),
                       or files already in a batch on the laptop.
  2. His words         the caption source is his dictation, typed or spoken, or the
                       spoken words of the video itself (the uploader's Whisper
                       captions). It goes to every platform verbatim; he cuts to fit
                       in the Inbox. Nothing is written for him.
  3. Prep              prep.video (bitrate only, never a crop) / prep.photo (resized
                       copies, originals untouched).
  4. Edit              captions (.srt/.vtt/.txt next to the ready video), or an edit
                       he asks for in his own words, handed to Claude, Kimi or ChatGPT.
                       The app itself never trims, crops or reframes (his 25 Sep rule).
  5. Approve           the item lands in his Inbox with every check (approvals.create).
  6. Post              Post page, as before: direct through the uploader for video on
                       Pixelfed/Bluesky, everything else handed to an agent or his click.
  7. File              done\\<date>\\<batch>\\ once every platform is posted.
"""
import json
import pathlib
import re
import subprocess
import threading

from . import approvals, files, paths, posting, prep, record
from .ward import actionlog, fences

JOBS = paths.DATA / "media_jobs.json"
_lock = threading.Lock()
EDITORS = ("Claude", "Kimi", "ChatGPT")
VIDEO_PLATFORMS = ["Pixelfed", "Bluesky", "YouTube", "YouTube title", "TikTok", "Facebook",
                   "Instagram", "Instagram Story", "Threads", "Tumblr"]
PHOTO_PLATFORMS = ["Pixelfed", "Bluesky", "Facebook", "Instagram", "Instagram Story",
                   "Threads", "Tumblr", "Etsy"]


# ------------------------------------------------------------------ background jobs
def _jobs() -> list[dict]:
    try:
        return json.loads(JOBS.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []


def _note(job_id: str, **kw) -> None:
    with _lock:
        js = _jobs()
        for j in js:
            if j["id"] == job_id:
                j.update(kw)
        JOBS.write_text(json.dumps(js[-60:], indent=2, ensure_ascii=False), encoding="utf-8")


def _new_job(kind: str, what: str) -> str:
    with _lock:
        js = _jobs()
        jid = f"{kind}-{len(js) + 1}-{actionlog.now_central()[-5:].replace(':', '')}"
        js.append({"id": jid, "kind": kind, "what": what, "status": "running",
                   "started": actionlog.now_central(), "result": ""})
        JOBS.write_text(json.dumps(js[-60:], indent=2, ensure_ascii=False), encoding="utf-8")
    return jid


def recent_jobs(n: int = 12) -> list[dict]:
    return list(reversed(_jobs()))[:n]


def _run(kind: str, what: str, fn, *a) -> str:
    jid = _new_job(kind, what)

    def go():
        try:
            _note(jid, status="done", result=str(fn(*a))[:600], ended=actionlog.now_central())
        except Exception as e:  # noqa: BLE001 - shown on the page, never hidden
            _note(jid, status="failed", result=str(e)[:600], ended=actionlog.now_central())
    threading.Thread(target=go, daemon=True).start()
    return jid


# ------------------------------------------------------------------ 1. files
def in_batches(p) -> pathlib.Path:
    """A file path sent from the page must be a file inside Batches\\."""
    rp = fences.check_writable(paths.ROOT / p if not pathlib.Path(p).is_absolute() else p)
    if paths.BATCHES.resolve() not in rp.parents or not rp.is_file():
        raise fences.Fenced("not a file in Batches")
    return rp


def batch_code_ok(code: str) -> bool:
    return bool(re.fullmatch(r"[0-9]{1,4}[A-Za-z]?", code or ""))


def import_drive(folder_id: str, batch: str, who: str = "Sam") -> str:
    if not batch_code_ok(batch):
        raise ValueError("batch code must be a number like 27")

    def job():
        r = files.drive_download(folder_id, batch, who)
        return (f"Batch {batch}: {len(r.get('downloaded', []))} downloaded, "
                f"{len(r.get('copied_from_laptop', []))} copied from the laptop, "
                f"{len(r.get('skipped', []))} already here.")
    return _run("drive", f"Drive folder into batch {batch}", job)


def media_in_batches() -> list[dict]:
    """Every video and photo on the laptop, by batch, with what prep made."""
    st = prep._state()
    out = []
    for b in sorted((p for p in paths.BATCHES.iterdir() if p.is_dir() and not p.name.startswith("_")),
                    key=lambda p: p.name, reverse=True):
        items = []
        for f in sorted(b.rglob("*")):
            if not f.is_file():
                continue
            ext = f.suffix.lower()
            parts = {x.lower() for x in f.relative_to(b).parts[:-1]}
            if "ready" in parts or "photos-sized" in parts:
                continue                                  # prep's own output, shown with its source
            if ext in prep.VIDEO_EXT:
                kind = "video"
            elif ext in prep.PHOTO_EXT:
                kind = "photo"
            else:
                continue
            s = st.get(str(f), {})
            ready = s.get("ready")
            items.append({"path": str(f), "rel": f.relative_to(paths.ROOT).as_posix(), "name": f.name,
                          "kind": kind, "folder": str(f.parent.relative_to(b)),
                          "mb": round(f.stat().st_size / 1e6, 1),
                          "ready": ready, "prep_error": s.get("error"),
                          "captions": _captions_for(ready if isinstance(ready, str) else str(f))})
        if items:
            out.append({"batch": b.name, "items": items})
    return out


def _captions_for(video: str) -> str | None:
    t = pathlib.Path(video).with_suffix(".txt")
    return t.read_text(encoding="utf-8", errors="replace")[:4000] if t.exists() else None


# ------------------------------------------------------------------ 3. prep
def prep_files(paths_: list[str]) -> str:
    done = []
    for p in paths_:
        p = in_batches(p)
        if p.suffix.lower() in prep.VIDEO_EXT:
            prep.video(p, who="Sam")
        elif p.suffix.lower() in prep.PHOTO_EXT:
            prep.photo(p, who="Sam")
        done.append(p.name)
    return f"Prepped {', '.join(done)}."


def _ready_for(p: pathlib.Path, platform_kind: str = "web") -> pathlib.Path:
    """The prepped copy of a file (making it now if it's missing)."""
    if p.suffix.lower() in prep.VIDEO_EXT:
        if p.parent.name == "ready":
            return p
        dest = (p.parent.parent if p.parent.name in ("originals", "opusclip") else p.parent) / "ready" / p.name
        if not dest.exists():
            prep.video(p, who="App")
        return dest
    r = prep.photo(p, who="App")
    return pathlib.Path(r["out"][platform_kind])


# ------------------------------------------------------------------ 4. edit
def make_captions(video: str) -> str:
    """The uploader's own Whisper captions, written next to the ready video."""
    v = in_batches(video)
    target = _ready_for(v)
    r = subprocess.run([str(posting.PY_UPLOADER), "-u", "oms_upload.py", "captions", str(target)],
                       cwd=str(paths.UPLOADER), capture_output=True, text=True, errors="replace",
                       timeout=3600, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    if not target.with_suffix(".txt").exists():
        raise RuntimeError("captions not written: " + actionlog.scrub((r.stdout + r.stderr)[-400:]))
    actionlog.log("Sam", f"Captions made for {target.name} (.srt, .vtt, .txt next to it).")
    return f"Captions written next to {target.name}. Read the words before you use them."


def ask_edit(file_path: str, words: str, to: str, who: str = "Sam") -> str:
    if to not in EDITORS or not words.strip():
        raise ValueError("pick an agent and say what you want")
    p = in_batches(file_path)
    sid = record.next_id("Requests", "S-")
    record.append("Requests", {
        "ID": sid, "When (Central)": actionlog.now_central(),
        "His words (verbatim)": (f"Edit this file: {p}. What he wants, in his words: {words.strip()} "
                                 f"— Keep the full frame (never crop, his 25 Sep rule) unless he says "
                                 f"otherwise here. Put the edited copy next to it with \"-edit\" in the "
                                 f"name; never change the original."),
        "About": "upload", "For": to, "Status": "open", "Result": "", "Updated": "From Video and photo"})
    actionlog.log(who, f"Asked {to} to edit {p.name} ({sid}).")
    return sid


# ------------------------------------------------------------------ 2 + 5. start a post
NO_TAGS = {"Facebook", "TikTok", "Etsy", "Etsy title", "YouTube title", "Instagram Story"}


def platform_text(platform: str, words: str, tags: list[str]) -> str:
    """His words for one platform, following the plug-in's rules: TikTok's
    description is always blank; Facebook stays hashtag-free; tags go at the
    end everywhere else that has them."""
    if platform == "TikTok":
        return ""
    if tags and platform not in NO_TAGS:
        return words + "\n\n" + " ".join(tags)
    return words


def start_post(file_paths: list[str], piece: str, words: str, platforms: list[str],
               ai_written: bool = False, who: str = "Sam", tags: str = "",
               alt: str = "", earned: str = "") -> str:
    """His new post: a Queue row, prepped files, and a draft in his Inbox whose
    text on every platform is his own words, verbatim."""
    if not file_paths or not words.strip() or not platforms:
        raise ValueError("pick files, give your words, and pick platforms")
    ps = [in_batches(f) for f in file_paths]
    kinds = {"video" if p.suffix.lower() in prep.VIDEO_EXT else "photo" for p in ps}
    if len(kinds) > 1:
        raise ValueError("a post is either video or photos, not both")
    media = kinds.pop()
    allowed = VIDEO_PLATFORMS if media == "video" else PHOTO_PLATFORMS
    platforms = [p for p in platforms if p in allowed]
    # pacing skill: Instagram feed posts are earned (about 2x his usual on another platform)
    if "Instagram" in platforms and not earned.strip():
        raise ValueError("Instagram feed posts are earned only: say where this already did well "
                         "(a link or a few words), or untick Instagram. Stories are always fine.")
    alts = [a.strip() for a in alt.splitlines() if a.strip()]
    if media == "photo" and "Bluesky" in platforms and len(alts) < len(ps):
        raise ValueError(f"Bluesky needs alt text for every photo: describe each one, one line per "
                         f"photo ({len(ps)} photos, {len(alts)} lines).")
    tag_list = ["#" + t.lstrip("#") for t in re.split(r"[\s,]+", tags) if t.strip("# ")]
    batch = next((x for x in ps[0].parts if batch_code_ok(x) and (paths.BATCHES / x).is_dir()), "")
    qid = record.next_id("Queue", "Q-")
    record.append("Queue", {
        "ID": qid, "Batch": batch, "Piece": piece.strip()[:200],
        "File": ", ".join(p.name for p in ps), "Platforms left": ", ".join(platforms),
        "Status": "waiting on approval", "Source dictation": words.strip()[:45000],
        "Link rule": "Shop link only if the Listings tab shows the listing live",
        "Order": "", "Claimed by": "", "Notes": f"{media} post started in the Control Room",
        "Source": f"{who}, Video and photo page", "As of": actionlog.now_central()[:10]})
    actionlog.log(who, f"Started a {media} post {qid}: {piece[:80]} ({len(ps)} file(s)).")

    def job():
        from . import checks
        ready = []
        for p in ps:
            kind = "etsy" if platforms == ["Etsy"] else "web"
            ready.append(str(_ready_for(p, kind).relative_to(paths.ROOT)))
        # video-post Stage 0, intake: the spoken words are read against the filming rules
        intake = []
        if media == "video":
            for p in ps:
                r = paths.ROOT / ready[ps.index(p)]
                try:
                    if not r.with_suffix(".txt").exists():
                        make_captions(str(p))
                    spoken = r.with_suffix(".txt").read_text(encoding="utf-8", errors="replace")
                    intake += checks.spoken_problems(spoken)
                except Exception as e:  # noqa: BLE001 - never skip intake silently
                    intake.append(f"Couldn't transcribe {p.name} ({str(e)[:120]}): watch it and check "
                                  f"the spoken words yourself before approving.")
        text = words.strip()
        aid = approvals.create(item=f"{piece.strip()[:120]} ({media})", queue_id=qid, source=text,
                               platforms={p: platform_text(p, text, tag_list) for p in platforms},
                               by=who, files=ready, ai_written=ai_written)
        d = approvals.load(aid)
        d.update(media=media, alt=alts, tags=tag_list, earned=earned.strip(),
                 intake=intake, intake_done=media == "video")
        approvals.save(d)
        warn = f" Intake flagged {len(intake)} spoken line(s): read them in the Inbox." if intake else ""
        return f"Ready for you in the Inbox as {aid} ({len(ready)} file(s) prepped).{warn}"
    return _run("post", f"{media} post {qid}: {piece[:60]}", job)


# ------------------------------------------------------------------ 6. where everything is
def pipeline() -> list[dict]:
    """Every queued media item and how far it has got."""
    by_q = {}
    for a in record.rows("Approvals"):
        d = approvals.load(a["ID"])
        if d and d.get("queue_id"):
            by_q.setdefault(d["queue_id"], []).append((a, d))
    out = []
    for q in record.rows("Queue"):
        if q.get("Status", "").lower() in ("superseded",):
            continue
        steps = []
        ap = by_q.get(q["ID"], [])
        a, d = ap[-1] if ap else (None, None)
        steps.append(("Files on the laptop", bool(q.get("File"))))
        steps.append(("Prepped", bool(d and posting.ready_files(d))))
        steps.append(("In your Inbox", bool(a)))
        steps.append(("Approved", bool(a and a.get("Status") in ("approved", "posted"))))
        posted = [p for p, v in (d or {}).get("platforms", {}).items() if v.get("status") == "posted"]
        steps.append((f"Posted ({len(posted)})" if posted else "Posted", bool(posted)))
        steps.append(("Filed", bool(d and d.get("filed"))))
        out.append({"id": q["ID"], "piece": q.get("Piece", ""), "status": q.get("Status", ""),
                    "files": q.get("File", ""), "approval": a["ID"] if a else "",
                    "media": (d or {}).get("media", "video"), "steps": steps,
                    "as_of": q.get("As of", "")})
    return list(reversed(out))
