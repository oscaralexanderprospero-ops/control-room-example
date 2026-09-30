/* Control Room: the step-by-step tour, and the speak button. */

const STEPS = {
  plan: [
    ["[data-tour=plan-title]", "My day. This is where the Control Room opens now. It shows one thing at a time, so you always know what's next."],
    ["[data-tour=plan-now]", "Now: the one thing to do. Press Done when it's done. 'Not now' moves it out of the way without losing it. 'Go there' opens the page where it gets done."],
    ["[data-tour=plan-focus]", "Focus for 25 minutes: a quiet timer. It keeps counting on other screens and chimes when time's up."],
    ["[data-tour=plan-then]", "Then: what comes after, in order. 'Do this now' moves anything to the top."],
    ["[data-tour=plan-add]", "Add something: type it or press Speak. Give it a time if it has one. Anything of yours that isn't done carries over to tomorrow by itself."],
  ],
  today: [
    [null, "Welcome to your Control Room. This is the one place between you and your agents: Claude, Kimi and ChatGPT. I'll show you around, one thing at a time. Press Next."],
    ["[data-tour=nav]", "These are your screens. Click any of them at any time. Nothing you click here posts anything by itself."],
    ["[data-tour=strip]", "This line is always here. The green light means Windows Defender is protecting the laptop. It also shows who is on duty, and that the app is linked to your Sheet."],
    ["[data-tour=tell]", "Tell the team. Type, or press Speak and talk. What you say goes to the agent on duty, saved in your exact words. Use it to change operations, listings or uploads."],
    ["[data-tour=pace]", "Posts left today, per platform. Each card says where its number comes from. A blank means nobody has a sourced number for it."],
    ["[data-tour=queue]", "The queue: what's waiting to go out. A yellow STALE tag means the fact is over a week old. Press 'Still true' if it is."],
    ["[data-tour=nav-inbox]", "The Inbox is where drafts wait for your yes. Your words sit beside each platform's draft. You approve, cut a sentence, ask ChatGPT, or send it back."],
    ["[data-tour=nav-blocked]", "Blocked on you: everything that needs you, with the fix right under it. Usually it's one button."],
    ["[data-tour=nav-team]", "The Team table is where the agents work problems out together, so you don't have to know the technical details."],
    ["[data-tour=help]", "That's it. Press Help on any screen to see its own walk-through again."],
  ],
  inbox: [
    ["[data-tour=inbox-title]", "The Inbox. Each card is one item waiting for your yes."],
    ["[data-tour=inbox-source]", "On the left: your own words, the source everything must come from."],
    [".plat", "Each platform's draft. Any word not in your words is marked, so a paraphrase stands out. The ticks and crosses are the rule checks: length, shop link, attribution note, facts, pacing."],
    ["details summary", "Cut a sentence: press Cut beside any sentence to remove it. There's no rewriting box, by design."],
    ["[data-tour=inbox-buttons]", "Approve all, ask ChatGPT to look, or send it back with a reason. Every choice is logged."],
  ],
  blocked: [
    ["[data-tour=blocked-title]", "Everything waiting on you. Under each item is its fix."],
    [".fixrow", "Green buttons record your answer. Buttons with an arrow open the exact page you need. 'Hand to' gives the job to the agent on duty."],
    [".typed", "Or type your answer in your own words and press Send."],
  ],
  team: [
    ["[data-tour=team-title]", "The Team table. Claude, Kimi and ChatGPT talk a problem through here."],
    ["textarea", "Put a problem on the table in your own words. The agents pick it up. They only come back to you with one plain question if they truly need you."],
  ],
  writing: [
    ["[data-tour=writing-title]", "Writing: your essays, the questions you owe, and how publishing is going."],
    ["h2", "Drafts waiting on you: say yes, no, or send it back with what to change."],
    ["[data-tour=prompts]", "The questions you owe. Answer by typing or pressing Speak. Your words are saved exactly, and Claude builds only from them."],
  ],
  post: [
    ["[data-tour=post-title]", "Post: approved items ready to go out."],
    ["table", "Each platform shows how it goes. Direct posts by itself at its earliest allowed time. Hand to agent goes to the agent on duty. Needs your click is yours, with the page to open and a box to paste the link once it's up."],
    [".fixrow", "Show file opens the folder with the file picked, ready to drag. Copy file lets you paste it straight into an upload box."],
    ["[data-tour=post-go]", "Post it: one click sets every platform going. Nothing happens before you press it."],
  ],
  duty: [
    [".bigcell", "Who runs the scheduled passes, and who reviews. The switches record your decision, and the agents check it before every pass."],
  ],
  files: [
    ["h2", "Each batch's files on the laptop. 'Show file' opens the folder with that file picked, ready to drag into a website's upload box."],
  ],
  ward: [
    ["h1", "The Ward: the Defender light, anything suspicious, and your Address. The code does the blocking; the Address is your charter."],
  ],
};

const Tour = {
  steps: [], i: 0, page: document.body.dataset.page,
  start(force) {
    this.steps = (STEPS[this.page] || []).filter(s => !s[0] || document.querySelector(s[0]));
    if (!this.steps.length) return;
    this.i = 0;
    document.getElementById("tour").hidden = false;
    this.show();
    if (!force) this.bump();
  },
  bump() {
    try { const k = "oms_tour_" + this.page; localStorage.setItem(k, String((+localStorage.getItem(k) || 0) + 1)); } catch (e) {}
  },
  seen() {
    try { return +localStorage.getItem("oms_tour_" + this.page) || 0; } catch (e) { return 99; }
  },
  show() {
    document.querySelectorAll(".tour-hl").forEach(e => e.classList.remove("tour-hl"));
    const [sel, text] = this.steps[this.i];
    document.getElementById("tourtext").textContent = text;
    document.getElementById("tourstep").textContent = `Step ${this.i + 1} of ${this.steps.length}`;
    document.getElementById("tournext").textContent = this.i === this.steps.length - 1 ? "Done" : "Next";
    if (sel) {
      const el = document.querySelector(sel);
      // the menu is folded by default: open it when the tour points at something inside it
      if (el && el.closest("#topmenu") && typeof omsMenu === "function") omsMenu(true, false);
      if (el) { el.classList.add("tour-hl"); el.scrollIntoView({ block: "center", behavior: "smooth" }); }
    }
  },
  move(d) {
    this.i += d;
    if (this.i < 0) this.i = 0;
    if (this.i >= this.steps.length) return this.end();
    this.show();
  },
  end() {
    document.getElementById("tour").hidden = true;
    document.querySelectorAll(".tour-hl").forEach(e => e.classList.remove("tour-hl"));
  },
};
// The first two visits to each screen show its walk-through by itself.
window.addEventListener("load", () => { if (Tour.seen() < 2) Tour.start(false); });

// Speak buttons: Chrome's built-in speech-to-text fills a box. The Tell the team
// button, plus any button with data-mic="<id of its box>".
(function () {
  const SR = window.SpeechRecognition || window.webkitSpeechRecognition;
  function wire(btn, box) {
    if (!btn || !box) return;
    if (!SR) { btn.hidden = true; return; }
    let rec = null;
    btn.addEventListener("click", () => {
      if (rec) { rec.stop(); return; }
      rec = new SR(); rec.lang = "en-US"; rec.continuous = true; rec.interimResults = false;
      const start = box.value ? box.value + " " : "";
      let said = "";
      rec.onresult = e => { for (let i = e.resultIndex; i < e.results.length; i++) if (e.results[i].isFinal) said += e.results[i][0].transcript + " "; box.value = start + said.trim(); };
      rec.onend = () => { rec = null; btn.textContent = "🎤 Speak"; };
      rec.onerror = () => { rec = null; btn.textContent = "🎤 Speak (didn't catch that)"; };
      btn.textContent = "■ Stop"; rec.start();
    });
  }
  wire(document.getElementById("micbtn"), document.getElementById("tellwords"));
  document.querySelectorAll("button[data-mic]").forEach(b => wire(b, document.getElementById(b.dataset.mic)));
})();

// Focus timer (My day). The end time is kept on this device, so it keeps counting
// through the pages refreshing themselves and shows on every screen's Now line.
(function () {
  const K = "omsFocusEnd", btn = document.getElementById("focusbtn");
  const spots = [document.getElementById("focusleft"), document.getElementById("nowfocus")].filter(Boolean);
  let ctx = null;
  const get = () => { try { return +localStorage.getItem(K) || 0; } catch (e) { return 0; } };
  const set = v => { try { v ? localStorage.setItem(K, String(v)) : localStorage.removeItem(K); } catch (e) {} };
  function chime() {
    try {
      ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
      [0, .35].forEach(d => { const o = ctx.createOscillator(), g = ctx.createGain();
        o.frequency.value = 660; g.gain.setValueAtTime(.15, ctx.currentTime + d);
        g.gain.exponentialRampToValueAtTime(.001, ctx.currentTime + d + .3);
        o.connect(g); g.connect(ctx.destination); o.start(ctx.currentTime + d); o.stop(ctx.currentTime + d + .3); });
    } catch (e) {}
  }
  function tick() {
    const end = get();
    let msg = "";
    if (end && end <= Date.now()) {
      set(0); chime();
      msg = "Time's up. Done, or another 25?";
      document.title = "Time's up · Control Room";
      if (btn) btn.textContent = "⏱ Another 25 minutes";
    } else if (end) {
      msg = Math.ceil((end - Date.now()) / 60000) + " min left";
      if (btn) btn.textContent = "■ Stop the timer";
    } else if (btn && !/Another/.test(btn.textContent)) {
      btn.textContent = "⏱ Focus for 25 minutes";
    }
    if (msg || end) spots.forEach(s => s.textContent = msg);
  }
  if (btn) btn.addEventListener("click", () => {
    ctx = ctx || new (window.AudioContext || window.webkitAudioContext)();
    const running = get() > Date.now();
    set(running ? 0 : Date.now() + 25 * 60000);
    document.title = "Control Room";
    spots.forEach(s => s.textContent = "");
    if (running) btn.textContent = "⏱ Focus for 25 minutes";
    tick();
  });
  tick(); setInterval(tick, 15000);
})();

function showFile(btn) {
  fetch("/act/show-file", { method: "POST", headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: "path=" + encodeURIComponent(btn.dataset.path) });
}

// Selection bars: tick items, then one button does the same thing for every ticked item.
// A bar: <div class="bulkbar" data-group="inbox">, with buttons data-op="approve" and an
// optional <input name="note">. Items: <input type="checkbox" class="bulkpick" data-group="inbox" value="ID">.
(function () {
  document.querySelectorAll(".bulkbar").forEach(bar => {
    const g = bar.dataset.group;
    const picks = () => [...document.querySelectorAll('.bulkpick[data-group="' + g + '"]')].filter(p => !p.closest('[hidden]'));
    const all = bar.querySelector(".bulkall");
    const count = bar.querySelector(".bulkcount");
    const refresh = () => {
      const n = picks().filter(p => p.checked).length;
      count.textContent = n ? n + " selected" : "none selected";
      bar.querySelectorAll("button[data-op]").forEach(b => b.disabled = !n);
      if (all) all.checked = n && n === picks().length;
    };
    if (all) all.addEventListener("change", () => { picks().forEach(p => p.checked = all.checked); refresh(); });
    picks().forEach(p => p.addEventListener("change", refresh));
    bar.querySelectorAll("button[data-op]").forEach(b => b.addEventListener("click", () => {
      const ids = picks().filter(p => p.checked).map(p => p.value);
      if (!ids.length) return;
      if (b.dataset.confirm && !confirm(b.dataset.confirm.replace("{n}", ids.length))) return;
      if (bar.hasAttribute("data-inplace")) {
        const body = new URLSearchParams(); body.append("op", b.dataset.op); ids.forEach(id => body.append("ids", id));
        bar.querySelectorAll("button[data-op]").forEach(x => x.disabled = true);
        fetch("/act/bulk", { method: "POST", headers: { "X-Requested-With": "fetch" }, body })
          .then(r => r.json()).then(d => {
            (d.ids || []).forEach(id => settleCard(document.getElementById(id), "Recorded."));
            count.textContent = d.n + " done";
            refresh();
          }).catch(() => { count.textContent = "That did not go through. Try once more."; refresh(); });
        return;
      }
      const f = document.createElement("form"); f.method = "post"; f.action = "/act/bulk";
      const add = (k, v) => { const i = document.createElement("input"); i.type = "hidden"; i.name = k; i.value = v; f.appendChild(i); };
      add("op", b.dataset.op); ids.forEach(id => add("ids", id));
      const note = bar.querySelector('input[name="note"]'); if (note) add("note", note.value);
      document.body.appendChild(f); f.submit();
    }));
    bar.addEventListener("recount", refresh);
    refresh();
  });
})();

// Answering in place: a form marked data-inplace posts in the background, the card
// says what was recorded, then folds away. The page never reloads or jumps.
function settleCard(card, message) {
  if (!card || card.dataset.settled) return;
  card.dataset.settled = "1";
  const pick = card.querySelector(".bulkpick"); if (pick) pick.checked = false;
  card.classList.add("settled");
  card.innerHTML = '<div class="recorded">&#10003; ' + message.replace(/[&<>]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;" }[c])) + '</div>';
  const badge = document.querySelector('nav a[href="/blocked"] .n, a[href="/blocked"] .n');
  const left = document.querySelectorAll(".card[id]:not(.settled)").length;
  if (badge) { if (left) badge.textContent = left; else badge.remove(); }
  setTimeout(() => {
    card.style.maxHeight = card.offsetHeight + "px";
    requestAnimationFrame(() => card.classList.add("folding"));
    setTimeout(() => { card.remove(); document.querySelectorAll(".bulkbar").forEach(b => b.dispatchEvent(new Event("recount")));
      const clear = document.getElementById("allclear"); if (clear && !document.querySelector(".card[id]")) { clear.hidden = false; document.querySelectorAll(".bulkbar").forEach(b => b.hidden = true); } }, 450);
  }, 1800);
}

document.addEventListener("submit", ev => {
  const f = ev.target;
  if (!f.matches || !f.matches("form[data-inplace]")) return;
  ev.preventDefault();
  if (f.dataset.busy) return;                       // a second click while the first is going does nothing
  const card = f.closest(".card");
  const buttons = card ? card.querySelectorAll("button") : f.querySelectorAll("button");
  const typed = f.querySelector('input[name="text"]');
  if (typed && !typed.value.trim()) { typed.focus(); return; }
  f.dataset.busy = "1"; buttons.forEach(b => b.disabled = true);
  const fd = new URLSearchParams(new FormData(f));
  fetch(f.action, { method: "POST", headers: { "X-Requested-With": "fetch" }, body: fd })
    .then(r => r.json()).then(d => {
      if (d.ok) { settleCard(card, d.message || "Recorded."); }
      else { delete f.dataset.busy; buttons.forEach(b => b.disabled = false); alert(d.message || "That did not go through."); }
    }).catch(() => {
      delete f.dataset.busy; buttons.forEach(b => b.disabled = false);
      alert("That did not go through. Nothing was recorded. Try once more.");
    });
});
