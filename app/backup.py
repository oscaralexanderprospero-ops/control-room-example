"""Backups of important files and website pages.

Each run makes Backup\\<date>\\ on the laptop holding:
  - site\\     every page in the live site's sitemap: the full HTML and the
               full text, with the address and fetch time (full pages, never
               summaries, per filing rule 6)
  - record\\   the Sheet as .xlsx, and the app's laptop copy of the record
  - drafts\\   the drafts folder
  - public\\   the generated public status page
  - logs\\     the action log and the Suspicious list
Then the small text files are copied to Drive, into the app's backup folder.

Never backed up anywhere: config\\ (the app's keys and sign-ins) and the
Uploader's config\\. Videos and photos are not re-uploaded, because the
originals already live in Drive.
"""
import datetime
import html.parser
import json
import pathlib
import shutil
import urllib.request
import xml.etree.ElementTree as ET

from . import google_auth, paths, record
from .ward import actionlog, fences

SITEMAP = "https://example.com/sitemap.xml"
STATE = paths.DATA / "backup_state.json"
# Drive: 02 Example Shop / 03 Operations and Trackers (from the map)
OPS_FOLDER = "1efoJNUVM9o9TGwB5LVIlTJVn5pDKmsW7"


class _Text(html.parser.HTMLParser):
    SKIP = {"script", "style", "noscript", "svg"}
    BLOCK = {"p", "h1", "h2", "h3", "h4", "li", "br", "div", "section",
             "blockquote", "tr", "summary"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.skip = 0
        self.out = []

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_endtag(self, tag):
        if tag in self.SKIP and self.skip:
            self.skip -= 1
        elif tag in self.BLOCK:
            self.out.append("\n")

    def handle_data(self, data):
        if not self.skip:
            self.out.append(data)


def _text(raw: str) -> str:
    p = _Text()
    p.feed(raw)
    lines = [ln.strip() for ln in "".join(p.out).splitlines()]
    out, prev = [], ""
    for ln in lines:
        if ln or prev:
            out.append(ln)
        prev = ln
    return "\n".join(out).strip() + "\n"


def _slug(url: str) -> str:
    s = url.split("://", 1)[-1].split("/", 1)[-1].strip("/") or "home"
    return s.replace("/", "__")[:150]


def _state() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def status() -> dict:
    s = _state()
    return {"last": s.get("last"), "pages": s.get("pages"), "folder": s.get("folder"),
            "drive_folder_url": s.get("drive_folder_url"), "drive_error": s.get("drive_error")}


def run(who: str = "App") -> dict:
    day = datetime.date.today().isoformat()
    base = fences.check_writable(paths.BACKUP / day)
    (base / "site").mkdir(parents=True, exist_ok=True)

    # 1. website pages, full
    with urllib.request.urlopen(SITEMAP, timeout=30) as r:
        root = ET.fromstring(r.read())
    ns = {"s": "http://www.sitemaps.org/schemas/sitemap/0.9"}
    urls = [u.find("s:loc", ns).text for u in root.findall("s:url", ns)]
    pages, failed = 0, []
    stamp = actionlog.now_central()
    for url in urls:
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Control-Room-backup"})
            with urllib.request.urlopen(req, timeout=30) as r:
                raw = r.read().decode("utf-8", "replace")
            slug = _slug(url)
            (base / "site" / f"{slug}.html").write_text(raw, encoding="utf-8")
            (base / "site" / f"{slug}.txt").write_text(
                f"Source: {url}\nCaptured: {stamp} Central\n\n" + _text(raw),
                encoding="utf-8")
            pages += 1
        except Exception as e:  # noqa: BLE001 - note it and carry on
            failed.append(f"{url}: {e}")

    # 2. the record
    (base / "record").mkdir(exist_ok=True)
    if record.CACHE.exists():
        shutil.copy2(record.CACHE, base / "record" / "record_cache.json")
    sid = record.sheet_id()
    if sid and google_auth.connected():
        try:
            data = google_auth.drive().files().export(
                fileId=sid,
                mimeType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            ).execute()
            (base / "record" / "Example Record.xlsx").write_bytes(data)
        except Exception as e:  # noqa: BLE001
            failed.append(f"Sheet export: {e}")

    # 3. drafts, public page, logs (never config)
    for src, name in ((paths.DRAFTS, "drafts"), (paths.PUBLIC_OUT, "public")):
        if src.exists():
            shutil.copytree(src, base / name, dirs_exist_ok=True)
    (base / "logs").mkdir(exist_ok=True)
    for f in ("actions.jsonl", "suspicious.jsonl"):
        if (paths.DATA / f).exists():
            shutil.copy2(paths.DATA / f, base / "logs" / f)
    for p in base.rglob("*"):
        fences.check_not_blocked(p)

    # 4. copy the text files to Drive
    drive_note = _to_drive(base, day)

    st = _state()
    st.update(last=stamp, pages=pages, folder=str(base), failed=failed, **drive_note)
    STATE.write_text(json.dumps(st, indent=2), encoding="utf-8")
    actionlog.log(who, f"Backup {day}: {pages} website pages, the record, drafts and "
                       f"logs saved to Backup\\{day}"
                       + (" and Drive" if drive_note.get("drive_uploaded") else "")
                       + (f"; {len(failed)} could not be fetched" if failed else "") + ".")
    return st


def _to_drive(base: pathlib.Path, day: str) -> dict:
    if not google_auth.connected():
        return {"drive_error": "Google not connected; laptop backup only."}
    try:
        from googleapiclient.http import MediaFileUpload
        svc = google_auth.drive()
        st = _state()
        folder = st.get("drive_folder_id")
        if not folder:
            # Filed per the Drive map: never at the root.
            f = svc.files().create(body={
                "name": "Control Room Backups",
                "mimeType": "application/vnd.google-apps.folder",
                "parents": [OPS_FOLDER]},
                fields="id,webViewLink").execute()
            folder = f["id"]
            st.update(drive_folder_id=folder, drive_folder_url=f["webViewLink"])
            STATE.write_text(json.dumps(st, indent=2), encoding="utf-8")
        day_folder = svc.files().create(body={
            "name": day, "mimeType": "application/vnd.google-apps.folder",
            "parents": [folder]}, fields="id").execute()["id"]
        n = 0
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.suffix.lower() not in (".txt", ".xlsx", ".jsonl", ".json", ".html"):
                continue
            if p.suffix == ".html" and "site" in p.parts:
                continue  # the .txt beside it is the full text; keeps Drive light
            svc.files().create(body={"name": str(p.relative_to(base)).replace("\\", " - "),
                                     "parents": [day_folder]},
                               media_body=MediaFileUpload(str(p), resumable=False),
                               fields="id").execute()
            n += 1
        return {"drive_uploaded": n, "drive_error": None,
                "drive_folder_url": st.get("drive_folder_url")}
    except Exception as e:  # noqa: BLE001
        return {"drive_error": str(e)[:300]}
