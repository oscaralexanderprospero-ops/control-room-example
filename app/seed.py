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
