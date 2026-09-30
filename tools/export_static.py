"""Export the demo as plain HTML pages (for a free static host).
Crawls the app in read-only mode and saves every page it can reach."""
import os
import pathlib
import re
import shutil
import sys

os.environ["PUBLIC_DEMO"] = "1"
ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from app import server  # noqa: E402

OUT = ROOT / "static-demo"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir()
shutil.copytree(ROOT / "app" / "static", OUT / "static")

client = server.app.test_client()
SKIP = ("/api/", "/media-file", "/listing-photo", "/prep-demo", "/act/", "/studio/", "/chatgpt-packet", "/enter")


def name_of(path: str) -> str:
    path = path.split("?")[0].split("#")[0].strip("/") or "plan"
    return re.sub(r"[^A-Za-z0-9_.-]+", "_", path) + ".html"


BANNER = ('<div style="background:#f6e7b4;color:#3a2c00;padding:8px 14px;font:14px system-ui;'
          'text-align:center">Read-only demo with made-up data. Buttons do nothing here. '
          '<a href="https://github.com/oscaralexanderprospero-ops/control-room-example">Get the code</a></div>')

NOTE = ("<script>try{localStorage.setItem('oms_tour_'+document.body.dataset.page,'99')}catch(e){}function ro(e){e.preventDefault();e.stopImmediatePropagation();"
        "alert('Read-only demo: buttons do not change anything here.');}"
        "document.addEventListener('submit',ro,true);"
        "document.addEventListener('click',function(e){if(e.target.closest&&e.target.closest('button[data-op]'))ro(e);},true);"
        "</script>")

seen, todo = set(), ["/plan"]
while todo:
    p = todo.pop()
    if p in seen or p.startswith(SKIP):
        continue
    seen.add(p)
    r = client.get(p)
    if r.status_code != 200 or "text/html" not in r.content_type:
        continue
    html = r.get_data(as_text=True)
    for href in re.findall(r'href="(/[^"#]*)"', html):
        if not href.startswith(("/static/",)) and not href.startswith(SKIP):
            todo.append(href.split("?")[0])

    def fix(m):
        url = m.group(2)
        if url.startswith("/static/"):
            return f'{m.group(1)}="{url[1:]}"'
        if url.startswith(SKIP):
            return f'{m.group(1)}="#"'
        return f'{m.group(1)}="{name_of(url)}"'
    html = re.sub(r'(href|action)="(/[^"#]*)"', fix, html)
    html = re.sub(r'(src)="(/static/[^"]*)"', lambda m: f'src="{m.group(2)[1:]}"', html)
    html = re.sub(r"(<body[^>]*>)", lambda m: m.group(1) + BANNER + NOTE, html, count=1)
    (OUT / name_of(p)).write_text(html, encoding="utf-8")

(OUT / "index.html").write_text('<meta http-equiv="refresh" content="0; url=plan.html">', encoding="utf-8")
print("pages:", sorted(f.name for f in OUT.glob("*.html")))
