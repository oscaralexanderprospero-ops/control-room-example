"""Control Room: the local app. Listens on 127.0.0.1 only.

Screens are for Sam' browser (entered through the desktop shortcut).
/api/* is for Claude and Kimi, each with its own key. Anything else gets the
Address and a not-authorized notice, and is logged as Suspicious.
"""
import datetime
import functools
import json
import os
import subprocess
import threading

from flask import (Flask, abort, jsonify, make_response, redirect, render_template,
                   request, send_file, url_for)
from urllib.parse import quote_plus

from . import (approvals, backup, checks, files, fixes, google_auth, pacing, paths,
               posting, prep, public_page, record, runner, schema, seed)
from .ward import access, actionlog, charter, defender, guard, phone

PORT = int(os.environ.get("CONTROL_ROOM_PORT", "8765"))
app = Flask(__name__, template_folder="templates", static_folder="static")
app.config["JSON_SORT_KEYS"] = False
_charter_served: dict[str, str] = {}      # agent -> time the charter was served


# ------------------------------------------------------------------ the door
def _uninvited(reason: str):
    guard.record("door", request.remote_addr or "?",
                 f"{request.method} {request.path} ({reason}) "
                 f"UA={request.headers.get('User-Agent', '')[:120]}",
                 ["uninvited request"])
    resp = make_response(charter.banner_page(), 401)
    resp.headers["Content-Type"] = "text/html; charset=utf-8"
    return resp


def _phone_door():
    """His paired phone, through Tailscale serve (see ward/phone.py)."""
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return _uninvited("not from this laptop")
    if not phone.login_ok(request.headers.get("Tailscale-User-Login")):
        return _uninvited("phone address without his Tailscale login")
    if request.path.startswith("/static/"):
        return None
    if request.path == "/pair":
        return None           # the one-time code is checked there
    if request.path.startswith("/api/") or request.path == "/enter":
        return _uninvited("agent API or launch link from the phone")
    if not phone.is_phone(request.cookies.get(phone.COOKIE)):
        return _uninvited("phone not paired")
    request.who = "Sam"
    request.via_phone = True
    if request.method == "POST":
        origin = request.headers.get("Origin") or request.headers.get("Referer") or ""
        if origin:
            from urllib.parse import urlsplit
            o = urlsplit(origin)
            if o.scheme != phone.scheme() or o.netloc.lower() != phone.host():
                return _uninvited("cross-site form post")
    return None


PUBLIC_DEMO = os.environ.get("PUBLIC_DEMO") == "1"   # read-only, for a public demo site


@app.before_request
def door():
    if PUBLIC_DEMO:
        # Public demo: anyone may look at the pages; nothing can change and the
        # agent API and file routes stay closed.
        if request.method != "GET":
            return make_response("This is a read-only demo. Run it yourself to try the buttons.", 403)
        if request.path.startswith(("/api/", "/media-file", "/listing-photo", "/prep-demo")):
            return make_response("Not available in the public demo.", 403)
        request.who = "Visitor"
        return None
    if phone.host_ok(request.host):
        return _phone_door()
    if not access.host_ok(request.host):
        return _uninvited("non-local host header")
    if request.remote_addr not in ("127.0.0.1", "::1"):
        return _uninvited("not from this laptop")
    if request.path.startswith("/static/") or request.path == "/enter":
        return None
    if request.path.startswith("/api/"):
        agent = access.agent_for_key(request.headers.get("X-Agent-Key"))
        if not agent:
            return _uninvited("agent API without a valid key")
        request.who = agent
        return None
    if access.is_sam(request.cookies.get(access.COOKIE)):
        request.who = "Sam"
        if request.method == "POST":
            # forms and buttons must come from the app's own pages
            origin = request.headers.get("Origin") or request.headers.get("Referer") or ""
            if origin:
                # compare the whole host:port, so "127.0.0.1:8765.evil.com" is refused
                from urllib.parse import urlsplit
                o = urlsplit(origin)
                if o.scheme != "http" or o.netloc not in {f"{h}:{PORT}" for h in access.LOCAL_HOSTS}:
                    return _uninvited("cross-site form post")
        return None
    return _uninvited("no session")


@app.route("/enter")
def enter():
    if request.args.get("t") != access.launch_key():
        return _uninvited("wrong launch key")
    resp = redirect(url_for("plan_view"))
    resp.set_cookie(access.COOKIE, access.session_value(), httponly=True,
                    samesite="Strict")
    actionlog.log("Sam", "Opened the Control Room.")
    return resp


# ------------------------------------------------------------------ helpers
def _ctx(**kw):
    record.pull()
    st = record.status()
    blocked, inbox = _blocked(), _inbox()
    if "now_task" not in kw:
        try:
            from . import plan
            n = plan.now_item(_plan_auto(blocked, inbox))
            kw["now_task"], kw["now_urgent"] = (n["what"], bool(n.get("urgent"))) if n else ("", False)
        except Exception:  # noqa: BLE001 - never break a page over the Now line
            kw["now_task"], kw["now_urgent"] = "", False
    return dict(rec=st, defender=defender.status(), duty=record.duty(),
                blocked_count=len(blocked), sus_count=_recent_suspicious(),
                inbox_count=len(inbox), biz_due=_biz_due(),
                # everything he has told the team that isn't finished yet
                open_requests=sum(1 for r in record.rows("Requests")
                                  if r.get("Status") in ("open", "working", "needs Sam")),
                today_str=pacing.now().strftime("%A %d %B %Y, %I:%M %p").replace(" 0", " "),
                google_client=google_auth.has_client(), **kw)


def _recent_suspicious(days: int = 7) -> int:
    """The Ward badge counts only the last week, so it can go back to zero."""
    cutoff = (datetime.datetime.now() - datetime.timedelta(days=days)).strftime("%Y-%m-%d")
    return sum(1 for s in guard.recent(500) if s.get("when", "")[:10] >= cutoff)


def _biz_due() -> int:
    try:
        from . import business
        c = business.counts()
        return c["to_ship"] + c["messages"] + c["reviews"]
    except Exception:  # noqa: BLE001 - never break a page over a count
        return 0


def _stale(d: str) -> bool:
    """True if a date string (YYYY-MM-DD or '27 Sep 2026') is over 7 days old."""
    if not d:
        return False
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%Y-%m-%d %H:%M"):
        try:
            dt = datetime.datetime.strptime(d.strip()[:len(datetime.date.today().strftime(fmt))], fmt).date()
            return (datetime.date.today() - dt).days > 7
        except ValueError:
            continue
    return False


app.jinja_env.globals["stale"] = _stale


def _day_of(d: str) -> datetime.date | None:
    for fmt in ("%Y-%m-%d", "%d %b %Y", "%Y-%m-%d %H:%M"):
        try:
            return datetime.datetime.strptime((d or "").strip()[:len(datetime.date.today().strftime(fmt))], fmt).date()
        except ValueError:
            continue
    return None


def _before_today(d: str) -> bool:
    """True if a date string is from an earlier day (so a note saying 'today' is old news)."""
    day = _day_of(d)
    return bool(day) and day < pacing.now().date()


app.jinja_env.globals["before_today"] = _before_today

DONE_WORDS = ("shipped", "answered", "done", "closed", "delivered", "cancel", "refund", "replied", "complete")


def _due_today() -> list[dict]:
    """Everything due today or overdue, worked out fresh from the dates each time."""
    today = pacing.now().date()
    out = []

    def add(what, day, link, kind):
        if day and day <= today:
            out.append({"what": what, "when": "overdue since " + day.strftime("%a %d %b") if day < today else "today",
                        "overdue": day < today, "link": link, "kind": kind})
    for r in record.rows("Orders"):
        if not any(w in (r.get("Status") or "").lower() for w in DONE_WORDS):
            verb = "Ship" if r.get("Kind") == "Order" else "Answer"
            add(f"{verb}: {r.get('Item', '')[:70]} ({r.get('Customer', '')})", _day_of(r.get("Ship or answer by", "")),
                "/business", "Business")
    for r in record.rows("Custom Orders"):
        if not any(w in (r.get("Status") or "").lower() for w in DONE_WORDS):
            add(f"Custom: {r.get('What', '')[:70]} ({r.get('Customer', '')})", _day_of(r.get("Due", "")), "/business", "Business")
    for r in record.rows("Writing"):
        st = (r.get("Status") or "").lower()
        if r.get("Kind") == "prompt" and not r.get("His words (verbatim)") and not st.startswith("deleted"):
            add(f"Question {r['ID']}: {r.get('Item', '')[:70]}", _day_of(r.get("Due", "")), f"/writing#{r['ID']}", "Writing")
        elif r.get("Kind") == "draft" and st.startswith("waiting"):
            add(f"Draft {r['ID']}: {r.get('Item', '')[:70]}", _day_of(r.get("Due", "")), f"/writing#{r['ID']}", "Writing")
    now = pacing.now()
    due = held = 0
    for j in posting._jobs():
        if j["status"] in ("waiting", "handed to agent", "claimed"):
            if j.get("held"):
                held += 1
            elif datetime.datetime.fromisoformat(j["not_before"]) <= now:
                due += 1
    if due:
        out.append({"what": f"{due} post{'s' if due > 1 else ''} due to go out now", "when": "today", "overdue": False,
                    "link": "/post", "kind": "Posts"})
    if held:
        out.append({"what": f"{held} post{'s' if held > 1 else ''} held by pacing (a time to check)", "when": "today",
                    "overdue": False, "link": "/post", "kind": "Posts"})
    from . import etsy_changes
    waiting = [c for c in etsy_changes.pending() if "Save" in c["state"]]
    if waiting:
        out.append({"what": f"{len(waiting)} Etsy edit screen{'s' if len(waiting) > 1 else ''} filled in and waiting for your Save",
                    "when": "today", "overdue": False, "link": "/shop#etsy", "kind": "Etsy"})
    out.sort(key=lambda x: (not x["overdue"], x["kind"]))
    return out


def _blocked():
    """Everything waiting on Sam, except drafts (those live in the Inbox)."""
    out = []
    for a in record.rows("Approvals"):
        if a.get("Status", "").lower() != "waiting":
            continue
        if approvals.load(a["ID"]):
            continue
        a["buttons"] = fixes.buttons(a)
        out.append(a)
    return out


def _inbox():
    return [a for a in record.rows("Approvals")
            if approvals.load(a["ID"]) and a.get("Status", "") in ("waiting", "with ChatGPT")]


def _plan_auto(blocked=None, inbox=None) -> list[dict]:
    """What the app already knows is waiting on him, for My day. Big piles
    (Inbox, Blocked on you) are one item each, never a wall of them."""
    from . import stalls
    st = record.status()
    try:
        out = stalls.items(posting._jobs(), st["connected"], st.get("error") or "", st["pending"],
                           bool(defender.status().get("ok")))
    except Exception:  # noqa: BLE001 - a broken check must never hide the rest of his day
        out = []
    # an overdue order or customer message is urgent (Star Seller: messages within 24 hours)
    out += [{"what": d["what"], "link": d["link"], "kind": d["kind"], "overdue": d["overdue"], "soft": False,
             "urgent": d["overdue"] and d["kind"] == "Business", "rank": 1}
            for d in _due_today()]
    inbox = _inbox() if inbox is None else inbox
    blocked = _blocked() if blocked is None else blocked
    if inbox:
        out.append({"what": f"Look at the {len(inbox)} draft{'s' if len(inbox) > 1 else ''} in your Inbox",
                    "link": "/inbox", "kind": "Inbox", "overdue": False, "soft": True})
    if blocked:
        out.append({"what": f"Blocked on you: {len(blocked)} thing{'s' if len(blocked) > 1 else ''} waiting. "
                            "Clear whatever you can", "link": "/blocked", "kind": "Blocked", "overdue": False,
                    "soft": True})
    for r in record.rows("Requests"):
        if r.get("Status") == "needs Sam":
            out.append({"what": f"The team needs you on: {(r.get('His words (verbatim)') or '')[:90]}",
                        "link": "/requests", "kind": "Team", "overdue": False, "soft": False})
    from . import marketing
    late = [r for k in ("Season", "Sale", "Campaign") for r in marketing.view()["by"][k] if r.get("prep_late")]
    if late:
        late.sort(key=lambda r: r["start_d"])
        names = ", ".join(r.get("Title", "") for r in late[:3]) + (" and more" if len(late) > 3 else "")
        out.append({"what": f"Get ready for what's coming up: {names}", "link": "/marketing",
                    "kind": "Marketing", "overdue": False, "soft": True})
    return out


def sam_only(fn):
    @functools.wraps(fn)
    def wrap(*a, **k):
        if getattr(request, "who", None) != "Sam":
            abort(403)
        return fn(*a, **k)
    return wrap


# ------------------------------------------------------------------ screens
@app.route("/")
def today():
    day = pacing.now().strftime("%Y-%m-%d")
    posts_today = [p for p in record.rows("Posts") if p.get("Date (Central)") == day]
    posts_today.sort(key=lambda p: (p.get("Time (Central)") or "99").zfill(5))   # 9:05 before 10:00
    queue = [q for q in record.rows("Queue")
             if q.get("Status", "").lower() not in ("done", "superseded", "posted")]
    from . import boards
    return render_template("today.html", **_ctx(
        page="today", queue=queue, posts=posts_today, pace=pacing.today(),
        calendar=boards.calendar(), due=_due_today()))


@app.route("/plan")
def plan_view():
    from . import plan
    v = plan.view(_plan_auto())
    return render_template("plan.html", **_ctx(page="plan", now_task="", p=v))


@app.post("/act/plan")
@sam_only
def act_plan():
    from . import plan
    op = request.form.get("op", "")
    if op == "add":
        day = request.form.get("day", "")
        if day not in ("", plan.today(), (pacing.now().date() + datetime.timedelta(days=1)).isoformat()):
            abort(400)
        plan.add(request.form.get("text", ""), request.form.get("time", "")[:5], day)
        return redirect(url_for("plan_view") + "?done=added#add")
    if op == "ask":
        # his one click hands a stuck thing to Claude, then moves it out of his way
        what, detail = request.form.get("what", "")[:300], request.form.get("ask", "")[:2000]
        sid = record.next_id("Requests", "S-")
        record.append("Requests", {
            "ID": sid, "When (Central)": actionlog.now_central(),
            "His words (verbatim)": (f"From My day, he pressed 'Ask the team to fix it' on: {what}. Details the "
                                     f"app found: {detail} Find out why and fix it, or tell him in one plain line "
                                     f"the one thing he needs to do."),
            "About": "operations", "For": "Claude", "Status": "open", "Result": "", "Updated": ""})
        actionlog.log("Sam", f"My day: asked the team to fix \"{what[:80]}\" ({sid}).")
        plan.mark(request.form.get("key", "")[:20], "later", what)
        return redirect(url_for("plan_view") + "?done=asked#now")
    plan.mark(request.form.get("key", "")[:20], op, request.form.get("what", "")[:300])
    return redirect(url_for("plan_view") + "#now")


@app.route("/shop")
def shop():
    ls = record.rows("Listings")
    from . import etsy_changes
    return render_template("shop.html", **_ctx(
        etsy_pending=etsy_changes.pending(),
        page="shop", live=[x for x in ls if x.get("Status") == "live"],
        drafts=[x for x in ls if x.get("Status") == "draft"],
        other=[x for x in ls if x.get("Status") not in ("live", "draft")],
        editable=LISTING_EDITABLE, statuses=LISTING_STATUSES))


@app.post("/act/etsy-saved")
@sam_only
def act_etsy_saved():
    """His 'I've saved it on Etsy' for a change that was waiting on his Save."""
    from . import etsy_changes
    etsy_changes.mark(request.form.get("source", ""), request.form.get("id", "")[:40],
                      request.form.get("platform", "Etsy")[:20], "saved", "Sam pressed Save on Etsy", "Sam")
    return redirect(url_for("shop") + "?done=etsy-saved#etsy")


LISTING_EDITABLE = ("Piece", "Price", "Status", "Notes")
LISTING_STATUSES = ("live", "draft", "sold", "deactivated", "expired", "not listed", "unknown")


@app.post("/act/listing-edit")
@sam_only
def act_listing_edit():
    """His Save on the Listings page. Rows are found by listing ID, or for a
    row with no ID yet, by its row number with the piece name double-checked."""
    lid, row_no, piece = request.form.get("id", ""), request.form.get("row", ""), request.form.get("was", "")
    r = record.find("Listings", "Etsy listing ID", lid) if lid else next(
        (x for x in record.rows("Listings") if str(x["_row"]) == row_no and x.get("Piece") == piece), None)
    if not r:
        abort(400)
    changed = []
    for f in LISTING_EDITABLE:
        v = request.form.get(f, "").strip()[:2000]
        if f == "Status" and v not in LISTING_STATUSES and v != r.get("Status", ""):
            continue
        if v != r.get(f, ""):
            record.set_cell("Listings", r["_row"], f, v)
            changed.append(f"{f}: {r.get(f, '') or '(blank)'} -> {v or '(blank)'}")
    if changed:
        actionlog.log("Sam", f"Listing {lid or r.get('Piece', '')}: " + "; ".join(changed))
    return redirect(url_for("shop") + f"?done={'saved' if changed else 'nochange'}#L{r['_row']}")


@app.route("/duty")
def duty():
    tasks = record.rows("Tasks")
    runs = _pass_runs()
    return render_template("duty.html", **_ctx(
        page="duty", agents=schema.AGENTS, history=record.duty_history(),
        tasks=tasks, runs=runs, passes_choices=schema.PASSES_CHOICES,
        review_choices=schema.REVIEW_CHOICES,
        charter_served=dict(_charter_served)))


@app.route("/blocked")
def blocked():
    return render_template("blocked.html", **_ctx(page="blocked", items=_blocked()))


@app.route("/reviews")
def reviews():
    return render_template("reviews.html", **_ctx(
        page="reviews", reviews=list(reversed(record.rows("Reviews")))))


@app.route("/files")
def files_view():
    return render_template("files.html", **_ctx(
        page="files", batches=files.batches(), plan=files.tidy_plan(),
        to_delete=files.to_delete_summary(), backup=backup.status(),
        dupes=_DUPES.get("groups"), dupes_at=_DUPES.get("at")))


@app.route("/ward")
def ward():
    return render_template("ward.html", **_ctx(
        page="ward", suspicious=guard.recent(100), actions=actionlog.recent(60),
        address_source=charter.source(), phone=phone.status(),
        via_phone=getattr(request, "via_phone", False)))


@app.post("/act/phone-pair")
@sam_only
def act_phone_pair():
    """Show a one-time QR on the laptop screen. Never from the phone itself."""
    if getattr(request, "via_phone", False):
        abort(403)
    url = phone.start_pairing()
    if not url:
        return redirect(url_for("ward") + "#phone")
    actionlog.log("Sam", f"Phone: showed a one-time pairing code ({phone.PAIR_MINUTES} minutes).")
    return render_template("phone_pair.html", **_ctx(page="ward", qr=phone.qr_svg(url),
                                                     minutes=phone.PAIR_MINUTES))


@app.post("/act/phone-forget")
@sam_only
def act_phone_forget():
    phone.forget()
    actionlog.log("Sam", "Phone: forgot every linked phone and closed the phone door.")
    return redirect(url_for("ward") + "#phone")


@app.route("/pair")
def pair():
    """Reached only through the phone door (his Tailscale login already checked)."""
    if not phone.host_ok(request.host):
        abort(404)
    token = phone.pair(request.args.get("c", ""), request.headers.get("User-Agent", ""))
    if not token:
        return _uninvited("expired or used pairing code")
    actionlog.log("Sam", "Phone: a phone was linked to the Control Room.")
    resp = redirect("/")
    resp.set_cookie(phone.COOKIE, token, max_age=phone.COOKIE_DAYS * 86400,
                    secure=phone.scheme() == "https",
                    # Lax, not Strict: the link is opened from the camera app, and a
                    # Strict cookie is held back on that first hop. Cross-site posts are
                    # still refused by the Origin check in _phone_door.
                    httponly=True, samesite="Lax")
    return resp


@app.route("/address")
def address():
    return render_template("address.html", **_ctx(page="ward", body=charter.as_html(),
                                                   address_source=charter.source()))


@app.route("/public")
def public_view():
    info = public_page.build()
    return render_template("public.html", **_ctx(page="public", info=info,
                                                  rows=record.rows("Public")))


@app.route("/public/status.html")
def public_file():
    return send_file(public_page.OUT)


# ------------------------------------------------------------------ Sam' buttons
def _back(msg: str = "", page: str = "today"):
    return redirect(url_for(page) + ("?done=" + msg if msg else ""))


@app.post("/act/duty")
@sam_only
def act_duty():
    which = request.form["which"]
    to = request.form["to"]
    choices = schema.PASSES_CHOICES if which == "passes" else schema.REVIEW_CHOICES
    if which not in ("passes", "review") or to not in choices:
        abort(400)
    reason = request.form.get("reason", "").strip()[:300] or "Switched in the Control Room."
    record.set_duty(which, to, "Sam", reason)
    label = "Scheduled passes" if which == "passes" else "Review duty"
    actionlog.log("Sam", f"{label} switched to {to}.", reason=reason)
    return _back("duty", "duty")


@app.post("/act/chatgpt")
@sam_only
def act_chatgpt():
    note = request.form.get("note", "")
    link = request.form.get("link", "").strip()
    about = request.form.get("about", "").strip()[:200]
    if not note.strip():
        return _back("empty", "reviews")
    flags = guard.check("Paste from ChatGPT", "ChatGPT", note)
    rid = record.next_id("Reviews", "R-")
    record.append("Reviews", {
        "ID": rid, "Date": actionlog.now_central()[:10], "By": "ChatGPT",
        "About": about, "Note (verbatim)": note, "Chat link": link,
        "Status": "PROPOSED" + (" (flagged: " + ", ".join(flags) + ")" if flags else ""),
        "Sam decided": "", "Decided on": ""})
    actionlog.log("Sam", f"Pasted a ChatGPT note into Reviews as {rid}.",
                  link=link or "none")
    return _back("chatgpt", "reviews")


@app.post("/act/review-decide")
@sam_only
def act_review_decide():
    rid = request.form["id"]
    decision = request.form["decision"]
    if decision not in ("yes", "no", "later"):
        abort(400)
    r = record.find("Reviews", "ID", rid)
    if not r:
        abort(404)
    words = {"yes": "Yes, do it", "no": "No", "later": "Later"}[decision]
    record.set_cell("Reviews", r["_row"], "Sam decided", words)
    record.set_cell("Reviews", r["_row"], "Decided on", actionlog.now_central())
    actionlog.log("Sam", f"Decided review {rid}: {words}.")
    return _back("decided", "reviews")


@app.post("/act/tidy")
@sam_only
def act_tidy():
    res = files.tidy_run("Sam")
    return _back(f"tidy-{res['copied']}", "files_view")


_DUPES: dict = {}


@app.post("/act/dupes-scan")
@sam_only
def act_dupes_scan():
    _DUPES.update(groups=files.find_duplicates(), at=actionlog.now_central())
    actionlog.log("Sam", f"Checked for duplicates: {len(_DUPES['groups'])} sets found.")
    return _back("scanned", "files_view")


@app.post("/act/dupes-move")
@sam_only
def act_dupes_move():
    res = files.move_duplicates("Sam")
    _DUPES.clear()
    return _back(f"moved-{len(res['moved'])}", "files_view")


@app.post("/act/empty-to-delete")
@sam_only
def act_empty():
    if request.form.get("confirm") != "yes":
        abort(400)
    files.empty_to_delete("Sam")
    return _back("emptied", "files_view")


@app.post("/act/backup")
@sam_only
def act_backup():
    threading.Thread(target=backup.run, args=("Sam",), daemon=True).start()
    return _back("backup-started", "files_view")


@app.post("/act/refresh")
@sam_only
def act_refresh():
    record.pull(force=True)
    return redirect(request.referrer or url_for("today"))


@app.post("/act/google-connect")
@sam_only
def act_google_connect():
    google_auth.adopt_downloaded_client()
    if not google_auth.has_client():
        return _back("no-client")
    threading.Thread(target=lambda: google_auth.credentials(interactive=True),
                     daemon=True).start()
    actionlog.log("Sam", "Started Google sign-in for the Control Room.")
    return _back("google-started")


@app.post("/act/show-file")
@sam_only
def act_show_file():
    p = request.form["path"]
    from .ward import fences
    try:
        fp = fences.check_showable(p)
    except fences.Fenced:
        abort(403)
    if not fp.exists():
        abort(404)
    subprocess.Popen(["explorer", "/select,", str(fp)])
    actionlog.log("Sam", f"Show file: {fp.name}")
    return ("", 204)


# ------------------------------------------------------------------ Stage 2: inbox
@app.route("/inbox")
def inbox():
    items = [approvals.view(a["ID"]) | {"row": a} for a in _inbox()]
    return render_template("inbox.html", **_ctx(page="inbox", items=items, limits=checks.LIMITS))


@app.post("/act/approve")
@sam_only
def act_approve():
    approvals.approve(request.form["id"], request.form.get("platform") or None)
    return _back("approved", "inbox")


@app.post("/act/bulk")
@sam_only
def act_bulk():
    """One click for everything he ticked: the same action each item's own
    button does, done for each selected item in turn."""
    from . import fixes, listing_updates, marketing, writing
    op = request.form.get("op", "")
    ids = [i[:40] for i in request.form.getlist("ids")][:200]
    note = request.form.get("note", "").strip()[:1000]
    n = 0
    okids = []
    for i in ids:
        n0 = n
        if op == "approve":
            if approvals.load(i):
                approvals.approve(i, None); n += 1
        elif op == "send-back":
            if approvals.load(i):
                approvals.send_back(i, note); n += 1
        elif op == "chatgpt":
            if approvals.load(i):
                approvals.ask_chatgpt(i, note); n += 1
        elif op == "post":
            if approvals.load(i):
                posting.plan(i, "Sam"); n += 1
        elif op in ("hand", "done"):
            row = record.find("Approvals", "ID", i)
            btns = fixes.buttons(row) if row else []
            if op == "hand":
                b = next((b for b in btns if b[1] == "hand"), None)
                if b:
                    fixes.hand(i, b[2][:1000]); n += 1
            else:
                b = next((b for b in btns if b[1] == "answer" and b[2].lower() == "done"), None)
                if b:
                    fixes.decide(i, "Done"); n += 1
        elif op == "capture-approve":
            writing.approve_capture(i); n += 1
        elif op == "listing-handover":
            listing_updates.save(i, {}, "", True); n += 1
        elif op == "marketing-hand":
            marketing.hand(i); n += 1
        else:
            abort(400)
        if n > n0:
            okids.append(i)
    if op == "post" and n:
        threading.Thread(target=posting.run_due, daemon=True).start()
    actionlog.log("Sam", f"Did '{op}' for {n} selected item(s): {', '.join(ids[:20])}")
    if request.headers.get("X-Requested-With") == "fetch":
        return jsonify(ok=True, n=n, ids=okids)
    back = (request.referrer or url_for("today")).split("?")[0].split("#")[0]
    return redirect(back + f"?done=bulk&n={n}")


@app.post("/act/cut")
@sam_only
def act_cut():
    try:
        index = int(request.form["index"])
    except ValueError:
        abort(400)
    approvals.cut(request.form["id"], request.form["platform"], index)
    return redirect(url_for("inbox") + "#" + request.form["id"])


@app.post("/act/ask-chatgpt")
@sam_only
def act_ask_chatgpt():
    approvals.ask_chatgpt(request.form["id"], request.form.get("note", "")[:1000])
    return _back("chatgpt", "inbox")


@app.get("/chatgpt-packet/<aid>")
def chatgpt_packet(aid):
    if getattr(request, "who", None) != "Sam":
        abort(403)
    if not approvals.load(aid):
        abort(404)
    resp = make_response(approvals.chatgpt_packet(aid))
    resp.headers["Content-Type"] = "text/plain; charset=utf-8"
    return resp


@app.post("/act/send-back")
@sam_only
def act_send_back():
    approvals.send_back(request.form["id"], request.form.get("reason", "")[:1000])
    return _back("sent-back", "inbox")


# ------------------------------------------------------------------ fixes
@app.post("/act/fix")
@sam_only
def act_fix():
    aid, kind, value = request.form["id"], request.form["kind"], request.form["value"]
    ajax = request.headers.get("X-Requested-With") == "fetch"
    row = record.find("Approvals", "ID", aid)
    if row and row.get("Status", "").lower() != "waiting":
        # a repeat click on something already answered: do nothing twice
        if ajax:
            return jsonify(ok=True, already=True, message="Already recorded: " + (row.get("Decision") or row.get("Status", "")))
        return redirect(request.referrer or url_for("blocked"))
    said = value
    if kind == "answer":
        fixes.decide(aid, value[:500])
    elif kind == "hand":
        sid = fixes.hand(aid, value[:1000])
        said = f"Handed to {record.duty().get('passes') or 'Claude'} ({sid})"
    elif kind == "app":
        said = fixes.app_fix(aid, value)
    elif kind == "typed":
        text = request.form.get("text", "").strip()
        if not text:
            if ajax:
                return jsonify(ok=False, message="Type your answer first.")
            return redirect(request.referrer or url_for("blocked"))
        fixes.decide(aid, text[:1000])
        said = text[:120]
        src = (row or {}).get("Source", "")
        if src.startswith("Team table T-"):
            team_post(src.split()[-1], "", "Sam", text)   # answer goes back to the team
    if ajax:
        return jsonify(ok=True, message="Recorded: " + said)
    return redirect(request.referrer or url_for("blocked"))


@app.post("/act/still-true")
@sam_only
def act_still_true():
    fixes.still_true(request.form["tab"], request.form["key_header"], request.form["key"])
    return redirect(request.referrer or url_for("today"))


@app.post("/act/recheck")
@sam_only
def act_recheck():
    fixes.recheck_platforms("Sam")
    return redirect(request.referrer or url_for("today"))


@app.post("/act/prep-now")
@sam_only
def act_prep_now():
    threading.Thread(target=prep.prep_queue, daemon=True).start()
    return _back("prep-started", "files_view")


@app.route("/prep-demo/<name>")
def prep_demo_file(name):
    if getattr(request, "who", None) != "Sam" or "/" in name or "\\" in name:
        abort(403)
    from flask import send_from_directory   # refuses anything outside the folder
    return send_from_directory(paths.BATCHES / "_prep-demo", name)


# ------------------------------------------------------------------ Tell the team
@app.post("/act/tell")
@sam_only
def act_tell():
    words = request.form.get("words", "").strip()
    if not words:
        return redirect(request.referrer or url_for("today"))
    about = request.form.get("about", "other")[:30]
    to = request.form.get("for") or record.duty().get("passes") or "Claude"
    if to not in ("Claude", "Kimi", "ChatGPT"):
        abort(400)
    sid =record.next_id("Requests", "S-")
    record.append("Requests", {
        "ID": sid, "When (Central)": actionlog.now_central(), "His words (verbatim)": words,
        "About": about, "For": to, "Status": "open", "Result": "", "Updated": ""})
    actionlog.log("Sam", f"Told the team ({sid}, for {to}): {words[:200]}")
    from urllib.parse import quote
    return redirect((request.referrer or url_for("today")).split("?")[0] + "?done=told&to=" + quote(to))


@app.route("/requests")
def requests_view():
    return render_template("requests.html", **_ctx(
        page="requests", reqs=list(reversed(record.rows("Requests")))))


# ------------------------------------------------------------------ Stage 3: posting
@app.route("/post")
def post_board():
    return render_template("post.html", **_ctx(page="post", board=posting.board(),
                                                upload_today=sorted(p.name for p in paths.UPLOAD_TODAY.iterdir() if p.is_file())))


@app.post("/act/post-plan")
@sam_only
def act_post_plan():
    if not approvals.load(request.form["id"]):
        abort(404)
    posting.plan(request.form["id"], "Sam")
    threading.Thread(target=posting.run_due, daemon=True).start()
    return redirect(url_for("post_board") + "?done=planned")


@app.post("/act/manual-posted")
@sam_only
def act_manual_posted():
    url = request.form.get("url", "").strip()
    if not url.startswith("http"):
        return redirect(url_for("post_board") + "?done=need-link")
    try:
        posting.record_manual(request.form["id"], request.form["platform"], url[:500], "Sam")
    except ValueError:
        abort(404)
    return redirect(url_for("post_board") + "?done=recorded")


@app.post("/act/copy-file")
@sam_only
def act_copy_file():
    from .ward import fences
    try:
        ok = posting.copy_to_clipboard(request.form["path"])
    except fences.Fenced:
        abort(403)
    actionlog.log("Sam", "Copied a file to the clipboard for pasting into an upload box.")
    return ("", 204) if ok else ("", 500)


@app.post("/act/hand-now")
@sam_only
def act_hand_now():
    agent = request.form.get("agent") or record.duty().get("passes") or "Claude"
    if agent not in ("Claude", "Kimi"):
        abort(400)
    runner.queue_for(agent, request.form["job"][:80], request.form["what"][:4000])
    return redirect((request.referrer or url_for("requests_view")).split("?")[0] + "?done=handed")


# ------------------------------------------------------------------ Boards (Kimi's tabs)
def _fix_button(r):
    from markupsafe import Markup
    return Markup(
        '<form method="post" action="/act/board" style="display:inline">'
        f'<input type="hidden" name="op" value="still"><input type="hidden" name="id" value="{r["ID"]}">'
        '<button class="quiet" style="padding:0 .5rem">Still true</button></form>')


app.jinja_env.globals["fix"] = _fix_button


def _status_form(r):
    from markupsafe import Markup, escape
    from .marketing import STATUSES
    opts = "".join(f"<option {'selected' if s == r.get('Status') else ''}>{s}</option>" for s in STATUSES)
    return Markup(
        '<form method="post" action="/act/marketing" style="display:inline">'
        f'<input type="hidden" name="op" value="status"><input type="hidden" name="id" value="{escape(r["ID"])}">'
        f'<input type="hidden" name="kind" value="{escape(r.get("Kind", ""))}">'
        f'<select name="status" aria-label="Status">{opts}</select> <button class="quiet">Save</button></form>')


app.jinja_env.globals["status_form"] = _status_form


@app.route("/board/<name>")
def board_view(name):
    from . import boards
    if name not in boards.BOARDS or name.startswith("_"):
        abort(404)
    b = boards.BOARDS[name]
    widgets = [dict(w, rows=boards.rows(name, w["key"])) for w in b["widgets"]]
    return render_template("board.html", **_ctx(page="board-" + name, b=b, board=name,
                                                 widgets=widgets, calendar=boards.calendar()))


@app.post("/act/board")
@sam_only
def act_board():
    from . import boards
    op, bid = request.form["op"], request.form.get("id", "")
    if op != "add" and not record.find("Boards", "ID", bid):
        abort(404)        # a stale page: the item is not in the record
    if op == "toggle":
        boards.toggle(bid)
    elif op in ("forward", "back"):
        boards.move(bid, 1 if op == "forward" else -1)
    elif op == "archive":
        boards.archive(bid)
    elif op == "still":
        boards.still_true(bid)
    elif op == "set-detail":
        boards.set_value(bid, "Detail", request.form.get("value", "")[:500])
    elif op == "add":
        board, widget = request.form["board"], request.form["widget"]
        if board not in boards.BOARDS or \
                widget not in {w["key"] for w in boards.BOARDS[board]["widgets"]}:
            abort(400)
        boards.add(board, widget, request.form["title"][:300],
                   detail=request.form.get("detail", "")[:1000], stage=request.form.get("stage", "")[:40],
                   platform=request.form.get("platform", "")[:40], date=request.form.get("date", "")[:10])
    else:
        abort(400)
    return redirect((request.referrer or url_for("today")).split("#")[0])


# ------------------------------------------------------------------ Business
@app.route("/business")
def business_view():
    from . import business
    return render_template("business.html", **_ctx(page="business", **business.view()))


@app.post("/act/business")
@sam_only
def act_business():
    from . import business
    tab = request.form["tab"]
    if tab not in business.TABS:
        abort(400)
    op = request.form.get("op")
    if op == "add":
        business.add(tab, {f: request.form.get(f, "")[:5000] for f in business.TABS[tab]["fields"]})
    elif op == "status":
        try:
            business.update(tab, request.form["id"], business.STATUS_COL[tab], request.form["value"])
        except ValueError:
            abort(400)
    elif op == "hand":
        business.hand(tab, request.form["id"], request.form.get("what", "")[:2000] or "please handle")
    return redirect(url_for("business_view"))


@app.post("/api/business/<tab>")
def api_business(tab):
    """Agents report orders, messages, custom orders and reviews.
    JSON: {"fields": {...one of the tab's fields...}, "status": "...", "source": "..."}
    or {"id": "...", "field": "...", "value": "..."} to update one field."""
    _need_charter()
    from . import business
    name = {"orders": "Orders", "custom-orders": "Custom Orders", "reviews": "Customer Reviews"}.get(tab)
    if not name:
        abort(404)
    body = request.get_json(silent=True)
    if not isinstance(body, dict) or not isinstance(body.get("fields", {}), dict):
        return jsonify(error="send a JSON object; fields must be an object"), 400
    # unknown fields are refused, as on every other agent call
    extra = sorted(set(body) - {"fields", "status", "source", "id", "field", "value"}) + \
        sorted(set(body.get("fields") or {}) - set(business.TABS[name]["fields"]))
    if extra:
        guard.record("agent API", request.who, json.dumps(body)[:2000],
                     ["unexpected fields: " + ", ".join(extra)])
        return jsonify(error="unknown fields", fields=extra), 400
    texts = [str(v) for v in (body.get("fields") or {}).values()] + [str(body.get("value", ""))]
    flags = guard.check(f"agent API {name}", request.who, *texts)
    try:
        if body.get("id"):
            if not business.update(name, str(body["id"])[:20], str(body.get("field", ""))[:40],
                                   str(body.get("value", ""))[:5000], request.who):
                return jsonify(error="no such row"), 404
            return jsonify(ok=True, flagged=flags)
        fields = {k: str(v)[:5000] for k, v in (body.get("fields") or {}).items()}
        rid = business.add(name, dict(fields, status=str(body.get("status", ""))[:30]), request.who,
                           source=str(body.get("source", ""))[:300] or f"{request.who} via agent API")
        return jsonify(ok=True, id=rid, flagged=flags)
    except ValueError as e:
        return jsonify(error=f"not allowed: {e}"), 400


# ------------------------------------------------------------------ Listing photos
@app.route("/listing-photo/<lid>")
def listing_photo(lid):
    from . import photos
    if getattr(request, "who", None) != "Sam" or not lid.isdigit():
        abort(403)
    f = photos.DIR / f"{lid}.jpg"
    if not f.exists():
        abort(404)
    return send_file(f, max_age=86400)


@app.post("/act/listing-photo")
@sam_only
def act_listing_photo():
    from . import photos
    lid = request.form["id"]
    up = request.files.get("photo")
    if lid.isdigit() and up:
        photos.save_upload(lid, up.read()[:15_000_000])
    return redirect(request.referrer or url_for("listing_updates_view"))


app.jinja_env.globals["has_photo"] = lambda lid: __import__("app.photos", fromlist=["has"]).has(str(lid))


# ------------------------------------------------------------------ Listings: needs updating
@app.route("/listings/updates")
def listing_updates_view():
    from . import listing_updates as lu
    rows = lu.all_rows()
    return render_template("listing_updates.html", **_ctx(
        page="shop", rows=rows, counts=lu.counts(rows), fields=lu.FIELDS, fields_for=lu.fields_for,
        retired=lu.RETIRED, missing_fields=lu.missing_fields, needs=lu.needs,
        open_n=sum(1 for r in rows if r.get("Status") != "done" and lu.needs(r))))


@app.post("/act/listing-update-all")
@sam_only
def act_listing_update_all():
    """One Save saves every listing he has changed on the page."""
    from . import listing_updates as lu
    b = request.get_json(silent=True) or {}
    items = b.get("listings") or []
    if not isinstance(items, list) or len(items) > 200:
        abort(400)
    n = 0
    for it in items:
        if not isinstance(it, dict) or not it.get("id"):
            continue
        vals = it.get("values") or {}
        lu.save(str(it["id"])[:40], {f: str(vals[f])[:200] for f in lu.FIELDS if f in vals},
                str(it.get("notes", ""))[:5000], False)
        n += 1
    return jsonify(ok=True, saved=n)


@app.post("/act/listing-update")
@sam_only
def act_listing_update():
    from . import listing_updates as lu
    lid = request.form["id"]
    if request.form.get("done") == "yes":
        lu.mark_done(lid)
    else:
        lu.save(lid, {f: request.form[f][:200] for f in lu.FIELDS if f in request.form},
                request.form.get("notes", "")[:5000], request.form.get("ready") == "yes")
    return redirect(url_for("listing_updates_view") + "?done=saved")


# ------------------------------------------------------------------ Marketing
@app.route("/marketing")
def marketing_view():
    from . import marketing
    return render_template("marketing.html", **_ctx(page="marketing", **marketing.view()))


@app.post("/act/marketing")
@sam_only
def act_marketing():
    from . import marketing
    op = request.form.get("op", "add")
    if op == "add" and request.form.get("title", "").strip():
        marketing.add(request.form.get("kind", "Idea"), request.form["title"][:300],
                      request.form.get("start", "")[:10], request.form.get("end", "")[:10],
                      request.form.get("platforms", "")[:200], request.form.get("details", "")[:5000],
                      why=request.form.get("why", "")[:500])
    elif op == "edit":
        marketing.edit(request.form["id"], {f: request.form.get(f, "")[:5000] for f in marketing.EDITABLE})
    elif op == "status":
        marketing.set_status(request.form["id"], request.form["status"])
    elif op == "hand":
        marketing.hand(request.form["id"])
    return redirect(url_for("marketing_view") + "#" + (request.form.get("id") or "add"))


# ------------------------------------------------------------------ Stats and SEO
@app.route("/stats")
def stats_view():
    from . import stats_seo as ss
    fixes_n = sum(1 for r in record.rows("Listing Updates")
                  if "wording" in r.get("Needs", "") and r.get("Status") != "done")
    return render_template("stats_seo.html", **_ctx(
        page="stats", stats=ss.table(), seo=ss.seo(), platforms=ss.PLATFORMS, metrics=ss.METRICS,
        lines=ss.LINES, title_tag_fixes=fixes_n))


@app.post("/act/stats")
@sam_only
def act_stats():
    from . import stats_seo as ss
    if request.form.get("op") == "refresh":
        ss.refresh_auto("Sam")
    elif request.form.get("value", "").strip():
        plat, metric = request.form.get("platform", ""), request.form.get("metric", "")
        if plat not in ss.PLATFORMS or metric not in ss.METRICS:
            abort(400)
        ss.add_reading(plat, metric, request.form["value"][:30], request.form.get("source", "")[:200])
    return redirect(url_for("stats_view"))


@app.post("/act/seo")
@sam_only
def act_seo():
    from . import stats_seo as ss
    op = request.form.get("op")
    try:
        if op == "add" and request.form.get("text", "").strip():
            kind = "Tag" if request.form.get("kind") == "Tag" else "Task"
            line = request.form.get("line", "")
            ss.add_seo(kind, request.form["text"][:300], line if line in ss.LINES else "",
                       request.form.get("platforms", "")[:100], request.form.get("why", "")[:300])
        elif op == "status":
            ss.set_status(request.form["id"], request.form["status"])
        elif op == "hand":
            ss.hand(request.form["id"])
    except ValueError:
        abort(400)
    return redirect(url_for("stats_view"))


@app.post("/api/stats")
def api_stats():
    """Agents report a number: {"platform", "metric", "value", "source"}."""
    _need_charter()
    from . import stats_seo as ss
    b = request.get_json(silent=True) or {}
    if b.get("platform") not in ss.PLATFORMS or b.get("metric") not in ss.METRICS or not str(b.get("value", "")).strip():
        return jsonify(error="platform, metric and value required", platforms=ss.PLATFORMS, metrics=ss.METRICS), 400
    ss.add_reading(b["platform"], b["metric"], str(b["value"])[:30],
                   str(b.get("source", ""))[:200] or f"{request.who} via agent API", request.who)
    return jsonify(ok=True)


# ------------------------------------------------------------------ Video and photo
@app.route("/media")
def media_view():
    from . import media
    from . import surfaces as surfaces_mod
    try:
        folders, drive_err = files.drive_folders(), ""
    except Exception as e:  # noqa: BLE001 - the page still works from the laptop
        folders, drive_err = [], str(e)[:200]
    return render_template("media.html", **_ctx(
        page="media", batches=media.media_in_batches(), folders=folders, drive_err=drive_err,
        jobs=media.recent_jobs(), pipe=media.pipeline(),
        vplats=media.VIDEO_PLATFORMS, pplats=media.PHOTO_PLATFORMS, editors=media.EDITORS,
        surfaces=surfaces_mod.by_status()))


@app.route("/media-file")
def media_file():
    """Preview a video or photo on the page: only files inside the app's own folders."""
    if getattr(request, "who", None) != "Sam":
        abort(403)
    from .ward import fences
    try:
        p = fences.check_showable(paths.ROOT / request.args.get("p", ""))
    except fences.Fenced:
        abort(404)
    ok_roots = [paths.BATCHES.resolve(), paths.UPLOAD_TODAY.resolve(), (paths.ROOT / "done").resolve()]
    if not p.is_file() or not any(r in p.parents for r in ok_roots):
        abort(404)
    return send_file(p, conditional=True)


@app.post("/act/media")
@sam_only
def act_media():
    from . import media
    from .ward import fences
    op = request.form.get("op", "")
    try:
        if op == "drive":
            media.import_drive(request.form["folder"], request.form.get("batch", "").strip())
        elif op == "prep":
            media._run("prep", "Prep " + ", ".join(pathlib_name(f) for f in request.form.getlist("f")),
                       media.prep_files, request.form.getlist("f"))
        elif op == "captions":
            media._run("captions", "Captions for " + pathlib_name(request.form["f"]),
                       media.make_captions, request.form["f"])
        elif op == "edit":
            media.ask_edit(request.form["f"], request.form.get("words", "")[:4000],
                           request.form.get("to", "Claude"))
        elif op == "start":
            media.start_post(request.form.getlist("f"), request.form.get("piece", "")[:200],
                             request.form.get("words", "")[:45000], request.form.getlist("platform"),
                             tags=request.form.get("tags", "")[:500], alt=request.form.get("alt", "")[:8000],
                             earned=request.form.get("earned", "")[:500])
        else:
            abort(400)
    except (ValueError, fences.Fenced) as e:
        return redirect(url_for("media_view") + "?err=" + quote_plus(str(e)[:200]))
    return redirect(url_for("media_view") + f"?done={op}#jobs")


def pathlib_name(p: str) -> str:
    return p.replace("\\", "/").rsplit("/", 1)[-1][:80]


# ------------------------------------------------------------------ Skills
@app.route("/skills")
def skills_view():
    from . import skills
    return render_template("skills.html", **_ctx(page="skills", cat=skills.catalogue()))


@app.post("/act/skill")
@sam_only
def act_skill():
    from . import skills
    agent = request.form.get("agent", "Claude")
    if agent not in ("Claude", "Kimi", "ChatGPT"):
        abort(400)
    note = request.form.get("note", "").strip()[:4000]
    detail = request.form.get("detail", "").strip()[:1000]
    words = " ".join(x for x in (f"Details: {detail}." if detail else "",
                                  f"His words: {note}" if note else "") if x)
    sid = skills.ask(agent, request.form["skill"][:80], words)
    back = request.form.get("back", "")
    if back.startswith("/") and not back.startswith("//"):      # only back to one of the app's own pages
        return redirect(back.split("?")[0] + f"?done=skill&to={agent}&sid={sid}")
    return redirect(url_for("skills_view") + "?done=asked")


# ------------------------------------------------------------------ Writing
@app.route("/writing")
def writing_view():
    from . import docs_studio, library, writing
    lib = library.load()
    groups = writing.grouped_docs(lib.get("docs", []))
    # opens on the most recently changed essay unless he picked a document
    first_essay = next((d["id"] for name, ds in groups if name.startswith("Essays") for d in ds), None)
    picked = request.args.get("doc")
    if picked:
        docs_studio.set_working(picked)
    # the pop-up editor opens on the document he's working on
    working_doc = picked or docs_studio.working()
    doc_id = working_doc or first_essay or docs_studio.DOCS[0][1]
    try:
        secs = docs_studio.sections(doc_id)
    except Exception as e:  # noqa: BLE001 - show it, don't break the page
        secs, err = [], str(e)[:200]
    else:
        err = ""
    for s in secs:
        s["draft"] = docs_studio.draft(doc_id, s["title"])
    current = docs_studio.doc(doc_id)
    return render_template("writing.html", **_ctx(
        library=lib, open_doc=current, open_link=f"https://docs.google.com/document/d/{doc_id}/edit",
        page="writing", w=writing.by_kind(), groups=groups, areas=[a for a, _ in groups],
        topics=writing.TOPICS, doc_id=doc_id, sections=secs, area_of=writing.area_of,
        where_of=writing.where, prompt_context=writing.prompt_context, prompt_why=writing.PROMPT_WHY,
        working_doc=doc_id if current else None,
        studio_error=err, qstatuses=writing.QUEUE_STATUSES, qplatforms=writing.QUEUE_PLATFORMS))


@app.get("/studio/sections")
def studio_sections():
    if getattr(request, "who", None) != "Sam":
        abort(403)
    from . import docs_studio
    try:
        return jsonify([s["title"] for s in docs_studio.sections(request.args["doc"])])
    except Exception:  # noqa: BLE001
        return jsonify(["General notes"])


@app.get("/studio/live")
def studio_live():
    """The pop-up editor's refresh: the whole document with his drafts."""
    if getattr(request, "who", None) != "Sam":
        abort(403)
    from . import docs_studio
    try:
        return jsonify(docs_studio.live(request.args["doc"]))
    except docs_studio.fences.Fenced:
        abort(400)
    except Exception as e:  # noqa: BLE001 - the editor keeps what it has and says so
        return jsonify(error=str(e)[:200]), 502


@app.post("/studio/autosave")
@sam_only
def studio_autosave():
    from . import docs_studio
    b = request.get_json(silent=True) or {}
    doc_id, section = str(b.get("doc", "")), str(b.get("section", ""))[:200]
    text, to = str(b.get("text", ""))[:100000], str(b.get("to", "Claude"))
    try:
        docs_studio.save_draft(doc_id, section, text)
        # typing only keeps his words safe; his Save button sends the instruction
        sid = docs_studio.edit_request(doc_id, section, text, to) if b.get("send") is True else None
    except docs_studio.fences.Fenced:
        abort(400)
    return jsonify(ok=True, request=sid, to=to,
                   saved_at=pacing.now().strftime("%I:%M %p").lstrip("0"))


@app.get("/studio/item")
def studio_item():
    """A draft or capture, opened in the pop-up editor."""
    if getattr(request, "who", None) != "Sam":
        abort(403)
    from . import writing
    it = writing.item(request.args.get("id", ""))
    return jsonify(it) if it else (jsonify(error="not found"), 404)


@app.post("/studio/item-save")
@sam_only
def studio_item_save():
    from . import writing
    b = request.get_json(silent=True) or {}
    try:
        sid = writing.save_item(str(b.get("id", "")), str(b.get("text", ""))[:100000],
                                b.get("send") is True, str(b.get("to", "Claude")))
    except ValueError:
        abort(400)
    return jsonify(ok=True, request=sid, to=b.get("to"),
                   saved_at=pacing.now().strftime("%I:%M %p").lstrip("0"))


@app.post("/act/capture")
@sam_only
def act_capture():
    from . import docs_studio, writing
    text = request.form.get("words", "").strip()
    doc = request.form.get("doc", "")
    topic = request.form.get("category", "Something else")[:60]
    if text and doc == "new":
        # a new piece with no document yet: it goes to Claude as material, by topic
        writing.capture(text[:50000], "New piece", request.form.get("title", "").strip()[:120] or "(untitled)", topic)
    elif text:
        d = docs_studio.doc(doc)
        if d:
            writing.capture(text[:50000], d[0], request.form.get("section", "General notes")[:200], topic)
    return redirect(url_for("writing_view") + "?done=captured#capture")


@app.post("/act/writing-delete")
@sam_only
def act_writing_delete():
    from . import writing
    wid = request.form.get("id", "")
    if not writing.delete(wid):
        abort(400)
    return redirect(url_for("writing_view") + "?done=deleted")


@app.post("/act/capture-approve")
@sam_only
def act_capture_approve():
    from . import writing
    writing.approve_capture(request.form["id"])
    return redirect(url_for("writing_view") + "#capture")


@app.post("/act/studio-save")
@sam_only
def act_studio_save():
    from . import docs_studio
    doc_id = request.form["doc"]
    try:
        section, text = request.form["section"][:200], request.form.get("text", "")[:100000]
        docs_studio.save_draft(doc_id, section, text)
        to = record.duty().get("passes")
        docs_studio.edit_request(doc_id, section, text, to if to in docs_studio.EDITORS else "Claude")
    except docs_studio.fences.Fenced:
        abort(400)
    return redirect(url_for("writing_view", doc=doc_id) + "&done=saved#studio")


@app.post("/act/queue")
@sam_only
def act_queue():
    from . import writing
    if request.form.get("op") == "status":
        writing.queue_status(request.form["id"], request.form["status"])
    elif request.form.get("title", "").strip():
        writing.queue_add(request.form["title"][:300], request.form.get("platform", "Blog")[:20],
                          request.form.get("category", "General")[:40])
    return redirect(url_for("writing_view") + "#queue")


@app.post("/act/shipped")
@sam_only
def act_shipped():
    from . import writing
    what = request.form.get("what", "").strip()
    if what:
        writing.shipped_add(request.form.get("date") or actionlog.now_central()[:10], what[:500])
    return redirect(url_for("writing_view") + "#shipped")


@app.post("/act/writing-answer")
@sam_only
def act_writing_answer():
    from . import writing
    words = request.form.get("words", "").strip()
    if words:
        writing.answer(request.form["id"], words[:20000])
    return redirect(url_for("writing_view") + "?done=answered#" + request.form["id"])


@app.post("/act/writing-decide")
@sam_only
def act_writing_decide():
    from . import writing
    d = request.form["decision"]
    if d not in ("yes", "no", "drop it", "send back"):
        abort(400)
    reason = request.form.get("reason", "").strip()
    writing.decide(request.form["id"], d + (f": {reason[:500]}" if reason else ""))
    return redirect(url_for("writing_view") + "?done=decided")


# ------------------------------------------------------------------ Team table
def _threads():
    th = {}
    for m in record.rows("Team"):
        if not m.get("Thread"):
            continue
        t = th.setdefault(m["Thread"], {"id": m["Thread"], "topic": m.get("Topic", ""),
                                        "messages": [], "status": "open"})
        t["messages"].append(m)
        if m.get("Topic"):
            t["topic"] = m["Topic"]
        if m.get("Status"):
            t["status"] = m["Status"]
    return sorted(th.values(), key=lambda t: t["messages"][-1]["When (Central)"], reverse=True)


def team_post(thread: str, topic: str, by: str, message: str, question: str = "",
              status: str = "open") -> str:
    if not thread:
        # next number after the highest existing thread (a count would reuse
        # a number if one was ever skipped)
        thread = record.next_id("Team", "T-", key="Thread")
    record.append("Team", {"Thread": thread, "Topic": topic, "When (Central)": actionlog.now_central(),
                           "By": by, "Message (verbatim)": message,
                           "Question for Sam": question, "Status": status})
    if question:
        aid = record.next_id("Approvals", "A-")
        record.append("Approvals", {
            "ID": aid, "Item": f"{by} asks ({thread}): {question}", "Kind": "question",
            "His one action": "Type your answer. It goes back to the team.",
            "Raised": actionlog.now_central()[:10], "Status": "waiting",
            "Source": f"Team table {thread}"})
    actionlog.log(by if by in actionlog.WHO else "App", f"Team table {thread}: message from {by}.")
    return thread


@app.route("/team")
def team():
    return render_template("team.html", **_ctx(page="team", threads=_threads()))


@app.post("/act/team")
@sam_only
def act_team():
    who = request.form.get("as", "Sam")
    if who not in ("Sam", "ChatGPT"):
        abort(400)
    msg = request.form.get("message", "").strip()
    if not msg:
        return redirect(url_for("team"))
    if who == "ChatGPT":
        guard.check("Team table paste from ChatGPT", "ChatGPT", msg)
        link = request.form.get("link", "").strip()
        if link:
            msg += f"\n\n(Chat link: {link})"
    t = team_post(request.form.get("thread", ""), request.form.get("topic", "")[:200], who, msg)
    return redirect(url_for("team") + "#" + t)


@app.post("/act/team-close")
@sam_only
def act_team_close():
    team_post(request.form["thread"], "", "Sam", "Closed.", status="closed")
    return redirect(url_for("team"))


# ------------------------------------------------------------------ agent API
API_FIELDS = {
    "claim": {"queue_id": 40, "note": 300},
    "release": {"queue_id": 40, "where_stopped": 500},
    "post": {"queue_id": 40, "platform": 40, "item": 200, "url": 500,
             "caption_as_posted": 5000, "date_central": 10, "time_central": 5,
             "state": 20, "source": 300},
    "approval": {"item": 500, "kind": 20, "his_one_action": 300,
                 "draft": 20000, "source_dictation": 20000, "source": 300},
    "pass_run": {"pass_name": 80, "outcome": 20, "summary": 1000},
    "log": {"entry": 1000},
    "request_update": {"request_id": 20, "status": 20, "result": 2000},
    "team": {"thread": 20, "topic": 200, "message": 5000, "question_for_sam": 500},
    "writing_draft": {"item": 200, "text": 45000, "source": 300, "owner": 40, "due": 20},
    "marketing_add": {"kind": 20, "title": 300, "start": 10, "end": 10, "platforms": 200,
                      "details": 5000, "why": 500},
}
PLATFORMS = {c[0] for c in seed.PACING_CEILINGS} | {"Etsy", "WordPress", "Ko-fi", "Website"}


def _fields(kind: str) -> dict:
    """Structured fields only. Unknown fields are refused, lengths capped,
    every text scanned. Text is stored as data and never acted on."""
    body = request.get_json(silent=True)
    if not isinstance(body, dict):
        abort(make_response(jsonify(error="send a JSON object"), 400))
    allowed = API_FIELDS[kind]
    extra = set(body) - set(allowed)
    if extra:
        guard.record("agent API", request.who, json.dumps(body)[:2000],
                     ["unexpected fields: " + ", ".join(sorted(extra))])
        abort(make_response(jsonify(error="unknown fields", fields=sorted(extra)), 400))
    out = {}
    for k, cap in allowed.items():
        v = body.get(k, "")
        if not isinstance(v, str):
            abort(make_response(jsonify(error=f"{k} must be text"), 400))
        out[k] = v[:cap]
    out["_flags"] = guard.check(f"agent API {kind}", request.who, *out.values())
    return out


def _need_charter():
    if request.who not in _charter_served:
        abort(make_response(jsonify(
            error="Fetch GET /api/charter first. Every connection starts with it."), 428))


@app.get("/api/charter")
def api_charter():
    when = actionlog.now_central()
    _charter_served[request.who] = when
    actionlog.log(request.who, "Connected to the agent API; charter served.")
    return jsonify(title="The Address to Any Mind", source=charter.source(),
                   served_at=when, text=charter.text())


@app.get("/api/record/<tab>")
def api_record(tab):
    _need_charter()
    if tab not in schema.TABS:
        abort(404)
    record.pull()
    rows = [{k: v for k, v in r.items() if k != "_row"} for r in record.rows(tab)]
    if tab == "Duty":
        return jsonify(duty=record.duty(), history=rows)
    return jsonify(tab=tab, rows=rows, pulled_at=record.status()["pulled_at"])


@app.get("/api/duty")
def api_duty():
    _need_charter()
    record.pull()
    return jsonify(record.duty())


@app.get("/api/pacing")
def api_pacing():
    _need_charter()
    record.pull()
    return jsonify(now_central=pacing.now().strftime("%Y-%m-%d %H:%M"),
                   platforms=pacing.today())


@app.post("/api/queue/claim")
def api_claim():
    _need_charter()
    f = _fields("claim")
    q = record.find("Queue", "ID", f["queue_id"])
    if not q:
        return jsonify(error="no such queue item"), 404
    holder = q.get("Claimed by", "")
    if holder and not holder.startswith(request.who):
        return jsonify(error="claimed by another actor", claimed_by=holder), 409
    stamp = f"{request.who} {actionlog.now_central()}"
    record.set_cell("Queue", q["_row"], "Claimed by", stamp)
    actionlog.log(request.who, f"QUEUE CLAIMED {f['queue_id']}", note=f["note"])
    return jsonify(ok=True, claimed_by=stamp)


@app.post("/api/queue/release")
def api_release():
    _need_charter()
    f = _fields("release")
    q = record.find("Queue", "ID", f["queue_id"])
    if not q:
        return jsonify(error="no such queue item"), 404
    record.set_cell("Queue", q["_row"], "Claimed by", "")
    actionlog.log(request.who, f"QUEUE RELEASED {f['queue_id']}",
                  where_stopped=f["where_stopped"])
    return jsonify(ok=True)


@app.post("/api/posts")
def api_post():
    _need_charter()
    f = _fields("post")
    if f["platform"] not in PLATFORMS:
        return jsonify(error="unknown platform", allowed=sorted(PLATFORMS)), 400
    # a date or time pacing can't read would silently drop out of the floor
    for k, fmt in (("date_central", "%Y-%m-%d"), ("time_central", "%H:%M")):
        if f[k]:
            try:
                datetime.datetime.strptime(f[k], fmt)
            except ValueError:
                return jsonify(error=f"{k} must look like {fmt.replace('%', '')}"), 400
    if f["state"] not in ("", "live", "scheduled"):
        return jsonify(error="state must be live or scheduled"), 400
    if f["url"] and not f["url"].startswith(("https://", "http://")):
        # it becomes a link on his screens: never a javascript: or file: link
        return jsonify(error="url must start with https://"), 400
    n = pacing.now()
    pid = record.next_id("Posts", "P-")
    record.append("Posts", {
        "ID": pid, "Date (Central)": f["date_central"] or n.strftime("%Y-%m-%d"),
        "Time (Central)": f["time_central"] or n.strftime("%H:%M"),
        "Platform": f["platform"], "Item": f["item"], "URL": f["url"],
        "Caption as posted": f["caption_as_posted"], "Posted by": request.who,
        "State": f["state"] or "live", "Source": f["source"] or f"{request.who} via agent API",
        "As of": n.strftime("%Y-%m-%d")})
    actionlog.log(request.who, f"Post result {pid}: {f['platform']} {f['item']}", url=f["url"])
    return jsonify(ok=True, id=pid, flagged=f["_flags"])


# ------------------------------------------------------------------ approved Etsy changes
@app.get("/api/etsy/pending")
def api_etsy_pending():
    """Etsy changes he has approved that are not on Etsy yet (or wait for his Save)."""
    _need_charter()
    from . import etsy_changes
    return jsonify(pending=etsy_changes.pending(), now_central=actionlog.now_central())


@app.post("/api/etsy/mark")
def api_etsy_mark():
    """{source: "approval"|"listing update", id, platform, state: staged|saved|failed, note}."""
    _need_charter()
    from . import etsy_changes
    b = request.get_json(silent=True) or {}
    ok = etsy_changes.mark(str(b.get("source", "")), str(b.get("id", ""))[:40], str(b.get("platform", "Etsy"))[:20],
                           str(b.get("state", "")), str(b.get("note", ""))[:400], request.who)
    return (jsonify(ok=True), 200) if ok else (jsonify(error="unknown item or state"), 400)


# ------------------------------------------------------------------ the upload pass
@app.get("/api/uploads/due")
def api_uploads_due():
    """Browser-route posts whose pacing time has come, with everything needed to post them."""
    _need_charter()
    return jsonify(due=posting.due_jobs(request.who), now_central=actionlog.now_central())


@app.post("/api/uploads/<op>")
def api_uploads(op):
    """claim {job_id} / done {job_id, url} (after checking it live) / failed {job_id, why}."""
    _need_charter()
    b = request.get_json(silent=True) or {}
    jid = str(b.get("job_id", ""))[:20]
    if op == "claim":
        ok = posting.claim_job(jid, request.who)
        return (jsonify(ok=True), 200) if ok else (jsonify(error="not yours to claim, or already posted"), 409)
    if op == "done":
        url = str(b.get("url", ""))[:500]
        if not url.startswith("https://"):
            return jsonify(error="url must be the live post's https:// link"), 400
        return (jsonify(ok=True), 200) if posting.finish_job(jid, url, request.who) \
            else (jsonify(error="no such job, or another agent has claimed it"), 409)
    if op == "failed":
        return (jsonify(ok=True), 200) if posting.fail_job(jid, str(b.get("why", ""))[:400], request.who) \
            else (jsonify(error="no such job"), 404)
    abort(404)


@app.post("/api/requests/update")
def api_request_update():
    _need_charter()
    f = _fields("request_update")
    r = record.find("Requests", "ID", f["request_id"])
    if not r:
        return jsonify(error="no such request"), 404
    if f["status"] not in ("open", "working", "done", "needs Sam", "can't do"):
        return jsonify(error="status must be open, working, done, needs Sam or can't do"), 400
    record.set_cell("Requests", r["_row"], "Status", f["status"])
    record.set_cell("Requests", r["_row"], "Result", f["result"])
    record.set_cell("Requests", r["_row"], "Updated", f"{actionlog.now_central()} {request.who}")
    actionlog.log(request.who, f"Request {f['request_id']}: {f['status']}", result=f["result"][:200])
    return jsonify(ok=True)


@app.post("/api/team")
def api_team():
    _need_charter()
    f = _fields("team")
    if not f["message"]:
        return jsonify(error="message is empty"), 400
    t = team_post(f["thread"], f["topic"], request.who, f["message"], f["question_for_sam"])
    return jsonify(ok=True, thread=t, flagged=f["_flags"])


@app.post("/api/approvals/drafts")
def api_approval_drafts():
    """A caption item for the Inbox: his source words plus one draft per
    platform. Structured: {"item", "queue_id", "source_dictation",
    "platforms": {"Bluesky": "...", ...}, "files": [...], "ai_written": false}."""
    _need_charter()
    body = request.get_json(silent=True) or {}
    allowed = {"item", "queue_id", "source_dictation", "platforms", "files",
               "ai_written", "is_sale_clip"}
    if not isinstance(body, dict) or set(body) - allowed or not isinstance(body.get("platforms"), dict) \
            or not isinstance(body.get("files", []), list):
        return jsonify(error="fields: " + ", ".join(sorted(allowed)) +
                       " (platforms an object, files a list)"), 400
    unknown = sorted(str(k) for k in body["platforms"] if str(k) not in checks.LIMITS)
    if unknown:
        return jsonify(error="unknown platforms", platforms=unknown, allowed=sorted(checks.LIMITS)), 400
    plats = {str(k)[:40]: str(v)[:20000] for k, v in body["platforms"].items()
             if str(k) in checks.LIMITS}
    flags = guard.check("agent API drafts", request.who, body.get("source_dictation", ""),
                        *plats.values())
    aid = approvals.create(str(body.get("item", ""))[:300], str(body.get("queue_id", ""))[:40],
                           str(body.get("source_dictation", ""))[:20000], plats, request.who,
                           files=[str(x)[:300] for x in body.get("files", [])][:20],
                           ai_written=bool(body.get("ai_written")),
                           is_sale_clip=bool(body.get("is_sale_clip")))
    return jsonify(ok=True, id=aid, flagged=flags)


@app.post("/api/marketing/add")
def api_marketing_add():
    """A season, seasonal idea or campaign for the Marketing page - e.g. a
    real astrological date (a zodiac season, a retrograde, a moon) as
    Kind="Season", or a themed idea (content or a future piece) as
    Kind="Idea". {"kind" (Season/Sale/SEO change/Campaign/Idea), "title",
    "start", "end" (YYYY-MM-DD), "platforms", "details", "why"}. Ideas about
    a future physical piece must stay themes/symbolism only - never invented
    materials, wood or dimensions; those are his to add."""
    _need_charter()
    from . import marketing
    f = _fields("marketing_add")
    mid = marketing.add(f["kind"] or "Idea", f["title"], f["start"], f["end"],
                        f["platforms"], f["details"], who=request.who, why=f["why"])
    return jsonify(ok=True, id=mid, flagged=f["_flags"])


@app.post("/api/writing/draft")
def api_writing_draft():
    """A finished piece of prose (a blog post draft and anything similar)
    goes onto the Writing screen, ready for him to open, edit and decide on
    - not just a note in the Inbox. {"item", "text", "source", "owner"
    (optional, defaults to you), "due" (optional, YYYY-MM-DD)}."""
    _need_charter()
    from . import writing
    f = _fields("writing_draft")
    wid = writing.add_draft(f["item"], f["text"], f["source"],
                            owner=f["owner"] or request.who, due=f["due"], who=request.who)
    return jsonify(ok=True, id=wid, flagged=f["_flags"])


@app.post("/api/approvals")
def api_approval():
    _need_charter()
    f = _fields("approval")
    aid = record.next_id("Approvals", "A-")
    record.append("Approvals", {
        "ID": aid, "Item": f["item"], "Kind": f["kind"] or "draft",
        "His one action": f["his_one_action"] or "Approve or send back.",
        "Raised": pacing.now().strftime("%Y-%m-%d"), "Status": "waiting",
        "Source": f["source"] or f"{request.who} via agent API"})
    if f["draft"] or f["source_dictation"]:
        _save_draft(aid, f)
    actionlog.log(request.who, f"Draft for approval {aid}: {f['item'][:80]}")
    return jsonify(ok=True, id=aid, flagged=f["_flags"])


def _save_draft(aid: str, f: dict) -> None:
    d = paths.DRAFTS / "approvals"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{aid}.json").write_text(json.dumps({
        "id": aid, "by": request.who, "item": f["item"], "draft": f["draft"],
        "source_dictation": f["source_dictation"], "flags": f["_flags"]},
        ensure_ascii=False, indent=2), encoding="utf-8")


PASS_RUNS = paths.DATA / "pass_runs.json"


def _pass_runs() -> dict:
    return json.loads(PASS_RUNS.read_text(encoding="utf-8")) if PASS_RUNS.exists() else {}


@app.post("/api/pass-run")
def api_pass_run():
    _need_charter()
    f = _fields("pass_run")
    runs = _pass_runs()
    runs[f["pass_name"]] = {"agent": request.who, "when": actionlog.now_central(),
                            "outcome": f["outcome"] or "done", "summary": f["summary"]}
    PASS_RUNS.write_text(json.dumps(runs, indent=2, ensure_ascii=False), encoding="utf-8")
    # hourly routines check in every run; an empty check-in is kept above
    # (so My day knows the routine is alive) but not added to the Log
    if f["outcome"] != "nothing to do":
        actionlog.log(request.who, f"Pass ran: {f['pass_name']} ({f['outcome'] or 'done'})",
                      summary=f["summary"][:300])
    return jsonify(ok=True)


@app.post("/api/log")
def api_log():
    _need_charter()
    f = _fields("log")
    actionlog.log(request.who, f["entry"])
    return jsonify(ok=True)


@app.errorhandler(403)
def forbidden(_e):
    return _uninvited("forbidden action")


# ------------------------------------------------------------------ start
def _worker():
    """Background jobs, every minute: post anything whose time has come.
    Every 5 minutes: sync the record and prep queued files. Every 30: Bluesky."""
    import time
    n = 0
    while True:
        try:
            posting.run_due()
            if n % 5 == 0:
                record.pull(force=True)
                prep.prep_queue()
            if n % 30 == 0:
                fixes.recheck_platforms("App")
            if n % 360 == 0:    # every six hours: Bluesky and Pixelfed follower counts
                from . import stats_seo
                stats_seo.refresh_auto("App")
        except Exception:  # noqa: BLE001 - try again next round
            pass
        n += 1
        time.sleep(60)


def main():
    access.ensure_keys()
    # Serve immediately from the laptop's cached copy (record.raw/rows already
    # fall back to record_cache.json); refresh from the live Sheet in the
    # background instead of making every screen wait ~30s for it on startup.
    threading.Thread(target=lambda: record.pull(force=True), daemon=True).start()
    threading.Thread(target=_worker, daemon=True).start()
    from waitress import serve
    serve(app, host=os.environ.get("CONTROL_ROOM_HOST", "127.0.0.1"), port=PORT, threads=8)


if __name__ == "__main__":
    main()
