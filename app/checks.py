"""The checks every approval item runs through, from the procedures:
platform length, words not in his source, the shop-link rule, the AI
Attribution Note, the factual limits, and pacing.

Nothing here rewrites anything. It only reports.
"""
import html
import re

from . import pacing, public_page, record

# Character limits per platform (captions/descriptions). Sources: KIMI
# PROCEDURE 03/04 and 00 KIMI STATE Platform Mechanics, plus each platform.
LIMITS = {
    "Bluesky": 300,           # ledger: "Max 4 images, 300 characters"
    "Threads": 500,           # ledger: "500-character limit"
    "Pixelfed": 2000,         # ledger: caption counter "0/2000"
    "Instagram": 2200,
    "Instagram Story": None,
    "TikTok": 2200,           # description stays blank by standing rule
    "YouTube": 5000,          # description; title is 100 (uploader README)
    "YouTube title": 100,
    "Facebook": 63206,
    "Tumblr": None,
    "Etsy title": 140,
    "Etsy": None,
    "Discord": 2000,          # plug-in longform-essay: one message of 2,000
    "FetLife": None,          # full length
    "Substack": None,
    "Blog": None,
}
THREADED = {"Bluesky", "Threads"}  # longform-essay: a thread, the limit is per post
LINK_FREE = {"TikTok"}        # "TikTok descriptions stay blank regardless"
NO_NOTE = {"Etsy", "Etsy title"}   # "No Attribution for etsy at this time"

# ---- from the Example Shop plug-in (read 27 Sep 2026), verbatim lists
PLUGIN = "example-plugin"
# etsy-listing, references/banned-language.md
WEAPON_WORDS = ["weapon", "combat", "battle", "fight", "strike", "blow", "thrust", "parry", "defense",
                "defensive", "deflect", "shield", "armor", "armored", "fortified", "attack", "assault",
                "guard", "martial", "self-defense", "intimidating", "imposing", "formidable"]
WEAPON_PHRASES = ["sturdy enough to", "strong enough to", "could be used to", "take a beating"]
OUTCOME = ["attracts", "brings", "manifests", "manifestation", "prosperity", "draws in", "heals",
           "healing", "cures", "balances your chakras", "clears negative energy", "protects you",
           "wards off", "charged to", "activated for", "will bring", "helps you", "promotes",
           "enhances your", "aligns your", "raises your vibration"]
HEDGES = ["said to", "traditionally believed", "may help with"]
FRANCHISE = ["gandalf", "hogwarts", "elder wand", "ollivander", "middle-earth", "rivendell", "sauron"]
FILLER = ["this beautiful handcrafted", "perfect for any practitioner", "designed to enhance",
          "crafted with care", "made with love", "this listing is for", "you are purchasing",
          "it is worth noting", "please note", "certainly", "in essence", "in other words",
          "perfect for everyone", "utilize", "leverage"]
BANNED_TAGS = ["bo staff", "jo staff", "martial arts", "mobility aid", "cane for elderly",
               "orthopedic cane", "sturdy cane"]
SUBJECTIVE = ["beautiful", "perfect", "stunning", "unique"]
# photo/video-post-multiplatform tag rules
OCCULT_TAGS = ["#witchsky", "#occultsky", "#pagansky", "#spiritsky", "#esotericsky"]
OCCULT_HINT = re.compile(r"\b(ritual|occult|pagan|witch\w*|magick\w*|wand|altar|spirit\w*|esoteric|grimoire|sigil)\b", re.I)
TAGGED = {"Bluesky", "Instagram", "Tumblr", "Pixelfed"}    # "tags on every platform that has them"
REPOST_LINE = "(Repost — from the TikTok archive, not new work.)"
KOFI = re.compile(r"ko-fi\.com/example-maker", re.I)
FILMING = re.compile(r"\b(magick\w*|example\s*shop)\b", re.I)


def _words_in(text: str, words: list[str]) -> list[str]:
    low = (text or "").lower()
    return [w for w in words if re.search(r"(?<![\w-])" + re.escape(w) + r"(?![\w-])", low)]


def spoken_problems(transcript: str) -> list[str]:
    """video-post Stage 0: spoken lines that break the filming rules
    (no "magick", no shop or community name). Practice vocabulary and names
    or addresses have no list in the skill, so a person still reads them."""
    return [ln.strip() for ln in (transcript or "").splitlines() if FILMING.search(ln)]

WORD = re.compile(r"[A-Za-z][A-Za-z'’-]*")
URL = re.compile(r"https?://\S+")
TAG = re.compile(r"#\w+")
NOTE = re.compile(r"AI Attribution Note\b.*", re.S)
ETSY_ID = re.compile(r"etsy\.com/(?:[\w-]+/)?listing/(\d+)")
STOREFRONT = re.compile(r"exampleshop\.etsy\.com/?(?:\s|$)")
# The fixed line the procedures add for listed pieces; not his speech.
ALLOWED_LINES = [re.compile(r"On Etsy:\s*https?://\S+"),
                 re.compile(re.escape("(Repost — from the TikTok archive, not new work.)"))]
SMALL = {"a", "an", "the", "and", "or", "of", "to", "in", "on", "it", "its", "it's",
         "is", "i", "my", "this", "that"}


def _norm(w: str) -> str:
    return w.lower().replace("’", "'").strip("'-")


def source_words(source: str) -> set[str]:
    out = set()
    for w in WORD.findall(source or ""):
        n = _norm(w)
        out.add(n)
        # "hand-carved" in his words also covers "hand carved", and "wand's" covers "wand"
        out.update(p for p in n.split("-") if p)
        if n.endswith("'s"):
            out.add(n[:-2])
    return out


def _said(n: str, have: set[str]) -> bool:
    """Is this (normalised) draft word in his words? Punctuation-only
    differences are not new words: hyphenation ("hand carved" /
    "hand-carved", "copper--and") and a possessive of a word he said."""
    if not n or n in have or n in SMALL:
        return True
    if n.endswith("'s") and n[:-2] in have:
        return True
    parts = [p for p in n.split("-") if p]
    return len(parts) > 1 and all(p in have or p in SMALL for p in parts)


def strip_extras(text: str) -> str:
    """Remove the parts that are not his speech but are allowed: links, tags,
    the 'On Etsy:' line and the attribution note."""
    t = NOTE.sub("", text or "")
    for rx in ALLOWED_LINES:
        t = rx.sub("", t)
    t = URL.sub("", t)
    t = TAG.sub("", t)
    return t


def new_words(draft: str, source: str) -> list[str]:
    have = source_words(source)
    out = []
    for w in WORD.findall(strip_extras(draft)):
        n = _norm(w)
        if not _said(n, have) and n not in out:
            out.append(n)
    return out


def highlight(draft: str, source: str) -> str:
    """HTML of the draft with any word not in his source marked."""
    have = source_words(source)
    extras = set()
    for rx in (URL, TAG):
        extras.update(m.group(0) for m in rx.finditer(draft or ""))
    note = NOTE.search(draft or "")
    body = draft[:note.start()] if note else (draft or "")
    out, pos = [], 0
    allowed_spans = []
    for rx in ALLOWED_LINES + [URL, TAG]:
        allowed_spans += [(m.start(), m.end()) for m in rx.finditer(body)]

    def in_allowed(i):
        return any(a <= i < b for a, b in allowed_spans)

    for m in WORD.finditer(body):
        out.append(html.escape(body[pos:m.start()]))
        w = m.group(0)
        if in_allowed(m.start()):
            out.append(f'<span class="extra">{html.escape(w)}</span>')
        elif _said(_norm(w), have):
            out.append(html.escape(w))
        else:
            out.append(f'<mark class="notsaid" title="not in his words">{html.escape(w)}</mark>')
        pos = m.end()
    out.append(html.escape(body[pos:]))
    if note:
        out.append(f'<span class="extra">{html.escape(draft[note.start():])}</span>')
    return "".join(out).replace("\n", "<br>")


def live_listing_ids() -> set[str]:
    return {r["Etsy listing ID"] for r in record.rows("Listings")
            if r.get("Status") == "live" and r.get("Etsy listing ID")}


def run(platform: str, draft: str, source: str, ai_written: bool = False,
        is_sale_clip: bool = False) -> list[dict]:
    """Every check for one platform's draft. Each result: name, ok, words."""
    res = []
    n = len(draft or "")
    lim = LIMITS.get(platform)
    posts = [p for p in re.split(r"\n\s*\n", draft or "") if p.strip()]
    if lim and n > lim and platform in THREADED and len(posts) > 1:
        longest = max(len(p) for p in posts)
        res.append({"name": "Length", "ok": longest <= lim,
                    "words": f"A thread of {len(posts)} posts, longest {longest} of {lim} characters"})
    else:
        res.append({"name": "Length", "ok": lim is None or n <= lim,
                    "words": f"{n} of {lim} characters" if lim else f"{n} characters (no limit)"})

    nw = new_words(draft, source)
    res.append({"name": "His words only", "ok": not nw,
                "words": "Every word is from his source." if not nw else
                "Not in his words: " + ", ".join(nw)})

    ids = ETSY_ID.findall(draft or "")
    live = live_listing_ids()
    if platform in LINK_FREE and (ids or URL.search(draft or "")):
        res.append({"name": "Shop link", "ok": False, "words": f"{platform} carries no link."})
    elif ids:
        bad = [i for i in ids if i not in live]
        res.append({"name": "Shop link", "ok": not bad,
                    "words": "Links a live listing." if not bad else
                    "Listing not live in the record: " + ", ".join(bad)})
    elif STOREFRONT.search(draft or ""):
        res.append({"name": "Shop link", "ok": is_sale_clip,
                    "words": "Storefront link: only for a sale-advert clip (his 24 Sep rule)."})
    else:
        res.append({"name": "Shop link", "ok": True, "words": "No shop link."})

    has_note = bool(NOTE.search(draft or ""))
    if platform in NO_NOTE:
        res.append({"name": "Attribution note", "ok": not has_note,
                    "words": "Etsy carries no note." if not has_note else "Remove the note: Etsy carries none."})
    elif ai_written:
        good = has_note and re.search(r"\((Claude, Anthropic|Kimi, Moonshot AI|ChatGPT/ChatGPT, OpenAI)\)", draft)
        sep = re.search(r"\n\s*(-{3,}|_{3,}|\*{3,})\s*\n\s*AI Attribution Note", draft or "")
        # longform-essay: three labelled percentages, each explained, naming him Sam/Sam
        m = NOTE.search(draft or "")
        note = m.group(0) if m else ""
        parts = [re.search(rx, note, re.I) for rx in (r"Direct input:?\s*(\d+)\s*%",
                                                      r"Directed/requested:?\s*(\d+)\s*%",
                                                      r"AI-researched/generated:?\s*(\d+)\s*%")]
        split_ok = all(parts) and sum(int(p.group(1)) for p in parts) == 100
        named = "sam/sam" in note.lower()
        ok = bool(good) and not sep and split_ok and named
        missing = [w for w, bad in (("the AI named", not good), ("no separator", sep),
                                    ("the three-way split adding to 100", not split_ok),
                                    ("him named as Sam/Sam", not named)) if bad]
        res.append({"name": "Attribution note", "ok": ok,
                    "words": "Note present: names the AI, three-way split adds to 100, names Sam/Sam, no separator."
                    if ok else "AI-written: the note needs " + ", ".join(missing) + "."})
    else:
        res.append({"name": "Attribution note", "ok": True,
                    "words": "His own words: no note needed." if not has_note else "Note present."})

    problems = [name for name, rx in public_page.CHECKS if rx.search(draft or "")]
    res.append({"name": "Factual limits", "ok": not problems,
                "words": "No forge, lapidary or move problems." if not problems else ", ".join(problems)})

    res += plugin_checks(platform, draft)

    base = platform.replace(" title", "")
    if base in {c[0] for c in pacing.seed.PACING_CEILINGS}:
        t, wait = pacing.next_slot(base)
        left = next((p["left"] for p in pacing.today() if p["platform"] == base), None)
        now = pacing.now()
        when = "held" if t is None else "now" if t <= now else t.strftime("%a %I:%M %p").replace(" 0", " ")
        ok = t is not None and (left is None or left > 0)
        res.append({"name": "Pacing", "ok": ok,
                    "words": f"Earliest: {when}" + (f"; {left} left today" if left is not None else "")
                    + (f". {wait}" if wait else "")})
    return res


def plugin_checks(platform: str, draft: str) -> list[dict]:
    """The rules from his Example Shop plug-in skills. "warn" items are
    advice (they don't mark the platform as failing); the rest are rules."""
    t = draft or ""
    out = []
    src = f"{PLUGIN}"
    if platform == "TikTok":
        out.append({"name": "TikTok blank", "ok": not t.strip(),
                    "words": "Description blank, as the rule says." if not t.strip()
                    else f"TikTok's description is always left blank: no caption, no hashtags ({src}:video-post-multiplatform)."})
    if platform == "Facebook":
        tags = TAG.findall(t)
        out.append({"name": "Facebook hashtags", "ok": not tags,
                    "words": "No hashtags." if not tags else "Facebook stays hashtag-free: remove " + " ".join(tags)})
        out.append({"name": "Facebook link", "ok": not URL.search(t),
                    "words": "No link in the body." if not URL.search(t)
                    else "Facebook body carries no link; the link goes in the first comment."})
    if platform in ("Etsy", "Etsy title"):
        bad = (_words_in(t, WEAPON_WORDS) + _words_in(t, WEAPON_PHRASES) + _words_in(t, BANNED_TAGS))
        out.append({"name": "Weapon language", "ok": not bad,
                    "words": "None found (this rule outranks everything else)." if not bad
                    else "Banned on Etsy: " + ", ".join(bad) + " (etsy-listing banned-language)."})
        oc = _words_in(t, OUTCOME) + _words_in(t, HEDGES)
        out.append({"name": "Promised outcomes", "ok": not oc,
                    "words": "None found. Judge the sentence, not only the words." if not oc
                    else "Promises an outcome or hedges: " + ", ".join(oc)})
        fr = _words_in(t, FRANCHISE)
        out.append({"name": "Franchise names", "ok": not fr,
                    "words": "None." if not fr else "Living franchise names: " + ", ".join(fr) + " (use wizard, mage, druid, fantasy, LARP, ren faire)."})
        fl = _words_in(t, FILLER) + (["em dash"] if "—" in t else [])
        out.append({"name": "Etsy style", "ok": not fl,
                    "words": "No filler, no em dashes." if not fl else "Remove: " + ", ".join(fl)})
    if platform == "Etsy title":
        words = len(WORD.findall(t))
        punct = [c for c in ",|" if c in t]
        subj = _words_in(t, SUBJECTIVE)
        ok = words <= 15 and not punct and not subj
        out.append({"name": "Etsy title rules", "ok": ok,
                    "words": f"{words} words, no commas or pipes." if ok else
                    f"{words} of 15 words" + (", no commas or pipes" if punct else "")
                    + (", no subjective words: " + ", ".join(subj) if subj else "") + "."})
    if platform not in ("Etsy", "Etsy title"):
        bad = _words_in(t, WEAPON_WORDS) + _words_in(t, WEAPON_PHRASES)
        if bad:
            out.append({"name": "Weapon language", "ok": True, "warn": True,
                        "words": "Words Etsy treats as weapon language: " + ", ".join(bad) + ". Fine here, never on Etsy."})
    if platform in TAGGED and t.strip():
        tags = [x.lower() for x in TAG.findall(t)]
        out.append({"name": "Tags", "ok": True, "warn": not tags,
                    "words": f"{len(tags)} tags." if tags else "No tags: the skills say tags on every post, on every platform that has them."})
        if platform == "Bluesky" and OCCULT_HINT.search(t) and not any(x in OCCULT_TAGS for x in tags):
            out.append({"name": "#WitchSky family", "ok": True, "warn": True,
                        "words": "An occult or ritual post: add one of #WitchSky #OccultSky #PaganSky #SpiritSky #EsotericSky."})
    if platform in ("Blog", "Substack"):
        out.append({"name": "Ko-fi block", "ok": bool(KOFI.search(t)),
                    "words": "Ends with the Ko-fi block." if KOFI.search(t)
                    else "Every blog post ends with the Ko-fi block (ko-fi.com/example), before the note."})
    return out
