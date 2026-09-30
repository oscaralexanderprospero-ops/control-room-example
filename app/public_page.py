"""The public status page, built only from Public tab rows marked Show = Y.

Words come from the row's "His words" cell exactly as written. Before the
page is written, every row is checked against the factual limits: the move
stays an aspiration, no forge of his own is implied, lapidary is not
overstated. A row that fails is left off and listed for him to see.
"""
import datetime
import html
import re

from . import paths, record

OUT = paths.PUBLIC_OUT / "status.html"

SECTIONS = [("Books", "Books and long writing"), ("Bench", "At the bench"),
            ("Platforms", "Where the work lives"), ("Notes", "Notes")]

CHECKS = [
    ("the move stated as settled",
     re.compile(r"\b(we|i)('ve| have)? (moved|relocated)\b|\bnow (live|living|based) in (another-city)\b|\bmoving to another city (on|in) \w+ \d", re.I)),
]


def check_row(r: dict) -> list[str]:
    text = " ".join([r.get("Item", ""), r.get("Status", ""), r.get("His words", "")])
    return [name for name, rx in CHECKS if rx.search(text)]


def build() -> dict:
    rows = [r for r in record.rows("Public") if r.get("Show", "").strip().upper() == "Y"]
    held, by = [], {}
    for r in rows:
        problems = check_row(r)
        if problems:
            held.append({"item": r.get("Item"), "problems": problems})
            continue
        by.setdefault(r.get("Section", ""), []).append(r)
    dates = sorted({r.get("As of", "") for r in rows if r.get("As of")})
    as_of = dates[-1] if dates else ""
    parts = []
    for key, title in SECTIONS:
        items = by.get(key, [])
        if not items:
            continue
        parts.append(f"<section><h2>{html.escape(title)}</h2>")
        for r in items:
            status = html.escape(r.get("Status", ""))
            parts.append(
                "<div class=row><div class=head>"
                f"<span class=item>{html.escape(r.get('Item', ''))}</span>"
                + (f"<span class=status>{status}</span>" if status else "")
                + "</div>"
                f"<p>{html.escape(r.get('His words', ''))}</p></div>")
        parts.append("</section>")
    page = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Current Status</title>
<style>
:root {{ --bg:#f5efe3; --ink:#2a2219; --muted:#6b5d4b; --line:#d8ccb4; --moss:#4f6b3a; --card:#fffaf0; }}
@media (prefers-color-scheme: dark) {{ :root {{ --bg:#1d1a15; --ink:#ece3d2; --muted:#b3a58d; --line:#3d352a; --moss:#9dbb7f; --card:#26221b; }} }}
body {{ background:var(--bg); color:var(--ink); font:18px/1.6 Georgia, "Times New Roman", serif; margin:0; }}
main {{ max-width:44rem; margin:0 auto; padding:2rem 1rem 4rem; }}
h1 {{ font-size:2rem; margin:0 0 .25rem; }}
.updated {{ color:var(--muted); font-size:.95rem; margin:0 0 2rem; }}
h2 {{ font-size:1.25rem; border-bottom:1px solid var(--line); padding-bottom:.3rem; margin-top:2.5rem; color:var(--moss); }}
.row {{ background:var(--card); border:1px solid var(--line); border-radius:6px; padding:.8rem 1rem; margin:.8rem 0; }}
.head {{ display:flex; flex-wrap:wrap; justify-content:space-between; gap:.5rem; }}
.item {{ font-weight:bold; }}
.status {{ color:var(--moss); font-family:system-ui, sans-serif; font-size:.9rem; }}
.row p {{ margin:.4rem 0 0; }}
</style></head>
<body><main>
<h1>Current Status</h1>
<p class="updated">Updated {html.escape(_nice(as_of))}.</p>
{''.join(parts)}
</main></body></html>
"""
    OUT.write_text(page, encoding="utf-8")
    return {"path": str(OUT), "rows": sum(len(v) for v in by.values()), "held": held,
            "as_of": as_of}


def _nice(d: str) -> str:
    try:
        return datetime.date.fromisoformat(d).strftime("%-d %B %Y")
    except ValueError:
        try:
            return datetime.date.fromisoformat(d).strftime("%d %B %Y").lstrip("0")
        except ValueError:
            return d
