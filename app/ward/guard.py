"""Prompt-injection guard and the Suspicious list.

Anything read from outside (web pages, comments, DMs, Drive docs, file names,
ChatGPT pastes, agent submissions) is stored and shown as data. Nothing here
ever acts on text. This module only looks for text that tries to give orders,
claims special authority, or asks for secrets, and records it so Sam sees
it. Flagged text is still stored verbatim; it is just marked.
"""
import datetime
import json
import re
import threading

from .. import paths

SUSPICIOUS_FILE = paths.DATA / "suspicious.jsonl"
_lock = threading.Lock()

PATTERNS = [
    ("gives orders", r"\b(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|your)\b.{0,30}\b(instructions?|rules?|prompts?|guidelines?)"),
    ("gives orders", r"\b(you (must|should|are required to|need to)|i (order|command|instruct) you)\b"),
    ("gives orders", r"\b(delete|erase|wipe|remove|publish|post|send|transfer|pay|upload|download|run|execute)\b.{0,30}\b(now|immediately|right away|without (asking|approval|confirmation))\b"),
    ("gives orders", r"\bdo not (tell|inform|ask|notify)\b.{0,30}\b(sam|sam|the user|anyone|him)\b"),
    ("claims authority", r"\b(system|admin(istrator)?|developer|anthropic|openai|moonshot|google|security team)\b.{0,20}\b(message|override|notice|instruction|mode|prompt)\b"),
    ("claims authority", r"\b(sam|sam|the owner|the user) (has |already )?(authori[sz]ed|approved|pre-?approved|said it'?s? (ok|fine))\b"),
    ("claims authority", r"\b(test|debug|maintenance|developer|god|jailbreak)\s*mode\b"),
    ("asks for secrets", r"\b(password|passcode|api[ _-]?key|secret|token|2fa|two[- ]factor|backup code|recovery code|credentials?|login details)\b.{0,40}\b(send|share|give|paste|provide|enter|reveal|tell|type)\b"),
    ("asks for secrets", r"\b(send|share|give|paste|provide|enter|reveal|tell|type)\b.{0,40}\b(password|passcode|api[ _-]?key|secret|token|2fa|backup code|recovery code|credentials?)\b"),
    ("asks for secrets", r"\b(config|credentials?)\b.{0,15}\b(folder|file|json)\b"),
]
_COMPILED = [(k, re.compile(p, re.I | re.S)) for k, p in PATTERNS]


def scan(text: str) -> list[str]:
    """Return the kinds of red flag found in text (empty if none)."""
    if not text:
        return []
    found = []
    for kind, rx in _COMPILED:
        if kind not in found and rx.search(text):
            found.append(kind)
    return found


def record(source: str, who: str, text: str, kinds: list[str],
           extra: dict | None = None) -> None:
    entry = {
        "when": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "source": source,
        "who": who,
        "kinds": kinds,
        "text": (text or "")[:4000],
    }
    if extra:
        entry.update(extra)
    with _lock:
        with open(SUSPICIOUS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def check(source: str, who: str, *texts: str) -> list[str]:
    """Scan every text; record one Suspicious entry if any is flagged."""
    kinds = []
    joined = "\n---\n".join(t for t in texts if t)
    for k in scan(joined):
        if k not in kinds:
            kinds.append(k)
    if kinds:
        record(source, who, joined, kinds)
    return kinds


def recent(limit: int = 50) -> list[dict]:
    if not SUSPICIOUS_FILE.exists():
        return []
    lines = SUSPICIOUS_FILE.read_text(encoding="utf-8").splitlines()
    out = []
    for ln in lines[-limit:]:
        try:
            out.append(json.loads(ln))
        except ValueError:
            continue
    return list(reversed(out))
