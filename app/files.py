"""File jobs, part one.

Job 1  Drive to laptop: straight from Drive through the Drive API, once per
       file, into Batches\\<code>\\originals\\. Drive's own MD5 is compared with
       every file already on the laptop, so nothing downloads twice.
Job 4  Duplicates: identical contents (SHA-256), never by name. Extra copies
       are MOVED to _to_delete\\<date>\\, never deleted. Emptying _to_delete
       sends files to the Recycle Bin, and only after Sam confirms.
Tidy   One-time copy (not move) of the ready files in the old Downloads
       folders into Batches\\.

Every path goes through ward.fences first.
"""
import datetime
import hashlib
import json
import os
import pathlib
import shutil

from . import paths
from .ward import actionlog, fences

MEDIA = {".mp4", ".mov", ".m4v", ".jpg", ".jpeg", ".png", ".heic", ".webp",
         ".wav", ".mp3", ".srt", ".vtt"}
HASH_INDEX = paths.DATA / "hash_index.json"
MANIFEST = paths.TO_DELETE / "manifest.jsonl"

# The one-time tidy: old folder -> (batch, subfolder, rename map)
LEGACY = []  # old folder -> (batch, subfolder, rename map); add your own one-time tidy here
BATCH_NOTES = {}


# ------------------------------------------------------------------ hashing
def sha256(p: pathlib.Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def md5(p: pathlib.Path) -> str:
    h = hashlib.md5()  # noqa: S324 - matches Drive's md5Checksum, not security
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _index() -> dict:
    if HASH_INDEX.exists():
        return json.loads(HASH_INDEX.read_text(encoding="utf-8"))
    return {}


def _save_index(ix: dict) -> None:
    HASH_INDEX.write_text(json.dumps(ix), encoding="utf-8")


def _hashes(p: pathlib.Path, ix: dict) -> dict:
    st = p.stat()
    key = str(p)
    e = ix.get(key)
    if e and e["size"] == st.st_size and e["mtime"] == int(st.st_mtime):
        return e
    e = {"size": st.st_size, "mtime": int(st.st_mtime),
         "sha256": sha256(p), "md5": md5(p)}
    ix[key] = e
    return e


# ------------------------------------------------------------------ scanning
def scan_roots() -> list[pathlib.Path]:
    """Folders searched for duplicates and already-downloaded files."""
    roots = [paths.BATCHES, paths.UPLOAD_TODAY, paths.PIPELINE]
    roots += sorted(p for p in paths.DOWNLOADS.glob("_*") if p.is_dir())
    return roots


def _walk(root: pathlib.Path):
    for dirpath, dirnames, filenames in os.walk(root):
        dp = pathlib.Path(dirpath)
        try:
            fences.check_readable(dp)
        except fences.Fenced:
            dirnames[:] = []
            continue
        dirnames[:] = [d for d in dirnames if not d.startswith(".")]
        for fn in filenames:
            p = dp / fn
            if p.suffix.lower() in MEDIA:
                yield p


def downloads_loose() -> list[pathlib.Path]:
    """Media files sitting loose at the top of Downloads (read-only)."""
    return [p for p in paths.DOWNLOADS.iterdir()
            if p.is_file() and p.suffix.lower() in MEDIA]


# ------------------------------------------------------------------ tidy
def tidy_plan() -> list[dict]:
    plan = []
    for src_rel, batch, sub, renames in LEGACY:
        src_dir = paths.DOWNLOADS / src_rel
        if not src_dir.is_dir():
            continue
        for p in sorted(src_dir.iterdir()):
            if not p.is_file() or p.suffix.lower() not in MEDIA:
                continue
            if p.name.startswith("chk_"):
                continue  # check frames, not ready files
            dest = paths.BATCHES / batch / sub / renames.get(p.name, p.name)
            plan.append({"src": str(p), "dest": str(dest), "size": p.stat().st_size,
                         "exists": dest.exists()})
    return plan


def tidy_run(who: str = "App") -> dict:
    copied, skipped = 0, 0
    for item in tidy_plan():
        src, dest = pathlib.Path(item["src"]), pathlib.Path(item["dest"])
        fences.check_readable(src)
        fences.check_writable(dest)
        if dest.exists() and dest.stat().st_size == src.stat().st_size:
            skipped += 1
            continue
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)   # copy, never move; the original stays
        copied += 1
    for batch, note in BATCH_NOTES.items():
        f = paths.BATCHES / batch / "README.txt"
        if (paths.BATCHES / batch).is_dir() and not f.exists():
            f.write_text(note + "\n", encoding="utf-8")
    actionlog.log(who, f"Tidy: copied {copied} ready files from the old Downloads "
                       f"folders into Batches ({skipped} already there). Originals untouched.")
    return {"copied": copied, "skipped": skipped}


# ------------------------------------------------------------------ batches
def batches() -> list[dict]:
    out = []
    for b in sorted((p for p in paths.BATCHES.iterdir() if p.is_dir()), reverse=True):
        groups = []
        for sub in sorted(p for p in b.iterdir() if p.is_dir()):
            files = [{"name": f.name, "size": f.stat().st_size, "path": str(f),
                      "modified": datetime.datetime.fromtimestamp(f.stat().st_mtime).strftime("%d %b %H:%M")}
                     for f in sorted(sub.rglob("*")) if f.is_file()]
            groups.append({"name": sub.name, "files": files})
        note = (b / "README.txt").read_text(encoding="utf-8").strip() if (b / "README.txt").exists() else ""
        out.append({"code": b.name, "groups": groups, "note": note})
    return out


# ------------------------------------------------------------------ duplicates
def find_duplicates() -> list[dict]:
    """Groups of identical files. For each group: which copy stays, and which
    extra copies may move to _to_delete (only ones the app may change)."""
    ix = _index()
    by_size: dict[int, list[pathlib.Path]] = {}
    candidates = list(downloads_loose())
    for r in scan_roots():
        if r.exists():
            candidates += list(_walk(r))
    for p in candidates:
        try:
            by_size.setdefault(p.stat().st_size, []).append(p)
        except OSError:
            continue
    groups = []
    for size, ps in by_size.items():
        if len(ps) < 2 or size == 0:
            continue
        by_hash: dict[str, list[pathlib.Path]] = {}
        for p in ps:
            by_hash.setdefault(_hashes(p, ix)["sha256"], []).append(p)
        for h, same in by_hash.items():
            if len(same) < 2:
                continue
            groups.append(_plan_group(h, size, same))
    _save_index(ix)
    return [g for g in groups if g["move"]]


def _rank(p: pathlib.Path) -> tuple:
    s = str(p).lower()
    in_dupes = "\\dupes\\" in s
    numbered = " (1)" in p.name or " (2)" in p.name or " (3)" in p.name
    in_batches = s.startswith(str(paths.BATCHES).lower())
    return (in_dupes or numbered, not in_batches, len(s))


def _movable(p: pathlib.Path) -> bool:
    try:
        fences.check_writable(p)
    except fences.Fenced:
        return False
    s = str(p).lower()
    # Batches copies of the old ready files are intentional copies, and the
    # old ready folders stay until he says so: neither is "extra".
    if s.startswith(str(paths.BATCHES).lower()):
        return False
    if "\\ready\\" in s:
        return False
    return True


def _plan_group(h: str, size: int, same: list[pathlib.Path]) -> dict:
    keep = sorted(same, key=_rank)[0]
    move = [p for p in same if p != keep and _movable(p)
            and ("\\dupes\\" in str(p).lower() or " (" in p.name)]
    return {"sha256": h[:16], "size": size, "keep": str(keep),
            "copies": [str(p) for p in same], "move": [str(p) for p in move]}


def move_duplicates(who: str) -> dict:
    stamp = datetime.date.today().isoformat()
    moved = []
    for g in find_duplicates():
        keep = pathlib.Path(g["keep"])
        if not keep.exists():
            continue
        for m in g["move"]:
            src = fences.check_writable(m)
            if sha256(src) != sha256(keep):   # re-check right before moving
                continue
            rel = src.relative_to(paths.HOME) if str(src).startswith(str(paths.HOME)) else pathlib.Path(src.name)
            dest = fences.check_writable(paths.TO_DELETE / stamp / rel)
            dest.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(src), str(dest))
            with open(MANIFEST, "a", encoding="utf-8") as f:
                f.write(json.dumps({"when": actionlog.now_central(), "from": str(src),
                                    "to": str(dest), "identical_to": str(keep)}) + "\n")
            moved.append({"from": str(src), "to": str(dest)})
    actionlog.log(who, f"Moved {len(moved)} duplicate files to _to_delete (nothing deleted).")
    return {"moved": moved}


def to_delete_summary() -> dict:
    files = [p for p in paths.TO_DELETE.rglob("*") if p.is_file() and p.name != "manifest.jsonl"]
    return {"count": len(files), "bytes": sum(p.stat().st_size for p in files),
            "files": [str(p.relative_to(paths.TO_DELETE)) for p in files][:200]}


def empty_to_delete(who: str) -> dict:
    """Only ever called after Sam confirms. Sends to the Recycle Bin."""
    from send2trash import send2trash
    n = 0
    for p in list(paths.TO_DELETE.rglob("*")):
        if p.is_file() and p.name != "manifest.jsonl":
            fences.check_writable(p)
            send2trash(str(p))
            n += 1
    actionlog.log(who, f"Emptied _to_delete: {n} files sent to the Recycle Bin.")
    return {"recycled": n}


# ------------------------------------------------------------------ Drive (job 1)
DATED = ("pics/vids", "pics", "vids")


def drive_folders(limit: int = 15) -> list[dict]:
    """The dated "... pics/vids" folders at the Drive root, newest first."""
    from . import google_auth
    svc = google_auth.drive()
    q = ("'root' in parents and mimeType='application/vnd.google-apps.folder' "
         "and trashed=false and name contains 'pics'")
    res = svc.files().list(q=q, orderBy="createdTime desc", pageSize=limit,
                           fields="files(id,name,createdTime)").execute()
    out = []
    for f in res.get("files", []):
        try:
            fences.check_drive_id(f["id"], f["name"])
        except fences.Fenced:
            continue
        out.append(f)
    return out


def drive_plan(folder_id: str, batch: str) -> list[dict]:
    from . import google_auth
    svc = google_auth.drive()
    fences.check_drive_ancestry(svc, folder_id)
    res = svc.files().list(
        q=f"'{folder_id}' in parents and trashed=false",
        fields="files(id,name,size,md5Checksum,mimeType)", pageSize=500).execute()
    have = {e["md5"]: k for k, e in _index().items() if "md5" in e}
    plan = []
    for f in res.get("files", []):
        # footage and photos only; documents filed in the folder stay in Drive
        if not f["mimeType"].startswith(("image/", "video/")):
            continue
        dest = paths.BATCHES / batch / "originals" / f["name"]
        already = have.get(f.get("md5Checksum", "")) or (str(dest) if dest.exists() else None)
        plan.append({"id": f["id"], "name": f["name"], "size": int(f.get("size", 0)),
                     "md5": f.get("md5Checksum"), "dest": str(dest), "already": already})
    return plan


def drive_download(folder_id: str, batch: str, who: str) -> dict:
    """Refresh the hash index first so files already on the laptop are seen."""
    ix = _index()
    for r in scan_roots():
        if r.exists():
            for p in _walk(r):
                _hashes(p, ix)
    for p in downloads_loose():
        _hashes(p, ix)
    _save_index(ix)
    from googleapiclient.http import MediaIoBaseDownload
    from . import google_auth
    svc = google_auth.drive()
    got, skipped, copied = [], [], []
    for item in drive_plan(folder_id, batch):
        if item["already"]:
            dest = pathlib.Path(item["dest"])
            src = _best_local(item["md5"]) if item["md5"] else None
            if src and not dest.exists() and src != dest:
                # already on the laptop: copy it into the batch, don't re-download
                fences.check_writable(dest)
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(src, dest)
                copied.append(item["name"])
            else:
                skipped.append(item["name"])
            continue
        dest = fences.check_writable(item["dest"])
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        with open(tmp, "wb") as fh:
            dl = MediaIoBaseDownload(fh, svc.files().get_media(fileId=item["id"]),
                                     chunksize=8 << 20)
            done = False
            while not done:
                _, done = dl.next_chunk()
        if item["md5"] and md5(tmp) != item["md5"]:
            tmp.unlink()
            raise IOError(f"download check failed for {item['name']}")
        tmp.rename(dest)
        got.append(item["name"])
    actionlog.log(who, f"Drive to laptop, batch {batch}: {len(got)} downloaded, "
                       f"{len(copied)} copied from files already on the laptop, "
                       f"{len(skipped)} already in the batch.")
    return {"downloaded": got, "copied_from_laptop": copied, "skipped": skipped}


def _best_local(md5sum: str) -> pathlib.Path | None:
    """The best existing laptop copy with this content (not a dupes copy)."""
    matches = [pathlib.Path(k) for k, e in _index().items()
               if e.get("md5") == md5sum and pathlib.Path(k).exists()]
    if not matches:
        return None
    return sorted(matches, key=_rank)[0]
