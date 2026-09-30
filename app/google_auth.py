"""Google sign-in for the app (Sheets, Drive read, Docs read).

The app has its own OAuth client ("Control Room", a Desktop client in
Sam' Google Cloud project your-google-cloud-project). Its downloaded JSON
lives only in Control Room\\config\\google_client.json. The uploader's
config folder is never read (the Ward's fence). Nothing here is printed or
logged. The refresh token is saved in config\\google_token.json without the
client secret.
"""
import json

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

from . import paths

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly",
    "https://www.googleapis.com/auth/drive.file",
    "https://www.googleapis.com/auth/documents.readonly",
]
CLIENT_FILE = paths.CONFIG / "google_client.json"
OWN_CLIENT_ID = "YOUR-OAUTH-CLIENT-ID"
TOKEN_FILE = paths.CONFIG / "google_token.json"
_creds = None


def adopt_downloaded_client() -> bool:
    """If Sam has just downloaded the client JSON (client_secret_*.json)
    into Downloads, move it into config\\. Called only right after he makes it."""
    if has_client():
        return True
    # Only the Control Room's own client; never the uploader's older one.
    for f in sorted(paths.DOWNLOADS.glob("client_secret_*.json"),
                    key=lambda p: p.stat().st_mtime, reverse=True):
        if OWN_CLIENT_ID not in f.name:
            continue
        d = json.loads(f.read_text(encoding="utf-8"))
        if d.get("installed", {}).get("client_secret"):
            CLIENT_FILE.write_text(json.dumps(d), encoding="utf-8")
            f.unlink()   # the only copy now lives in config\
            return True
    return False


def has_client() -> bool:
    if not CLIENT_FILE.exists():
        return False
    d = json.loads(CLIENT_FILE.read_text(encoding="utf-8")).get("installed", {})
    return bool(d.get("client_id") and d.get("client_secret"))


def _client() -> dict:
    d = json.loads(CLIENT_FILE.read_text(encoding="utf-8"))["installed"]
    return {"client_id": d["client_id"], "client_secret": d["client_secret"],
            "token_uri": d.get("token_uri", "https://oauth2.googleapis.com/token")}


def _save(creds: Credentials) -> None:
    TOKEN_FILE.write_text(json.dumps({
        "token": creds.token, "refresh_token": creds.refresh_token,
        "scopes": list(creds.scopes or SCOPES),
        "expiry": creds.expiry.isoformat() if creds.expiry else None,
    }), encoding="utf-8")


def credentials(interactive: bool = False):
    """Return working credentials, or None if Sam has not signed in yet."""
    global _creds
    if _creds and _creds.valid:
        return _creds
    if not has_client():
        return None
    c = _client()
    if TOKEN_FILE.exists():
        d = json.loads(TOKEN_FILE.read_text(encoding="utf-8"))
        creds = Credentials(token=d.get("token"),
                            refresh_token=d.get("refresh_token"),
                            token_uri=c["token_uri"], client_id=c["client_id"],
                            client_secret=c["client_secret"],
                            scopes=d.get("scopes") or SCOPES)
        try:
            if not creds.valid:
                creds.refresh(Request())
                _save(creds)
            _creds = creds
            return creds
        except Exception:  # noqa: BLE001 - expired or revoked: sign in again
            if not interactive:
                return None
    if not interactive:
        return None
    flow = InstalledAppFlow.from_client_config(
        {"installed": {"client_id": c["client_id"],
                       "client_secret": c["client_secret"],
                       "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                       "token_uri": c["token_uri"],
                       "redirect_uris": ["http://localhost"]}},
        SCOPES)
    creds = flow.run_local_server(
        port=0, open_browser=True,
        authorization_prompt_message="",
        success_message="Signed in. You can close this tab and go back to "
                        "the Control Room.")
    _save(creds)
    _creds = creds
    return creds


def connected() -> bool:
    return credentials() is not None


_sheets_svc = None
_sheets_svc_creds = None
_drive_svc = None
_drive_svc_creds = None


def sheets():
    global _sheets_svc, _sheets_svc_creds
    creds = credentials()
    if _sheets_svc is None or _sheets_svc_creds is not creds:
        from googleapiclient.discovery import build
        _sheets_svc = build("sheets", "v4", credentials=creds, cache_discovery=False)
        _sheets_svc_creds = creds
    return _sheets_svc


def drive():
    global _drive_svc, _drive_svc_creds
    creds = credentials()
    if _drive_svc is None or _drive_svc_creds is not creds:
        from googleapiclient.discovery import build
        _drive_svc = build("drive", "v3", credentials=creds, cache_discovery=False)
        _drive_svc_creds = creds
    return _drive_svc


if __name__ == "__main__":
    credentials(interactive=True)
    print("google sign-in saved")
