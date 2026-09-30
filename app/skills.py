"""Skills and plug-ins: every skill each agent has, in one place.

- Claude: the Example Shop plug-in (lives in his Claude account).
- Kimi: the nine handover skills and the nine video-pipeline worker skills
  (read live from their SKILL.md files on this laptop).
- Connectors Claude works through, and the tools on this laptop.

The app doesn't run a skill itself. "Ask ... to run this" puts his request,
in his words, in the Requests tab for that agent's next session or pass.
"""
import pathlib
import re

from . import paths, record
from .ward import actionlog

KIMI_HANDOVER = paths.PIPELINE / "Kimi Handover" / ".kimi" / "skills"
KIMI_PIPELINE = paths.PIPELINE / ".kimi" / "skills"

# Claude plug-in skills (Example Shop), with the Kimi skill that does the same job.
JOBS = [
    ("Etsy listings", "etsy-listing", "example-etsy-listing",
     "Writes, audits or shortens Etsy listing copy from his description of a piece, and builds the draft on Etsy. Drafts only; he clicks Publish."),
    ("Listing launch", "listing-launch", "example-listing-launch",
     "When a listing goes live: gathers the piece's photos and video, gets his OK on the copy, and posts it everywhere with the shop link, spaced to the pacing floor."),
    ("Photo posting", "photo-post-multiplatform", "example-photo-posting",
     "Posts photos of a piece or the website across his platforms, captions from his dictation."),
    ("Video posting", "video-post-multiplatform", "example-video-posting",
     "Publishes a cut, Short, Reel or clip across his platforms: intake, captions, routes, verification."),
    ("Build videos", "process-longform", "example-process-longform",
     "One Descript project per piece; collects progress clips and cuts the creation video when he asks."),
    ("Longform essays", "longform-essay-multiplatform", "example-longform-essay",
     "Essays built from his own material, fact-checked, cut per platform. Composing is Claude's; Kimi posts finished pieces."),
    ("Community surfaces", "platform-community-surfaces", "example-community-surfaces",
     "Which groups and communities each post should also land in; which are gated, hostile or dead."),
    ("Posting pacing", "platform-posting-pacing", "example-posting-pacing",
     "The check before any post: today's volume per platform and the hour-apart floor. The app runs this check too."),
    ("Scheduled passes", "scheduled-passes", "example-scheduled-passes",
     "The daily, weekly and monthly passes, and the take-over / Claude-is-back switch."),
]

CONNECTORS = [
    ("Google Drive", "Claude", "Reads and files his docs; the app also has its own Google link."),
    ("Descript (Agent Underlord)", "Claude", "Edits and publishes build videos in Descript."),
    ("OpusClip", "Claude", "Clips and transcripts. Its API needs a paid plan; the browser route is used."),
    ("WordPress.com", "Claude", "The old site, kept as a record. The connector is blocked on the free plan (9 Sep)."),
    ("Google Calendar", "Claude", "Events and scheduling."),
    ("Claude in Chrome", "Claude", "Drives his Chrome for posting routes."),
    ("Kimi Browser Extension", "Kimi", "Drives his Chrome for Kimi's posting routes."),
]

TOOLS = [
    ("Example uploader (oms_upload.py)", "App", "Direct posting to Pixelfed and Bluesky (YouTube API locks private).", "/post"),
    ("Video and photo prep", "App", "Bitrate-only video re-encode, never cropped; resized photo copies.", "/files"),
    ("Drive to laptop", "App", "Downloads footage and photos once, into batch folders.", "/files"),
    ("Backups", "App", "Website pages, the Sheet, drafts and logs, to the laptop and Drive.", "/files"),
]


CURRENT_HELPERS = {"photo-triage", "listing-image-pull", "upload-stage"}


def _front(p: pathlib.Path) -> dict:
    txt = p.read_text(encoding="utf-8", errors="replace")[:3000]
    name = re.search(r"^name:\s*(.+)$", txt, re.M)
    desc = re.search(r"^description:\s*(.+)$", txt, re.M)
    d = (desc.group(1).strip().strip('"') if desc else "").replace("â€”", "—")
    return {"name": name.group(1).strip() if name else p.parent.name, "description": d,
            "path": str(p)}


def kimi_skills(folder: pathlib.Path) -> list[dict]:
    if not folder.is_dir():
        return []
    return [_front(p) for p in sorted(folder.glob("*/SKILL.md"))]


def catalogue() -> dict:
    kimi = {s["name"]: s for s in kimi_skills(KIMI_HANDOVER)}
    jobs = [{"job": j, "claude": c, "kimi": k, "what": w, "kimi_found": k in kimi,
             "kimi_desc": kimi.get(k, {}).get("description", "")} for j, c, k, w in JOBS]
    # Only the helpers the current pipeline uses; the rest served the long-form
    # YouTube pipeline, which isn't in use (removed from the app 27 Sep 2026).
    workers = [s for s in kimi_skills(KIMI_PIPELINE) if s["name"] in CURRENT_HELPERS]
    return {"jobs": jobs, "workers": workers}


PLUGIN = "example-plugin"
BY_JOB = {j: (c, k) for j, c, k, _ in JOBS}
BY_ID = {c: (j, c, k) for j, c, k, _ in JOBS}


def skill_words(agent: str, skill: str) -> str:
    """How to name the skill so each agent finds the right one: Claude by its
    plug-in name, Kimi by its own skill, ChatGPT by the job (it has neither)."""
    if skill in BY_JOB:                  # the Skills page sends the job name
        job, (cid, kid) = skill, BY_JOB[skill]
    else:                                # the page buttons send the plug-in id
        job, cid, kid = BY_ID.get(skill, (skill, None, None))
    if agent == "Claude" and cid:
        return f"Use your plug-in skill {PLUGIN}:{cid} ({job})."
    if agent == "Kimi" and kid:
        return f"Use your skill {kid} ({job})."
    if agent == "ChatGPT" and cid:
        return (f"Job: {job} (Claude's {PLUGIN}:{cid}). Do the part ChatGPT can do (drafting from his "
                f"words, reviewing, checking), and say what Claude or Kimi must do on the laptop.")
    return f"Run your skill \"{skill}\"."


def ask(agent: str, skill: str, note: str, who: str = "Sam") -> str:
    sid = record.next_id("Requests", "S-")
    words = skill_words(agent, skill) + (f" {note}" if note else "")
    record.append("Requests", {
        "ID": sid, "When (Central)": actionlog.now_central(), "His words (verbatim)": words,
        "About": "operations", "For": agent, "Status": "open", "Result": "",
        "Updated": "From the Skills page"})
    actionlog.log(who, f"Asked {agent} to run {skill} ({sid}).")
    return sid
