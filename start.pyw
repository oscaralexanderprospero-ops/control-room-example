"""Desktop shortcut target: start the Control Room if it isn't running, then
open it in the default browser. Runs with no console window."""
import os
import pathlib
import socket
import subprocess
import sys
import time
import webbrowser

ROOT = pathlib.Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from app.ward import access  # noqa: E402

PORT = int(os.environ.get("CONTROL_ROOM_PORT", "8765"))


def running() -> bool:
    with socket.socket() as s:
        s.settimeout(0.5)
        return s.connect_ex(("127.0.0.1", PORT)) == 0


if not running():
    log = open(ROOT / "data" / "server.log", "a", encoding="utf-8")
    subprocess.Popen([str(ROOT / ".venv" / "Scripts" / "pythonw.exe"), "-m", "app.server"],
                     cwd=str(ROOT), stdout=log, stderr=log,
                     creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
    for _ in range(60):
        if running():
            break
        time.sleep(0.5)

access.ensure_keys()
url = f"http://127.0.0.1:{PORT}/enter?t={access.launch_key()}"

# Open as its own desktop window (Chrome's app mode: no tabs, no address bar,
# its own taskbar icon). Sam uses Chrome, never Edge.
LOCAL = pathlib.Path.home() / "AppData" / "Local"
APPS = [pathlib.Path(r"C:\Program Files\Google\Chrome\Application\chrome.exe"),
        pathlib.Path(r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe"),
        LOCAL / "Google" / "Chrome" / "Application" / "chrome.exe"]
exe = next((e for e in APPS if e.exists()), None)
if exe:
    subprocess.Popen([str(exe), f"--app={url}", "--window-size=1280,860"])
else:
    webbrowser.open(url)
