"""Every folder the app knows about, in one place."""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent          # Control Room
APP = ROOT / "app"
CONFIG = ROOT / "config"          # local secrets: never logged, never backed up
DATA = ROOT / "data"
BATCHES = ROOT / "Batches"
UPLOAD_TODAY = ROOT / "Upload Today"
TO_DELETE = ROOT / "_to_delete"
BACKUP = ROOT / "Backup"
PUBLIC_OUT = ROOT / "public"
DRAFTS = ROOT / "drafts"

HOME = pathlib.Path.home()
DOWNLOADS = HOME / "Downloads"
PIPELINE = HOME / "Videos" / "Video Pipeline"
UPLOADER = PIPELINE / "Uploader"
UPLOADER_CONFIG = UPLOADER / "config"
UPLOADER_DONE = UPLOADER / "done"

for p in (CONFIG, DATA, BATCHES, UPLOAD_TODAY, TO_DELETE, BACKUP, PUBLIC_OUT,
          DRAFTS):
    p.mkdir(parents=True, exist_ok=True)
