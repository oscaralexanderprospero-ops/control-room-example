"""Main photo of each listing, so Sam can see which piece is which.

Live listings: photo links read from his public shop pages (Etsy's own image
server, i.etsystatic.com, which serves files openly). Downloaded once into
data/listing_photos/<listing id>.jpg and served from the laptop.
Drafts are not public; their photos come from Shop Manager later, or he can
add one himself.
"""
import json
import urllib.request

from . import paths
from .ward import actionlog

URLS = paths.DATA / "listing_photo_urls.json"
DIR = paths.DATA / "listing_photos"
DIR.mkdir(exist_ok=True)
CDN = "https://i.etsystatic.com/"


def urls() -> dict:
    d = json.loads(URLS.read_text(encoding="utf-8")) if URLS.exists() else {}
    return {k: v for k, v in d.items() if not k.startswith("_")}


def has(lid: str) -> bool:
    return (DIR / f"{lid}.jpg").exists()


def fetch_all(who: str = "App") -> dict:
    got, failed = 0, []
    for lid, path in urls().items():
        f = DIR / f"{lid}.jpg"
        if f.exists():
            continue
        try:
            req = urllib.request.Request(CDN + path, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=30) as r:
                f.write_bytes(r.read())
            got += 1
        except Exception as e:  # noqa: BLE001
            failed.append(f"{lid}: {e}")
    actionlog.log(who, f"Listing photos: {got} downloaded, {len(failed)} failed.")
    return {"downloaded": got, "failed": failed}


def save_upload(lid: str, data: bytes, who: str = "Sam") -> None:
    from PIL import Image
    import io
    im = Image.open(io.BytesIO(data)).convert("RGB")
    im.thumbnail((800, 800))
    im.save(DIR / f"{lid}.jpg", "JPEG", quality=88)
    actionlog.log(who, f"Added a photo for listing {lid}.")
