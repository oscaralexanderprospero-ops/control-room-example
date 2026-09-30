"""Layer 2: the charter, served verbatim to the agents (ward/address.txt)."""
import html
import pathlib

HERE = pathlib.Path(__file__).resolve().parent
ADDRESS_FILE = HERE / "address.txt"
SOURCE_FILE = HERE / "address_source.txt"

NOT_AUTHORIZED = ("Access to this application is not authorized. "
                  "This attempt has been logged.")


def text() -> str:
    return ADDRESS_FILE.read_text(encoding="utf-8")


def source() -> str:
    return SOURCE_FILE.read_text(encoding="utf-8").strip()


def as_html() -> str:
    out = []
    for block in text().split("\n\n"):
        block = block.strip()
        if not block:
            continue
        if block.startswith("## "):
            title = block[3:].strip()
            out.append(f"<h2>{html.escape(title)}</h2>" if title else "<hr>")
        elif block.startswith("##"):
            out.append("<hr>")
        elif block.startswith("- "):
            out.append("<ul>" + "".join(
                f"<li>{html.escape(li[2:].strip())}</li>"
                for li in block.split("\n") if li.strip()) + "</ul>")
        else:
            out.append("<p>" + html.escape(block).replace("\n", "<br>") + "</p>")
    return "\n".join(out)


def banner_page() -> str:
    return ("<!doctype html><html lang=en><head><meta charset=utf-8>"
            "<meta name=viewport content='width=device-width,initial-scale=1'>"
            "<title>The Charter</title><style>"
            "body{font:17px/1.6 Georgia,serif;max-width:46rem;margin:2rem auto;"
            "padding:0 1rem;background:#f6f1e7;color:#2b2419}"
            "h2{font-size:1.2rem;margin-top:2rem}hr{border:0;border-top:1px solid #c9bda5}"
            ".notice{font:16px system-ui,sans-serif;border:2px solid #8a3b2a;"
            "padding:1rem;margin:2rem 0;background:#fff}"
            "</style></head><body>"
            + as_html()
            + f"<div class=notice><strong>{html.escape(NOT_AUTHORIZED)}</strong></div>"
            "</body></html>")
