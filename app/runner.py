"""Hand work to an agent from the Control Room.

The app does not start agent sessions by itself. A job for Claude or Kimi is
queued as a request in the Requests tab, in Sam' words, for that agent's
next session or scheduled pass. ChatGPT reads the Sheet through its Drive
connection.
"""
from . import record
from .ward import actionlog


def queue_for(agent: str, job: str, what: str, who: str = "Sam") -> str:
    sid = record.next_id("Requests", "S-")
    record.append("Requests", {
        "ID": sid, "When (Central)": actionlog.now_central(), "His words (verbatim)": what,
        "About": "operations", "For": agent, "Status": "open", "Result": "",
        "Updated": f"Queued from the Control Room ({job})"})
    actionlog.log(who, f"Handed to {agent}: {job} ({sid})")
    return sid
