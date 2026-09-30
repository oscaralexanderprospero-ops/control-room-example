"""The writing library: every document in his writing folders, so he can
open any of them to edit.

Folders (from the Drive map, public side only):
  01 Books and Longform (all books, essays, fiction)
  02 Example Shop / 02 Listing Copy - Published and Ready
  03 Publishing and Social / 01 Publishing Queue and Plans
The private folders are never walked: the fence refuses them by ID and name,
and none of them sit under these roots.
"""
import json
import time

from . import google_auth, paths
from .ward import actionlog, fences

ROOTS = [
    ("Books and Longform", "1Fp3tYyrERZfOvFQYUQeyxqOARvUUQ_LM"),
    ("Listing Copy", "1PmZn8foRWoDBjoOw6LIZQsXdkOIzM95V"),
    ("Publishing Plans", "1reeoPVYeaePXPXdsVeu87fLKRrNvW0TP"),
]
CACHE = paths.DATA / "library.json"
DOC_TYPES = ("application/vnd.google-apps.document",
             "application/vnd.openxmlformats-officedocument.wordprocessingml.document")
FOLDER = "application/vnd.google-apps.folder"


def load(max_age: int = 6 * 3600, force: bool = False) -> dict:
    if CACHE.exists() and not force:
        d = json.loads(CACHE.read_text(encoding="utf-8"))
        if time.time() - d.get("t", 0) < max_age:
            return d
    if not google_auth.connected():
        return json.loads(CACHE.read_text(encoding="utf-8")) if CACHE.exists() else {"docs": []}
    svc = google_auth.drive()
    docs, todo, seen = [], [(name, fid, name) for name, fid in ROOTS], set()
    while todo and len(docs) < 1500:
        root, fid, path = todo.pop(0)
        if fid in seen:
            continue
        seen.add(fid)
        try:
            fences.check_drive_id(fid, path)
        except fences.Fenced:
            continue
        token = None
        while True:
            res = svc.files().list(
                q=f"'{fid}' in parents and trashed=false",
                fields="nextPageToken,files(id,name,mimeType,modifiedTime,webViewLink)",
                pageSize=200, pageToken=token).execute()
            for f in res.get("files", []):
                try:
                    fences.check_drive_id(f["id"], f["name"])
                except fences.Fenced:
                    continue
                if f["mimeType"] == FOLDER:
                    todo.append((root, f["id"], f"{path} / {f['name']}"))
                elif f["mimeType"] in DOC_TYPES:
                    name = f["name"]
                    state = ("superseded" if "SUPERSEDED" in name.upper()
                             else "current" if "CURRENT" in name.upper() else "")
                    docs.append({"id": f["id"], "name": name, "folder": path, "root": root,
                                 "modified": f.get("modifiedTime", "")[:10], "link": f.get("webViewLink", ""),
                                 "state": state, "gdoc": f["mimeType"] == DOC_TYPES[0]})
            token = res.get("nextPageToken")
            if not token:
                break
    docs.sort(key=lambda d: d["modified"], reverse=True)
    d = {"t": time.time(), "checked": actionlog.now_central(), "docs": docs}
    CACHE.write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")
    return d


def find(doc_id: str) -> dict | None:
    return next((d for d in load().get("docs", []) if d["id"] == doc_id), None)
