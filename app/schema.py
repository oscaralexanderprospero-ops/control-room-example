"""The shape of the one record: tab names and their column headers.

The Google Sheet "Example Record" is the record. These headers are
row 1 of each tab. The app finds columns by header name, so a column added by
hand in the Sheet does not break anything.
"""

SHEET_TITLE = "Example Record"

TABS = {
    "Queue": [
        "ID", "Batch", "Piece", "File", "Platforms left", "Status",
        "Source dictation", "Link rule", "Order", "Claimed by", "Notes",
        "Source", "As of",
    ],
    "Posts": [
        "ID", "Date (Central)", "Time (Central)", "Platform", "Item", "URL",
        "Caption as posted", "Posted by", "State", "Source", "As of",
    ],
    "Listings": [
        "Etsy listing ID", "Piece", "Status", "Listed", "URL", "Price",
        "Last verified", "Notes", "Source",
    ],
    "Approvals": [
        "ID", "Item", "Kind", "His one action", "Raised", "Status",
        "Decision", "Decided on", "Source",
    ],
    "Pacing": [
        "Platform", "Posts today", "Last post today (Central)",
        "Next allowed (Central)", "Daily ceiling", "Posts left",
        "Ceiling source", "Notes",
    ],
    "Duty": ["Setting", "Value", "Since", "Set by", "Reason"],
    "Reviews": [
        "ID", "Date", "By", "About", "Note (verbatim)", "Chat link",
        "Status", "Sam decided", "Decided on",
    ],
    "Tasks": [
        "Agent", "Pass", "Central time", "Days", "State", "Original cron",
        "Source", "Notes",
    ],
    "Public": [
        "Section", "Item", "Status", "His words", "Show", "Source", "As of",
    ],
    "Log": ["When (Central)", "By", "Entry"],
    # Added in Stage 2 at Sam' request (27 Sep 2026):
    # his dictated instructions, and the agents' shared problem threads.
    "Requests": [
        "ID", "When (Central)", "His words (verbatim)", "About", "For",
        "Status", "Result", "Updated",
    ],
    "Team": [
        "Thread", "Topic", "When (Central)", "By", "Message (verbatim)",
        "Question for Sam", "Status",
    ],
    # Writing and publishing (from Kimi Work's "Writing and Publishing" tab
    # design, KIMI WORK DASHBOARD REBUILD SPEC 2 Sep 2026, with current facts).
    "Writing": [
        "ID", "Kind", "Item", "Owner", "Due", "Status", "His words (verbatim)",
        "Source", "As of",
    ],
    # Every listing that needs any update, with columns for Sam to fill.
    "Listing Updates": [
        # Length -> Height and Handle or thickest width -> Thickness, his ruling 27 Sep 2026
        "Listing ID", "Piece", "Active or Draft", "Needs", "Detail", "Weight", "Height",
        "Thickness", "Ferrule OD", "Grip length", "Grip wrap", "Cord or chain length",
        "Shipping tube length", "Finish", "Species", "His notes (verbatim)", "Status", "Source", "As of",
    ],
    # Business: orders and customer messages, custom orders and repairs,
    # and customer reviews (added 27 Sep 2026 at his request).
    "Orders": [
        "ID", "Kind", "Received (Central)", "Customer", "Item", "Listing ID", "Price",
        "Ship or answer by", "Status", "Tracking", "Notes", "Source", "As of",
    ],
    "Custom Orders": [
        "ID", "Kind", "Customer", "What", "Materials", "Price", "Deposit", "Due", "Status",
        "Channel", "His notes (verbatim)", "Source", "As of",
    ],
    "Customer Reviews": [
        "ID", "Date", "Stars", "Listing", "Reviewer", "Review (verbatim)", "Reply status",
        "Reply", "Source", "As of",
    ],
    # Stats (one row per reading, so history is kept) and SEO (tag bank + tasks).
    "Stats": ["Date", "Platform", "Metric", "Value", "Source"],
    "SEO": ["ID", "Kind", "Product line", "Text", "Platforms", "Status", "Why", "Source", "As of"],
    # Seasonal SEO changes, sales, marketing campaigns and ideas.
    "Marketing": [
        "ID", "Kind", "Title", "Start", "End", "Platforms", "Details", "Status", "Owner",
        "Source", "As of", "Why it's here",
    ],
    # The four Kimi Work dashboard tabs, copied into the app (27 Sep 2026).
    # One row per item; each widget knows how to show its own rows.
    "Boards": [
        "ID", "Board", "Widget", "Title", "Detail", "Stage", "Owner",
        "Platform", "Date", "Done", "Source", "As of",
    ],
}

# Duty tab layout: rows 2 and 3 are the two live cells; history starts at row 6.
DUTY_PASSES_CELL = "B2"
DUTY_REVIEW_CELL = "B3"
DUTY_HISTORY_HEADER_ROW = 5
DUTY_HISTORY_HEADERS = ["When (Central)", "Cell", "From", "To", "By", "Reason"]

# ChatGPT added at his request (27 Sep 2026). ChatGPT works in ChatGPT, not on
# this laptop, so the duty page warns before passes are handed to it.
PASSES_CHOICES = ["Claude", "Kimi", "ChatGPT"]
REVIEW_CHOICES = ["ChatGPT", "Claude"]

# The three agents and their lanes, as Sam ruled them.
AGENTS = [
    {
        "name": "Claude",
        "maker": "Anthropic",
        "lane": "Runs the scheduled passes when on duty. Makes the changes "
                "(site code, drafts from his words). Can cover review when "
                "ChatGPT is short on tokens.",
        "source": "SITE CHANNEL v2, SAM DECIDED 24 Sep 2026; KIMI HANDOVER Part 2",
    },
    {
        "name": "Kimi",
        "maker": "Moonshot AI, in Kimi Work",
        "lane": "Covers the scheduled passes, uploads and Etsy drafts when "
                "the passes are switched to Kimi here. His words only: tidies "
                "and cuts his dictation, fills mechanical fields. No essays.",
        "source": "KIMI HANDOVER Part 2, rulings of 26 Sep 2026; always-on tasks 28 Sep 2026",
    },
    {
        "name": "ChatGPT",
        "maker": "ChatGPT, OpenAI",
        "lane": "Brainstorms, critiques and reviews. Reads Drive through "
                "ChatGPT's Google Drive connection. Never rewrites his words. "
                "Claude can cover when ChatGPT is short on tokens.",
        "source": "SITE CHANNEL v2, SAM DECIDED 24 Sep 2026",
    },
]
