"""Antivirus health light. This does not scan anything; it asks Windows
Defender whether real-time protection is on and its definitions are current.
"""
import json
import subprocess
import time

_cache = {"at": 0, "value": None}


def status() -> dict:
    if _cache["value"] and time.time() - _cache["at"] < 300:
        return _cache["value"]
    cmd = ("Get-MpComputerStatus | Select-Object RealTimeProtectionEnabled,"
           "AntivirusEnabled,AntivirusSignatureAge,"
           "@{n='Updated';e={$_.AntivirusSignatureLastUpdated.ToString('d MMM yyyy h:mm tt')}}"
           " | ConvertTo-Json")
    try:
        out = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", cmd],
            capture_output=True, text=True, timeout=40,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        d = json.loads(out.stdout)
        rtp = bool(d.get("RealTimeProtectionEnabled"))
        age = d.get("AntivirusSignatureAge")
        fresh = age is not None and int(age) <= 3
        ok = rtp and bool(d.get("AntivirusEnabled")) and fresh
        if ok:
            words = "Defender is on and its definitions are current."
            action = ""
        elif not rtp:
            words = "Defender's real-time protection is OFF."
            action = ("Open Windows Security and switch Real-time protection "
                      "back on.")
        else:
            words = f"Defender's definitions are {age} days old."
            action = "Open Windows Security and click Check for updates."
        value = {"ok": ok, "words": words, "action": action,
                 "updated": d.get("Updated"), "age_days": age,
                 "source": "Windows Defender (Get-MpComputerStatus)"}
    except Exception as e:  # noqa: BLE001 - show the light as unknown
        value = {"ok": False, "words": "Could not read Defender's status.",
                 "action": "Tell Claude the Ward light is grey.",
                 "updated": None, "age_days": None, "error": str(e)[:200],
                 "source": "Windows Defender (Get-MpComputerStatus)"}
    _cache.update(at=time.time(), value=value)
    return value
