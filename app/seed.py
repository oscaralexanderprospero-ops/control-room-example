"""Example data for the demo. Everything here is made up.

"Example Woodworks" is a pretend one-person shop. The rows show the shape of
each tab so the screens have something to display. Replace them with your own,
or point the app at your own Google Sheet (see README).
"""

LEDGER = "example ledger"
DAY = "2026-01-15"

# ---------------------------------------------------------------- Queue
LINK = "Final line: the shop link, on every platform except TikTok."
QUEUE = [
    ["Q-01", "A", "Walnut walking stick", "walnut-stick-detail.mp4",
     "Bluesky, YouTube, TikTok", "in progress",
     "Here is the walnut stick I finished this weekend. I oiled it twice and "
     "the grain came up nicely near the handle.",
     LINK, "1", "", "Example note: waiting on the second clip.", LEDGER, DAY],
    ["Q-02", "A", "Walnut walking stick", "walnut-stick-handle.mp4",
     "Instagram, Facebook", "ready", "", LINK, "2", "", "", LEDGER, DAY],
    ["Q-03", "B", "Maple spoon set", "spoons-flatlay.jpg", "Pixelfed, Threads",
     "waiting on his dictation", "", "", "", "",
     "Example: the app asks once and does not nag.", LEDGER, DAY],
    ["Q-05", "C", "Ash bookends", "ash-bookends-finish.mp4",
     "Bluesky, YouTube, Instagram", "ready",
     "The ash bookends are done. Two coats of oil, and I rounded every edge by hand.",
     LINK, "3", "", "Example: caption is cut from his words, never rewritten.", LEDGER, DAY],
    ["Q-06", "C", "Ash bookends", "ash-bookends-photos-1.jpg",
     "Pixelfed, Threads, Tumblr", "in progress", "", LINK, "4", "Claude",
     "Example: claimed by Claude, photos being prepared.", LEDGER, DAY],
    ["Q-07", "D", "Cherry cutting board (sold)", "cherry-board-sold.mp4",
     "Facebook", "held", "", "Sold: no link.", "", "",
     "Example: a sold piece never gets a shop link.", LEDGER, "2026-01-09"],
    ["Q-04", "old", "Bench tour clip", "", "Tumblr", "low priority", "", "",
     "", "", "", LEDGER, DAY],
]

# ---------------------------------------------------------------- Posts
def _p(i, date, time, platform, item, url, by="Claude", state="live",
       source=LEDGER, as_of=DAY, caption=""):
    return [i, date, time, platform, item, url, caption, by, state, source,
            as_of]

POSTS = [
    _p("P-001", "2026-01-14", "09:10", "Bluesky", "Maple spoon set",
       "https://example.com/post/1", caption="Three maple spoons, freshly oiled."),
    _p("P-002", "2026-01-14", "10:20", "YouTube", "Maple spoon set",
       "https://example.com/post/2"),
    _p("P-003", "2026-01-14", "11:30", "TikTok", "Maple spoon set", ""),
    _p("P-004", "2026-01-15", "12:00", "Facebook", "Walnut walking stick", "",
       state="scheduled"),
    _p("P-005", "2026-01-13", "09:05", "Bluesky", "Cherry cutting board",
       "https://example.com/post/5", caption="Cherry board, finished. Food-safe oil, three coats."),
    _p("P-006", "2026-01-13", "10:15", "YouTube", "Cherry cutting board",
       "https://example.com/post/6", caption="(title) Finishing a cherry cutting board"),
    _p("P-007", "2026-01-13", "11:40", "Instagram", "Cherry cutting board",
       "https://example.com/post/7"),
    _p("P-008", "2026-01-12", "14:20", "Pixelfed", "Spoon carving, day two",
       "https://example.com/post/8", caption="Second day on the maple spoons: the bowls are hollowed."),
    _p("P-009", "2026-01-12", "15:30", "Threads", "Spoon carving, day two",
       "https://example.com/post/9"),
    _p("P-010", "2026-01-11", "09:00", "Bluesky", "Bench tour",
       "https://example.com/post/10", caption="A quick tour of the bench, tools on the wall."),
    _p("P-011", "2026-01-11", "10:10", "Tumblr", "Bench tour", "https://example.com/post/11"),
    _p("P-012", "2026-01-10", "16:00", "Etsy", "Walnut walking stick listing",
       "https://example.com/listing/1000000001", by="Sam"),
    _p("P-013", "2026-01-15", "16:30", "Bluesky", "Ash bookends", "",
       state="scheduled"),
    _p("P-014", "2026-01-15", "17:45", "YouTube", "Ash bookends", "",
       state="scheduled"),
]

# ---------------------------------------------------------------- Listings
LISTINGS = [
    ["1000000001", "Walnut walking stick, 36 inch, oiled finish", "live",
     "2026-01-10", "https://example.com/listing/1000000001", "$120",
     "2026-01-14", "", LEDGER],
    ["1000000002", "Maple spoon set of three", "live", "2026-01-05",
     "https://example.com/listing/1000000002", "$45", "2026-01-14", "", LEDGER],
    ["1000000003", "Cherry cutting board", "sold", "", "", "", "2026-01-08",
     "Sold. Never link.", LEDGER],
]

# ---------------------------------------------------------------- Approvals
APPROVALS = [
    ["A-01", "Blog post draft: \"What I learned oiling my first walnut piece\"",
     "draft", "Say yes or no to the draft.", "2026-01-13", "waiting", "", "",
     LEDGER],
    ["A-02", "Etsy draft listing: Ash bookends", "listing",
     "Open the draft and press publish yourself.", "2026-01-14", "waiting",
     "", "", LEDGER],
    ["A-03", "Captions for the ash bookends video (Bluesky, YouTube title)", "draft",
     "Approve, cut, ask ChatGPT, or send back.", "2026-01-15", "waiting", "", "", "Claude; queue Q-05"],
    ["A-04", "Caption for the maple spoon photos (Pixelfed)", "draft",
     "Approve, cut, ask ChatGPT, or send back.", "2026-01-14", "waiting", "", "", "Claude; queue Q-03"],
]

# Inbox drafts: detail files written by tools/build_demo.py (drafts/approvals/<ID>.json)
INBOX_DRAFTS = {
    "A-03": {
        "item": "Captions for the ash bookends video", "queue_id": "Q-05", "by": "Claude",
        "source_dictation": ("The ash bookends are done. Two coats of oil, and I rounded every edge "
                             "by hand. They are heavy enough to hold a shelf of books."),
        "ai_written": False, "is_sale_clip": True, "files": ["ash-bookends-finish.mp4"],
        "platforms": {
            "Bluesky": "The ash bookends are done. Two coats of oil, and I rounded every edge by hand.",
            "YouTube title": "The ash bookends are done",
        },
    },
    "A-04": {
        "item": "Caption for the maple spoon photos", "queue_id": "Q-03", "by": "Claude",
        "source_dictation": "Three maple spoons, freshly oiled. The grain in the smallest one surprised me.",
        "ai_written": False, "is_sale_clip": False, "files": ["spoons-flatlay.jpg"],
        "platforms": {"Pixelfed": "Three maple spoons, freshly oiled."},
    },
}

# ---------------------------------------------------------------- Writing
# (ID, Kind, Item, Owner, Due, Status, His words, Source, As of)
WRITING = [
    ["W-01", "draft", "Blog: What I learned oiling my first walnut piece", "Claude", "2026-01-20",
     "waiting", "", "Built from Sam's stated positions", DAY],
    ["W-02", "draft", "Essay: Why I still make spoons by hand", "Claude", "2026-01-27",
     "waiting", "", "Built from Sam's stated positions", DAY],
    ["W-03", "draft", "Newsletter: January at the bench", "Kimi", "2026-01-31",
     "sent back", "", "Example: sent back with a reason", DAY],
    ["K-01", "capture", "Spoon carving guide / Chapter 4 / Book", "Sam", "", "staged",
     "Keep the hook knife sharper than you think you need. A dull one tears the grain and you fight it the whole way.",
     "Capture box in the Control Room", DAY],
    ["K-02", "capture", "Blog / Oiling / Blog post", "Sam", "", "staged",
     "Walnut drinks the first coat. Wait a full day before the second one.",
     "Capture box in the Control Room", DAY],
    ["P-1", "prompt", "Do you oil the inside of a spoon bowl, or leave it raw?", "Claude", "2026-01-22",
     "waiting", "", "Example prompt", DAY],
    ["P-2", "prompt", "What is the one tool a beginner should buy first?", "Claude", "2026-01-29",
     "answered 2026-01-14", "A good straight knife, before anything else.", "Example prompt", DAY],
    ["Q-W1", "queue", "What I learned oiling my first walnut piece", "Blog", "Craft", "Drafting", "", "", DAY],
    ["Q-W2", "queue", "Why I still make spoons by hand", "Substack", "Craft", "Idea", "", "", DAY],
    ["Q-W3", "queue", "A month of small bench wins", "Blog", "Other", "Queued", "", "", DAY],
    ["S-W1", "shipped", "Blog: Setting up the bench", "Sam", "2026-01-06", "done", "", "Blog", DAY],
    ["S-W2", "shipped", "Substack: What I am making this winter", "Sam", "2026-01-13", "done", "", "Substack", DAY],
]

# ---------------------------------------------------------------- Team table
# (Thread, Topic, When, By, Message, Question for Sam, Status)
TEAM = [
    ["T-001", "Pacing on Facebook", "2026-01-13 09:00", "Claude",
     "Facebook already has four posts today. I held the fifth until after the hour floor.", "", "open"],
    ["T-001", "", "2026-01-13 09:20", "ChatGPT",
     "Agreed. Holding is right. The evening slot is free if you want to use it.", "", "open"],
    ["T-002", "Alt text for the bookends photos", "2026-01-14 11:00", "Kimi",
     "I wrote alt text for all four photos. It only says what the photo shows.", "", "open"],
    ["T-002", "", "2026-01-14 11:30", "Claude",
     "One photo shows a shadow that reads like a crack. I need to know if it is a crack.",
     "Is the dark line on the second bookend photo a crack or a shadow?", "open"],
    ["T-003", "Etsy renewal timing", "2026-01-10 08:00", "ChatGPT",
     "Renewing every day does not help search. Renew only when a listing expires.", "", "closed"],
]

# ---------------------------------------------------------------- Requests
# (ID, When, His words, About, For, Status, Result, Updated)
REQUESTS = [
    ["S-001", "2026-01-14 08:10", "Please queue the bookends video for Bluesky and YouTube, and put the captions in my Inbox.",
     "upload", "Claude", "done", "Queued as Q-05; captions are in the Inbox (A-03).", "2026-01-14 08:40"],
    ["S-002", "2026-01-14 19:20", "Move the Facebook post for the walnut stick to noon tomorrow.",
     "operations", "Claude", "working", "", ""],
    ["S-003", "2026-01-15 07:50", "Start a draft about what I learned oiling walnut. Use what I told you last week.",
     "writing", "Claude", "done", "Draft W-01 is on the Writing screen.", "2026-01-15 08:15"],
]


# ---------------------------------------------------------------- Duty
DUTY_CELLS = [
    ["Scheduled passes on duty", "Claude", "2026-01-10", "Sam",
     "Example: Claude runs the scheduled passes until Sam says otherwise."],
    ["Review duty", "ChatGPT", "2026-01-10", "Sam",
     "Example: ChatGPT reviews, Claude builds."],
]
DUTY_HISTORY = [
    ["2026-01-10", "Scheduled passes on duty", "Kimi", "Claude", "Sam",
     "Example hand-over"],
]

# ---------------------------------------------------------------- Reviews
REVIEWS = [
    ["R-001", "2026-01-12", "Claude", "Community routing",
     "Start routing bench posts into a woodworking group.", "", "PROPOSED",
     "", ""],
]

# ---------------------------------------------------------------- Tasks
EX = "example schedule"
TASKS = [
    ["Claude", "Photo pass", "11:30am, 5:30pm", "daily", "on", "", EX, ""],
    ["Claude", "Video upload", "10am, 1pm, 4pm", "daily", "on", "", EX, ""],
    ["Claude", "Blog draft-and-stage", "9:00am", "Mon, Wed, Fri", "on", "", EX, ""],
    ["Claude", "Link and bio audit", "7:00pm", "1st of month", "off", "", EX,
     "Example: switched off."],
]

# ---------------------------------------------------------------- Public
STATUS = "Example status page"
PUBLIC = [
    ["Books", "A Beginner's Guide to Spoon Carving", "8 of 10 chapters",
     "Example text. Nearly done."],
    ["Bench", "Woodworking", "steady", "Example text. The trade the shop is built on."],
    ["Bench", "Metalwork", "early", "Example text. Learning."],
    ["Platforms", "Live now", "", "Bluesky, YouTube, Etsy, a website"],
]
PUBLIC_ROWS = [r + ["Y", STATUS, DAY] for r in PUBLIC]

# ---------------------------------------------------------------- Log
LOG = [
    [DAY + " 09:00", "Claude", "Demo record created with made-up example data."],
]

# ---------------------------------------------------------------- Pacing
PACING_CEILINGS = [
    ["Bluesky", 5, "Example ceiling", ""],
    ["YouTube", 5, "Example ceiling", ""],
    ["TikTok", 5, "Example ceiling", ""],
    ["Facebook", 5, "Example ceiling", "Most often double-booked."],
    ["Threads", 2, "Example ceiling", ""],
    ["Instagram", 1, "Example ceiling", "Stories are separate."],
    ["Instagram Story", "", "Example: daily", ""],
    ["Pixelfed", 5, "Example ceiling", ""],
    ["Tumblr", 3, "Example ceiling", ""],
    ["Etsy", "", "No ceiling", ""],
    ["WordPress", "", "No ceiling", ""],
]

AMBIGUOUS = [
    "Example: a queue item where the notes disagree about which platform is still wanted.",
]
