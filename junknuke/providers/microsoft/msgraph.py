"""
graph.py — Microsoft Graph API authentication and helpers.

Auth flow:
  - First run (host):  python -m junknuke.main --auth-only
                       Opens a browser, saves token.json to data/
  - Subsequent runs:   token.json is refreshed automatically.
  - In Docker:         token.json is mounted as a volume.
                       The container never needs a browser.
"""

import base64
import json
import logging
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import requests

from junknuke import settings

log = logging.getLogger(__name__)

AUTHORITY    = "https://login.microsoftonline.com/consumers"
REDIRECT_URI = "http://localhost:8765/callback"
SCOPES = "https://graph.microsoft.com/Mail.ReadWrite https://graph.microsoft.com/Mail.Send https://graph.microsoft.com/User.Read offline_access"
GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# ── Token management ──────────────────────────────────────────────────────────

# ── Token management ──────────────────────────────────────────────────────────

def _save_tokens(tokens: dict):
    Path(settings.TOKEN_FILE).parent.mkdir(parents=True, exist_ok=True)
    with open(settings.TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)

def _load_tokens() -> dict | None:
    p = Path(settings.TOKEN_FILE)
    if p.exists():
        with open(p) as f:
            return json.load(f)
    return None

def _refresh(refresh_token: str) -> dict | None:
    resp = requests.post(f"{AUTHORITY}/oauth2/v2.0/token", data={
        "client_id":     settings.AZURE_CLIENT_ID,
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
        "redirect_uri":  REDIRECT_URI,
        "scope":         SCOPES,
    }, timeout=30)
    if resp.ok and "access_token" in resp.json():
        tokens = resp.json()
        _save_tokens(tokens)
        log.info("Access token refreshed.")
        return tokens
    log.warning(f"Token refresh failed: {resp.text[:200]}")
    return None

# ── Browser auth flow (host only, first run) ──────────────────────────────────

class _CallbackHandler(BaseHTTPRequestHandler):
    auth_code = None

    def do_GET(self):
        params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
        if "code" in params:
            _CallbackHandler.auth_code = params["code"][0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"""
                <html><body style='font-family:sans-serif;padding:40px'>
                <h2>&#10003; Authenticated successfully!</h2>
                <p>You can close this window and return to the terminal.</p>
                </body></html>
            """)
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, *args):
        pass


def browser_auth() -> dict:
    """Interactive browser login. Only needed on first run on the host."""
    auth_url = (
        f"{AUTHORITY}/oauth2/v2.0/authorize"
        f"?client_id={settings.AZURE_CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope={urllib.parse.quote(SCOPES)}"
        f"&response_mode=query"
        f"&prompt=select_account"
    )

    server = HTTPServer(("localhost", 8765), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request, daemon=True)
    thread.start()

    print("\n" + "=" * 60)
    print("Opening browser for Microsoft sign-in...")
    print("Sign in with your HOTMAIL/OUTLOOK account.")
    print("\nIf the browser does not open, visit:")
    print(f"  {auth_url}")
    print("=" * 60 + "\n")

    webbrowser.open(auth_url)

    deadline = time.time() + 120
    while _CallbackHandler.auth_code is None and time.time() < deadline:
        time.sleep(0.5)
    server.server_close()

    if not _CallbackHandler.auth_code:
        raise RuntimeError("Timed out waiting for browser sign-in.")

    resp = requests.post(f"{AUTHORITY}/oauth2/v2.0/token", data={
        "client_id":    settings.AZURE_CLIENT_ID,
        "grant_type":   "authorization_code",
        "code":         _CallbackHandler.auth_code,
        "redirect_uri": REDIRECT_URI,
        "scope":        SCOPES
    }, timeout=30)
    print(resp.json())
    resp.raise_for_status()
    tokens = resp.json()
    if "access_token" not in tokens:
        raise RuntimeError(f"Token exchange failed: {tokens}")

    _save_tokens(tokens)
    log.info("Authentication successful — token saved to %s", settings.TOKEN_FILE)
    return tokens


def get_access_token() -> str:
    """Return a valid access token, refreshing silently if needed."""
    tokens = _load_tokens()
    if tokens:
        refreshed = _refresh(tokens.get("refresh_token", ""))
        if refreshed:
            return refreshed["access_token"]
        log.warning("Silent refresh failed — manual re-authentication required.")
        log.warning("Run: python -m junknuke.main --auth-only")
        raise RuntimeError("Token expired. Re-authenticate on the host with --auth-only.")
    raise RuntimeError(
        f"No token found at {settings.TOKEN_FILE}. "
        "Run: python -m junknuke.main --auth-only"
    )

# ── Graph API helpers ─────────────────────────────────────────────────────────

def graph_get(path: str, access_token: str, params: dict = None) -> dict:
    resp = requests.get(
        f"{GRAPH_BASE}{path}",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()

def graph_delete(path: str, access_token: str):
    resp = requests.delete(
        f"{GRAPH_BASE}{path}",
        headers={"Authorization": f"Bearer {access_token}"},
        timeout=30,
    )
    resp.raise_for_status()

def graph_post(path: str, access_token: str, payload: dict):
    resp = requests.post(
        f"{GRAPH_BASE}{path}",
        headers={
            "Authorization": f"Bearer {access_token}",
            "Content-Type":  "application/json",
        },
        json=payload,
        timeout=30,
    )
    resp.raise_for_status()
    return resp

def get_junk_messages(access_token: str, min_age_days: int):
    """Yield message dicts from the Junk Email folder."""
    from datetime import datetime, timedelta, timezone
    cutoff = (datetime.now(timezone.utc) - timedelta(days=min_age_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )
    url    = f"{GRAPH_BASE}/me/mailFolders/junkemail/messages"
    params = {
        "$select": "id,subject,from,internetMessageHeaders,receivedDateTime",
        "$filter": f"receivedDateTime lt {cutoff}",
        "$top":    50,
        "$orderby": "receivedDateTime asc",
    }
    headers = {"Authorization": f"Bearer {access_token}"}

    while url:
        resp = requests.get(url, headers=headers, params=params, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        yield from data.get("value", [])
        url    = data.get("@odata.nextLink")
        params = None
