"""File jobs, part two: video prep (job 2) and photo prep (job 3).

Video (his rule, 25 Sep 2026): re-encode the bitrate only, about 2400k at
30 fps; keep the full frame (1080x1920 stays 1080x1920); never crop, never
scale, never reframe. If 2400k would land over the 10 MB browser-route limit,
the bitrate is lowered just enough to fit; the frame is never touched.

Photos: resized copies only, never a crop, originals never changed. Copies go
next to the originals, in <batch>\\photos-sized\\<size>\\.
  web   2048 px long side, quality 92, metadata stripped (the ledger's
        proven setting: ~700 KB, no visible loss) - Bluesky, Pixelfed,
        Instagram, Threads, Tumblr, Facebook
  etsy  3000 px long side max (never enlarged), quality 92, metadata stripped

Runs by itself: the worker in server.py calls prep_queue() every few minutes,
so ready files exist before an item reaches Sam for approval.
"""
import json
import pathlib
import re
import subprocess

from PIL import Image, ImageOps

from . import paths, record
from .ward import actionlog, fences

MAX_BYTES = 10 * 1000 * 1000 - 300_000          # under 10 MB with headroom
TARGET_KBPS = 2400
AUDIO_KBPS = 128
PHOTO_SIZES = {"web": 2048, "etsy": 3000}
ETSY_MAX_BYTES = 1_000_000        # etsy-listing skill: under 1 MB per file
ETSY_MIN_SIDE = 2000              # etsy-listing skill: at least 2000px on both sides
VIDEO_EXT = {".mp4", ".mov", ".m4v"}
PHOTO_EXT = {".jpg", ".jpeg", ".png", ".webp"}
STATE = paths.DATA / "prep_state.json"


def ffmpeg() -> str:
    import imageio_ffmpeg
    return imageio_ffmpeg.get_ffmpeg_exe()


def probe(p: pathlib.Path) -> dict:
    """Duration, size and frame of a video, read from ffmpeg's own report."""
    r = subprocess.run([ffmpeg(), "-hide_banner", "-i", str(p)],
                       capture_output=True, text=True, errors="replace",
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    txt = r.stderr
    d = re.search(r"Duration: (\d+):(\d+):([\d.]+)", txt)
    v = re.search(r"Video: .*?, (\d{2,5})x(\d{2,5})", txt)
    fps = re.search(r"([\d.]+) fps", txt)
    rot = re.search(r"rotation of (-?\d+)", txt) or re.search(r"rotate\s*:\s*(-?\d+)", txt)
    dur = int(d[1]) * 3600 + int(d[2]) * 60 + float(d[3]) if d else None
    return {"duration": dur, "width": int(v[1]) if v else None,
            "height": int(v[2]) if v else None, "fps": float(fps[1]) if fps else None,
            "rotation": int(rot[1]) if rot else 0, "bytes": p.stat().st_size}


def video(src, dest=None, who: str = "App") -> dict:
    src = fences.check_readable(src)
    if dest is None:
        dest = src.parent.parent / "ready" / src.name if src.parent.name in ("originals", "opusclip") \
            else src.parent / "ready" / src.name
    dest = fences.check_writable(dest)
    if dest.resolve() == src.resolve():
        raise ValueError("prep would overwrite the original")
    dest.parent.mkdir(parents=True, exist_ok=True)
    before = probe(src)
    if before["bytes"] <= MAX_BYTES and (before["fps"] or 30) <= 30.5:
        kbps = None   # already fits: straight copy, no re-encode
    else:
        fit = int((MAX_BYTES * 8 / 1000) / (before["duration"] or 60)) - AUDIO_KBPS - 40
        kbps = max(600, min(TARGET_KBPS, fit))
    tmp = dest.with_name(dest.stem + ".part.mp4")
    if kbps is None:
        tmp.write_bytes(src.read_bytes())
    else:
        # bitrate and frame rate only: no -vf, no scale, no crop
        cmd = [ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-i", str(src),
               "-c:v", "libx264", "-preset", "medium",
               "-b:v", f"{kbps}k", "-maxrate", f"{int(kbps * 1.25)}k", "-bufsize", f"{kbps * 2}k",
               "-r", "30", "-pix_fmt", "yuv420p",
               "-c:a", "aac", "-b:a", f"{AUDIO_KBPS}k",
               "-map_metadata", "0", "-movflags", "+faststart", str(tmp)]
        subprocess.run(cmd, check=True, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    after = probe(tmp)
    expected = (before["width"], before["height"])
    if kbps is not None and abs(before.get("rotation") or 0) in (90, 270):
        expected = (before["height"], before["width"])   # rotation applied, same frame
    same_frame = expected == (after["width"], after["height"])
    if not same_frame:
        tmp.unlink()
        raise RuntimeError(f"frame changed {before['width']}x{before['height']} -> "
                           f"{after['width']}x{after['height']}; not kept")
    if after["bytes"] > MAX_BYTES:
        tmp.unlink()
        raise RuntimeError(f"still {after['bytes'] / 1e6:.1f} MB after re-encode")
    tmp.replace(dest)
    actionlog.log(who, f"Video prep: {src.name} {before['bytes'] / 1e6:.1f} MB -> "
                       f"{after['bytes'] / 1e6:.1f} MB, {after['width']}x{after['height']} "
                       f"kept, {kbps or 'no re-encode'}{'k' if kbps else ''}.")
    return {"src": str(src), "dest": str(dest), "before": before, "after": probe(dest),
            "kbps": kbps}


def frame(video_path, at: float, out) -> str:
    out = fences.check_writable(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run([ffmpeg(), "-y", "-hide_banner", "-loglevel", "error", "-ss", str(at),
                    "-i", str(fences.check_readable(video_path)), "-frames:v", "1",
                    "-q:v", "3", str(out)], check=True,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    return str(out)


def photo(src, who: str = "App") -> dict:
    src = fences.check_readable(src)
    base = src.parent.parent if src.parent.name == "originals" else src.parent
    out = {}
    with Image.open(src) as im0:
        im0 = ImageOps.exif_transpose(im0)          # upright, as the phone shows it
        before = {"size": im0.size, "bytes": src.stat().st_size}
        for name, long_side in PHOTO_SIZES.items():
            dest = fences.check_writable(base / "photos-sized" / name / (src.stem + ".jpg"))
            if dest.exists():
                out[name] = str(dest)
                continue
            dest.parent.mkdir(parents=True, exist_ok=True)
            im = im0.convert("RGB")
            if max(im.size) > long_side:
                im.thumbnail((long_side, long_side), Image.LANCZOS)   # keeps the whole frame
            im.save(dest, "JPEG", quality=92, optimize=True)          # no EXIF written
            # etsy-listing skill: "Under 1MB per file for the Etsy uploader". Only the
            # quality steps down; the frame and size stay as they are.
            q = 92
            while name == "etsy" and dest.stat().st_size >= ETSY_MAX_BYTES and q > 60:
                q -= 6
                im.save(dest, "JPEG", quality=q, optimize=True)
            out[name] = str(dest)
    actionlog.log(who, f"Photo prep: {src.name} -> web and Etsy copies (original unchanged).")
    return {"src": str(src), "before": before, "out": out}


# ------------------------------------------------------------------ automatic
def _state() -> dict:
    return json.loads(STATE.read_text(encoding="utf-8")) if STATE.exists() else {}


def _find_in_batch(batch: str, name: str) -> pathlib.Path | None:
    b = paths.BATCHES / batch
    if not name or not b.is_dir():
        return None
    for p in b.rglob(name.strip()):
        return p
    return None


def prep_queue() -> list[str]:
    """Make sure every queued item's files are prepped. Quiet if nothing to do."""
    done = []
    st = _state()
    for q in record.rows("Queue"):
        if q.get("Status", "").lower() in ("done", "superseded", "held"):
            continue
        batch = q.get("Batch", "")
        for name in [n.strip() for n in q.get("File", "").split(",") if n.strip()]:
            p = _find_in_batch(batch, pathlib.Path(name).name)
            if not p or str(p) in st:
                continue
            try:
                if p.suffix.lower() in VIDEO_EXT and p.parent.name != "ready":
                    r = video(p)
                    st[str(p)] = {"ready": r["dest"], "when": actionlog.now_central()}
                    done.append(p.name)
                elif p.suffix.lower() in VIDEO_EXT:
                    st[str(p)] = {"ready": str(p), "when": actionlog.now_central(),
                                  "note": "already a ready file"}
                elif p.suffix.lower() in PHOTO_EXT:
                    r = photo(p)
                    st[str(p)] = {"ready": r["out"], "when": actionlog.now_central()}
                    done.append(p.name)
            except Exception as e:  # noqa: BLE001 - record it, try the rest
                st[str(p)] = {"error": str(e)[:300], "when": actionlog.now_central()}
    STATE.write_text(json.dumps(st, indent=2), encoding="utf-8")
    return done
