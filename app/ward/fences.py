"""Fences in code. Every file move and every Drive read goes through here.

- Files: the app may only change things under Downloads\\_prep*,
  Videos\\Video Pipeline\\ (never its Uploader\\config\\) and
  Control Room\\ (never its config\\). Everything else is read-only,
  and only for comparing duplicates.
- Drive: the private folders and CREDENTIALS are refused by ID, and any
  folder whose parents lead into them is refused too.
"""
import pathlib

from .. import paths


class Fenced(Exception):
    """Raised when something tries to cross a fence."""


# Never readable or writable by any code path in this app.
BLOCKED_DIRS = [paths.UPLOADER_CONFIG, paths.CONFIG]

# Drive folders that are never listed, read, indexed or displayed.
BLOCKED_DRIVE = {
    # Drive folder ID: label. Add the IDs of any private folders here.
}
BLOCKED_DRIVE_NAMES = ("personal and private", "private",
                       "credentials")


def _resolve(p) -> pathlib.Path:
    return pathlib.Path(p).resolve()


def _under(p: pathlib.Path, root: pathlib.Path) -> bool:
    try:
        p.relative_to(root.resolve())
        return True
    except ValueError:
        return False


def check_not_blocked(p) -> pathlib.Path:
    rp = _resolve(p)
    for b in BLOCKED_DIRS:
        if _under(rp, b):
            raise Fenced(f"blocked folder: {b.name}")
    return rp


def check_writable(p) -> pathlib.Path:
    """May the app create, move or change this path?"""
    rp = check_not_blocked(p)
    if _under(rp, paths.ROOT) or _under(rp, paths.PIPELINE):
        return rp
    if _under(rp, paths.DOWNLOADS):
        rel = rp.relative_to(paths.DOWNLOADS.resolve())
        if rel.parts and rel.parts[0].lower().startswith("_prep"):
            return rp
    raise Fenced(f"outside the folders the app may change: {rp}")


def check_readable(p) -> pathlib.Path:
    """Reading is allowed anywhere except the blocked folders."""
    return check_not_blocked(p)


def check_showable(p) -> pathlib.Path:
    """Show file / Copy file (buttons in the browser): only the app's own
    folders, the same ones it may change. Never the blocked folders, and
    never an arbitrary path sent in a form."""
    return check_writable(p)


def check_drive_id(file_or_folder_id: str, name: str = "") -> None:
    if file_or_folder_id in BLOCKED_DRIVE:
        raise Fenced("private Drive folder: " + BLOCKED_DRIVE[file_or_folder_id])
    low = (name or "").lower()
    if any(n in low for n in BLOCKED_DRIVE_NAMES):
        raise Fenced(f"private Drive folder by name: {name}")


def check_drive_ancestry(service, file_id: str) -> None:
    """Walk up the parents of a Drive item; refuse if any is private."""
    seen = set()
    todo = [file_id]
    while todo:
        fid = todo.pop()
        if fid in seen:
            continue
        seen.add(fid)
        check_drive_id(fid)
        meta = service.files().get(fileId=fid, fields="id,name,parents",
                                   supportsAllDrives=True).execute()
        check_drive_id(meta["id"], meta.get("name", ""))
        todo.extend(meta.get("parents", []) or [])
