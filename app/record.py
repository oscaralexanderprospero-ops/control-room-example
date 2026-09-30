"""The one record: the Google Sheet "Example Record".

The Sheet is the record. The app keeps a copy of every tab in
data/record_cache.json so the dashboard still opens when Google is
unreachable, and queues writes made offline in data/pending_writes.jsonl,
sending them as soon as it can. The app never deletes a row: things are
marked done, superseded or decided instead.
"""
import json
import threading
import time

from . import google_auth, paths, schema
from .ward import actionlog

SETTINGS = paths.DATA / "settings.json"
CACHE = paths.DATA / "record_cache.json"
PENDING = paths.DATA / "pending_writes.jsonl"
_lock = threading.RLock()
_state = {"tabs": {}, "pulled_at": None, "source": "none", "error": None}


# ------------------------------------------------------------------ settings
def settings() -> dict:
    if SETTINGS.exists():
        return json.loads(SETTINGS.read_text(encoding="utf-8"))
    return {}


def save_settings(**kv) -> None:
    s = settings()
    s.update(kv)
    SETTINGS.write_text(json.dumps(s, indent=2), encoding="utf-8")


def sheet_id() -> str | None:
    return settings().get("sheet_id")


def sheet_url() -> str | None:
    sid = sheet_id()
    return f"https://docs.google.com/spreadsheets/d/{sid}/edit" if sid else None


# ------------------------------------------------------------------ cache
def _load_cache() -> None:
    if CACHE.exists() and not _state["tabs"]:
        d = json.loads(CACHE.read_text(encoding="utf-8"))
        _state.update(tabs=d.get("tabs", {}), pulled_at=d.get("pulled_at"),
                      source=d.get("source", "laptop copy"))


def _save_cache() -> None:
    CACHE.write_text(json.dumps({"tabs": _state["tabs"],
                                 "pulled_at": _state["pulled_at"],
                                 "source": _state["source"]},
                                ensure_ascii=False), encoding="utf-8")


def status() -> dict:
    _load_cache()
    pending = 0
    if PENDING.exists():
        pending = sum(1 for ln in PENDING.read_text(encoding="utf-8").splitlines() if ln.strip())
    return {"connected": google_auth.connected() and bool(sheet_id()),
            "sheet_url": sheet_url(), "pulled_at": _state["pulled_at"],
            "source": _state["source"], "error": _state["error"],
            "pending": pending}


# ------------------------------------------------------------------ reading
def pull(force: bool = False) -> None:
    """Refresh the copy from the Sheet (at most once a minute unless forced)."""
    with _lock:
        _load_cache()
        if not force and _state["pulled_at"] and \
                time.time() - _state.get("_t", 0) < 60:
            return
        if not (sheet_id() and google_auth.connected()):
            return
        try:
            flush_pending()
            ranges = [f"'{t}'!A1:Z2000" for t in schema.TABS]
            res = google_auth.sheets().spreadsheets().values().batchGet(
                spreadsheetId=sheet_id(), ranges=ranges,
                valueRenderOption="FORMATTED_VALUE").execute()
            tabs = {}
            for tab, vr in zip(schema.TABS, res.get("valueRanges", [])):
                tabs[tab] = vr.get("values", [])
            _state.update(tabs=tabs, source="Google Sheet", error=None,
                          pulled_at=actionlog.now_central(), _t=time.time())
            _save_cache()
        except Exception as e:  # noqa: BLE001 - fall back to the laptop copy
            _state["error"] = str(e)[:300]


def raw(tab: str) -> list[list[str]]:
    _load_cache()
    return _state["tabs"].get(tab, [])


def rows(tab: str) -> list[dict]:
    """Rows of a tab as dicts keyed by header. Duty and Pacing are special."""
    data = raw(tab)
    if not data:
        return []
    if tab == "Duty":
        return duty_history()
    headers = _headers(tab)
    missing = [h for h in schema.TABS.get(tab, []) if h not in headers]
    out = []
    for i, r in enumerate(data[1:], start=2):
        if not any(c.strip() for c in r if isinstance(c, str)):
            continue
        d = {h: (r[j] if j < len(r) else "") for j, h in enumerate(headers) if h}
        # a column renamed or removed in the Sheet reads as blank, never breaks a screen
        for h in missing:
            d[h] = ""
        d["_row"] = i
        out.append(d)
    return out


def duty() -> dict:
    data = raw("Duty")
    def cell(r):
        return data[r][1] if len(data) > r and len(data[r]) > 1 else ""
    def meta(r, c):
        return data[r][c] if len(data) > r and len(data[r]) > c else ""
    return {"passes": cell(1), "passes_since": meta(1, 2),
            "passes_by": meta(1, 3), "review": cell(2),
            "review_since": meta(2, 2), "review_by": meta(2, 3)}


def duty_history() -> list[dict]:
    data = raw("Duty")
    hr = schema.DUTY_HISTORY_HEADER_ROW - 1
    if len(data) <= hr:
        return []
    heads = schema.DUTY_HISTORY_HEADERS
    out = []
    for r in data[hr + 1:]:
        if any(r):
            out.append({h: (r[j] if j < len(r) else "") for j, h in enumerate(heads)})
    return out


# ------------------------------------------------------------------ writing
def _queue(op: dict) -> None:
    with open(PENDING, "a", encoding="utf-8") as f:
        f.write(json.dumps(op, ensure_ascii=False) + "\n")


def _apply(op: dict) -> None:
    api = google_auth.sheets().spreadsheets().values()
    if op["op"] == "append":
        # "at" names the header row of the table to append under (default A1)
        api.append(spreadsheetId=sheet_id(), range=f"'{op['tab']}'!{op.get('at', 'A1')}",
                   valueInputOption="RAW",
                   insertDataOption="INSERT_ROWS",
                   body={"values": [op["row"]]}).execute()
    elif op["op"] == "update":
        api.update(spreadsheetId=sheet_id(), range=f"'{op['tab']}'!{op['a1']}",
                   valueInputOption="RAW",
                   body={"values": op["values"]}).execute()


def flush_pending() -> None:
    if not PENDING.exists() or not (sheet_id() and google_auth.connected()):
        return
    ops = [json.loads(ln) for ln in PENDING.read_text(encoding="utf-8").splitlines() if ln.strip()]
    done = 0
    for op in ops:
        try:
            _apply(op)
            done += 1
        except Exception:  # noqa: BLE001 - keep the rest for next time
            break
    rest = ops[done:]
    PENDING.write_text("".join(json.dumps(o, ensure_ascii=False) + "\n" for o in rest),
                       encoding="utf-8")


def _write(op: dict) -> None:
    with _lock:
        _load_cache()
        # update the laptop copy first so the screen shows it at once
        tab =_state["tabs"].setdefault(op["tab"], [schema.TABS.get(op["tab"], [])])
        if op["op"] == "append":
            tab.append([str(v) for v in op["row"]])
        elif op["op"] == "update":
            r, c = _a1_to_rc(op["a1"])
            for i, vals in enumerate(op["values"]):
                while len(tab) <= r + i:
                    tab.append([])
                row = tab[r + i]
                for j, v in enumerate(vals):
                    while len(row) <= c + j:
                        row.append("")
                    row[c + j] = str(v)
        _save_cache()
        if sheet_id() and google_auth.connected():
            try:
                flush_pending()
                _apply(op)
                return
            except Exception as e:  # noqa: BLE001
                _state["error"] = str(e)[:300]
        _queue(op)


def _a1_to_rc(a1: str) -> tuple[int, int]:
    a1 = a1.split(":")[0]
    col = 0
    i = 0
    while i < len(a1) and a1[i].isalpha():
        col = col * 26 + (ord(a1[i].upper()) - 64)
        i += 1
    return int(a1[i:]) - 1, col - 1


def _col(n: int) -> str:
    s = ""
    n += 1
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _headers(tab: str) -> list[str]:
    """Row 1 of a tab as the Sheet has it (stray spaces trimmed), or the
    schema's headers if the tab is empty."""
    data = raw(tab)
    return [str(h).strip() for h in data[0]] if data else list(schema.TABS[tab])


def append(tab: str, values: dict) -> list:
    row = [values.get(h, "") for h in _headers(tab)]
    _write({"op": "append", "tab": tab, "row": row})
    return row


def set_cell(tab: str, row_number: int, header: str, value) -> None:
    col = _headers(tab).index(header)
    _write({"op": "update", "tab": tab, "a1": f"{_col(col)}{row_number}",
            "values": [[value]]})


def find(tab: str, key_header: str, key: str) -> dict | None:
    for r in rows(tab):
        if r.get(key_header) == key:
            return r
    return None


def next_id(tab: str, prefix: str, key: str = "ID") -> str:
    """Next ID for a prefix in one tab. Reads both padded and unpadded
    numbers (A-01, A-045, S-1), so the new ID never repeats one in use."""
    n = 0
    for r in rows(tab):
        v = str(r.get(key, "")).strip()
        if v.startswith(prefix):
            try:
                n = max(n, int(v[len(prefix):]))
            except ValueError:
                pass
    return f"{prefix}{n + 1:03d}"


def set_duty(which: str, to: str, by: str, reason: str) -> None:
    d = duty()
    cell_row = 2 if which == "passes" else 3
    frm = d["passes"] if which == "passes" else d["review"]
    today = actionlog.now_central()
    _write({"op": "update", "tab": "Duty", "a1": f"B{cell_row}:E{cell_row}",
            "values": [[to, today[:10], by, reason]]})
    label = "Scheduled passes on duty" if which == "passes" else "Review duty"
    hist = [today, label, frm, to, by, reason]
    # Append under the history table (row 5), not the two live cells at the
    # top: from A1 the Sheet would treat rows 1-3 as the table and insert the
    # entry into the blank row above the history header.
    _write({"op": "append", "tab": "Duty", "row": hist,
            "at": f"A{schema.DUTY_HISTORY_HEADER_ROW}"})


def log_to_sheet(entry: dict) -> None:
    """Copy an action-log entry into the Log tab."""
    what = entry["what"]
    if entry.get("detail"):
        what += " (" + "; ".join(f"{k}: {v}" for k, v in entry["detail"].items()) + ")"
    _write({"op": "append", "tab": "Log",
            "row": [entry["when"], entry["who"], what]})


actionlog.on_entry(log_to_sheet)

