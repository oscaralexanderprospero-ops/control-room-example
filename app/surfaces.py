"""Community surfaces, from the plug-in skill
example-plugin:platform-community-surfaces (read 27 Sep 2026).

Where each post should ALSO land, what each surface costs to enter, and which
are gated, hostile or dead, with the threshold that would change that. The
app shows this; it posts nothing here. Engagement (a restack, a reply, a
join, a pack addition) is not a post and costs nothing against the pacing
ceilings; anything that makes a NEW post in a feed (a Substack Note, a
community-tagged thread) counts and goes through pacing.
"""
import re

SKILL = "example-plugin:platform-community-surfaces"

# (platform, surface, status, what it needs / what changes it)
SURFACES = [
    ("Facebook", "Groups: woodworking category", "active",
     "Share from the published post's own page into each group, one at a time."),
    ("Facebook", "Example group awaiting approval", "pending", "Join questionnaire not answered yet."),
    ("Bluesky", "Curated feeds", "active", "Tag the post; feeds also match on alt text."),
    ("Tumblr", "Woodworking community", "active", "Tag AI-assisted content."),
    ("Instagram", "Collab posts", "active", "Up to 5 collaborators."),
    ("YouTube", "Memberships", "gated", "Needs a subscriber and watch-time minimum."),
    ("Etsy", "Teams and Forums", "hostile", "Useless as promotion."),
    ("TikTok", "Fan Groups", "gated", "Needs a follower minimum."),
]

CANE = re.compile(r"\b(cane|canes|walking[- ]stick|stick|staff|staves|carving)\b", re.I)
WAND = re.compile(r"\b(wand|wands|pendant|pendants)\b", re.I)


def also_land_in(item: str, platforms: list[str]) -> list[str]:
    """For one post: the community surfaces it should also land in."""
    out = []
    cane, wand = bool(CANE.search(item or "")), bool(WAND.search(item or ""))
    if "Facebook" in platforms:
        if cane or not wand:
            out.append("Facebook: share into every cane / walking-stick / staff / carving group, one group at a time from the published post.")
        if wand or not cane:
            out.append("Facebook: share into every pagan / witchcraft group, one group at a time from the published post.")
    if "Bluesky" in platforms:
        out.append("Bluesky: a #WitchSky-family tag if it's occult or ritual, and alt text, so the curated feeds pick it up.")
    if "Tumblr" in platforms:
        out.append("Tumblr: reblog into the matching community (tag it as AI content if it is).")
    if "Threads" in platforms:
        out.append("Threads: the fitting community (Art Threads or Photographers of Threads for bench photos) is a phone job and counts as a post.")
    if "Substack" in platforms or "Blog" in platforms:
        out.append("Substack: a Note pointing at the piece (counts as a post; pacing).")
    if "YouTube" in platforms:
        out.append("YouTube: a Post about it (no subscriber minimum).")
    return out


def by_status() -> dict:
    out = {}
    for plat, surf, status, need in SURFACES:
        out.setdefault(status, []).append({"platform": plat, "surface": surf, "need": need})
    return out
