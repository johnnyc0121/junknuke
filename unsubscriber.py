#!/usr/bin/env python3
"""
Outlook Junk Mail Unsubscriber — Microsoft Graph REST API version
Uses a local browser redirect for OAuth2 (no device code flow needed),
then reads your Junk folder via Graph API and unsubscribes from mailing lists.
"""

import json
import logging
import re
import smtplib
import threading
import time
import urllib.parse
import webbrowser
import argparse
import requests

from datetime import datetime, timedelta, timezone
from email.mime.text import MIMEText
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import config

# ── Logging ───────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(config.LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── OAuth2 constants ──────────────────────────────────────────────────────────

AUTHORITY     = "https://login.microsoftonline.com/consumers/oauth2/v2.0"
REDIRECT_URI  = "http://localhost:8765/callback"
SCOPES        = "https://graph.microsoft.com/Mail.ReadWrite https://graph.microsoft.com/Mail.Send offline_access"
GRAPH_BASE    = "https://graph.microsoft.com/v1.0"

# ── Token management ──────────────────────────────────────────────────────────

def save_tokens(tokens: dict):
    with open(config.TOKEN_FILE, "w") as f:
        json.dump(tokens, f, indent=2)

def load_tokens() -> dict | None:
    if Path(config.TOKEN_FILE).exists():
        with open(config.TOKEN_FILE) as f:
            return json.load(f)
    return None

def refresh_tokens(refresh_token: str) -> dict | None:
    resp = requests.post(f"{AUTHORITY}/token", data={
        "client_id":     config.CLIENT_ID,
        "grant_type":    "refresh_token",
        "refresh_token": refresh_token,
        "redirect_uri":  REDIRECT_URI,
        "scope":         SCOPES,
    })
    if resp.ok and "access_token" in resp.json():
        tokens = resp.json()
        save_tokens(tokens)
        log.info("Token refreshed successfully.")
        return tokens
    log.warning(f"Token refresh failed: {resp.text}")
    return None

# ── Local browser OAuth2 flow ─────────────────────────────────────────────────

class _CallbackHandler(BaseHTTPRequestHandler):
    auth_code = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)
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
            self.wfile.write(b"Missing auth code.")

    def log_message(self, format, *args):
        pass  # suppress server request logs


def browser_auth_flow() -> dict:
    """Open a browser for login, catch the redirect locally, exchange for tokens."""

    auth_url = (
        f"{AUTHORITY}/authorize"
        f"?client_id={config.CLIENT_ID}"
        f"&response_type=code"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI)}"
        f"&scope={urllib.parse.quote(SCOPES)}"
        f"&response_mode=query"
        f"&prompt=select_account"
    )

    # Start local callback server in a background thread
    server = HTTPServer(("localhost", 8765), _CallbackHandler)
    thread = threading.Thread(target=server.handle_request)
    thread.daemon = True
    thread.start()

    print("\n" + "=" * 60)
    print("Opening browser for Microsoft sign-in...")
    print("Sign in with your HOTMAIL/OUTLOOK account (Account B).")
    print("\nIf the browser doesn't open automatically, go to:")
    print(f"  {auth_url}")
    print("=" * 60 + "\n")

    webbrowser.open(auth_url)

    # Wait for the callback
    deadline = time.time() + 120
    while _CallbackHandler.auth_code is None and time.time() < deadline:
        time.sleep(0.5)

    server.server_close()

    if not _CallbackHandler.auth_code:
        raise RuntimeError("Timed out waiting for browser sign-in.")

    # Exchange code for tokens
    resp = requests.post(f"{AUTHORITY}/token", data={
        "client_id":    config.CLIENT_ID,
        "grant_type":   "authorization_code",
        "code":         _CallbackHandler.auth_code,
        "redirect_uri": REDIRECT_URI,
        "scope":        SCOPES,
    })
    resp.raise_for_status()
    tokens = resp.json()
    if "access_token" not in tokens:
        raise RuntimeError(f"Token exchange failed: {tokens}")

    save_tokens(tokens)
    log.info("Authentication successful — tokens saved.")
    return tokens


def get_access_token() -> str:
    tokens = load_tokens()
    if tokens:
        refreshed = refresh_tokens(tokens.get("refresh_token", ""))
        if refreshed:
            return refreshed["access_token"]
        log.warning("Refresh failed — re-authenticating.")
    tokens = browser_auth_flow()
    return tokens["access_token"]

# ── Graph API helpers ─────────────────────────────────────────────────────────

def graph_get(path: str, access_token: str, params: dict = None) -> dict:
    resp = requests.get(
        f"{GRAPH_BASE}{path}",
        headers={"Authorization": f"Bearer {access_token}"},
        params=params,
    )
    resp.raise_for_status()
    return resp.json()

def get_junk_messages(access_token: str, min_age_days: int):
    """Yield message dicts from the Junk Email folder."""
    cutoff = (datetime.now(timezone.utc) - timedelta(days=min_age_days)).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    url = f"{GRAPH_BASE}/me/mailFolders/junkemail/messages"
    params = {
        "$select": "id,subject,from,internetMessageHeaders,receivedDateTime",
        "$filter": f"receivedDateTime lt {cutoff}",
        "$top": 50,
        "$orderby": "receivedDateTime asc",
    }
    headers = {"Authorization": f"Bearer {access_token}"}

    while url:
        resp = requests.get(url, headers=headers, params=params)
        resp.raise_for_status()
        data = resp.json()
        for msg in data.get("value", []):
            yield msg
        url = data.get("@odata.nextLink")
        params = None  # nextLink already contains params

# ── Unsubscribe helpers ───────────────────────────────────────────────────────

def get_header(msg: dict, name: str) -> str:
    """Extract a header value from the Graph message's internetMessageHeaders list."""
    name_lower = name.lower()
    for h in msg.get("internetMessageHeaders", []):
        if h.get("name", "").lower() == name_lower:
            return h.get("value", "")
    return ""

def extract_list_unsubscribe(msg: dict) -> dict:
    result = {"mailto": None, "http": None, "post_required": False}
    raw = get_header(msg, "List-Unsubscribe")
    if not raw:
        return result

    if "List-Unsubscribe=One-Click" in get_header(msg, "List-Unsubscribe-Post"):
        result["post_required"] = True

    for part in re.findall(r"<([^>]+)>", raw):
        part = part.strip()
        if part.startswith("mailto:"):
            result["mailto"] = part[len("mailto:"):]
        elif part.startswith("http"):
            result["http"] = part

    return result

def fetch_body_for_link(msg_id: str, access_token: str) -> str:
    """Fetch the full message body to scan for unsubscribe links."""
    try:
        data = graph_get(f"/me/messages/{msg_id}", access_token,
                         params={"$select": "body"})
        return data.get("body", {}).get("content", "")
    except Exception:
        return ""

def find_body_unsubscribe_link(body: str) -> str | None:
    patterns = [
        r'https?://[^\s<>"\']+unsubscribe[^\s<>"\']*',
        r'https?://[^\s<>"\']+opt[_-]?out[^\s<>"\']*',
        r'https?://[^\s<>"\']+remove[^\s<>"\']*',
    ]
    for pattern in patterns:
        matches = re.findall(pattern, body, re.IGNORECASE)
        if matches:
            return sorted(matches, key=len)[0]
    return None

def do_http_unsubscribe(url: str, post_required: bool, dry_run: bool) -> bool:
    if dry_run:
        log.info(f"  [DRY-RUN] Would {'POST' if post_required else 'GET'} {url[:80]}")
        return True
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; unsubscriber/1.0)"}
        if post_required:
            resp = requests.post(
                url,
                data="List-Unsubscribe=One-Click",
                headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
                timeout=15, allow_redirects=True,
            )
        else:
            resp = requests.get(url, headers=headers, timeout=15, allow_redirects=True)
        log.info(f"  HTTP {'POST' if post_required else 'GET'} → {resp.status_code} {url[:70]}")
        return resp.status_code < 400
    except Exception as e:
        log.warning(f"  HTTP unsubscribe failed: {e}")
        return False

def do_mailto_unsubscribe(mailto: str, access_token: str, dry_run: bool) -> bool:
    if "?" in mailto:
        addr, qs = mailto.split("?", 1)
        m = re.search(r"subject=([^&]+)", qs, re.IGNORECASE)
        subject = m.group(1).replace("+", " ") if m else "Unsubscribe"
        m = re.search(r"body=([^&]+)", qs, re.IGNORECASE)
        body = m.group(1).replace("+", " ") if m else "Please unsubscribe me."
    else:
        addr, subject, body = mailto, "Unsubscribe", "Please unsubscribe me."

    if dry_run:
        log.info(f"  [DRY-RUN] Would email {addr} | Subject: {subject}")
        return True

    try:
        # Send via Graph API (no SMTP needed)
        payload = {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": addr}}],
            },
            "saveToSentItems": False,
        }
        resp = requests.post(
            f"{GRAPH_BASE}/me/sendMail",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            json=payload,
        )
        resp.raise_for_status()
        log.info(f"  Unsubscribe email sent to {addr}")
        return True
    except Exception as e:
        log.warning(f"  mailto unsubscribe failed: {e}")
        return False

# ── Processed cache ───────────────────────────────────────────────────────────

def load_processed() -> set:
    if Path(config.PROCESSED_FILE).exists():
        with open(config.PROCESSED_FILE) as f:
            return set(json.load(f))
    return set()

def save_processed(ids: set):
    with open(config.PROCESSED_FILE, "w") as f:
        json.dump(list(ids), f, indent=2)

# ── Allowlist ─────────────────────────────────────────────────────────────────

def is_allowlisted(msg: dict) -> bool:
    sender = msg.get("from", {}).get("emailAddress", {}).get("address", "")
    return any(term.lower() in sender.lower() for term in config.ALLOWLIST)

# ── Main ──────────────────────────────────────────────────────────────────────

def run(dry_run: bool, min_age_days: int, limit: int | None):
    log.info(f"=== Run started | dry_run={dry_run} | min_age_days={min_age_days} ===")

    access_token = get_access_token()
    processed    = load_processed()
    processed    = load_processed()

    stats = {"seen": 0, "skipped_processed": 0, "skipped_allowlist": 0,
             "no_unsub": 0, "success": 0, "failed": 0}
    count = 0

    for msg in get_junk_messages(access_token, min_age_days):
        msg_id  = msg["id"]
        subject = msg.get("subject", "(no subject)")
        sender  = msg.get("from", {}).get("emailAddress", {}).get("address", "(unknown)")
        stats["seen"] += 1

        if msg_id in processed:
            stats["skipped_processed"] += 1
            continue

        if limit and count >= limit:
            break

        if is_allowlisted(msg):
            log.info(f"ALLOWLISTED  | {sender}")
            stats["skipped_allowlist"] += 1
            processed.add(msg_id)
            continue

        log.info(f"Processing   | {sender[:55]} | {subject[:45]}")
        unsub   = extract_list_unsubscribe(msg)
        success = False

        if unsub["http"] and unsub["post_required"]:
            success = do_http_unsubscribe(unsub["http"], post_required=True, dry_run=dry_run)
        elif unsub["http"]:
            success = do_http_unsubscribe(unsub["http"], post_required=False, dry_run=dry_run)
        elif unsub["mailto"]:
            success = do_mailto_unsubscribe(unsub["mailto"], access_token, dry_run=dry_run)
        else:
            # Fallback: fetch full body and scan for links
            body = fetch_body_for_link(msg_id, access_token)
            link = find_body_unsubscribe_link(body)
            if link:
                log.info(f"  Body fallback: {link[:80]}")
                success = do_http_unsubscribe(link, post_required=False, dry_run=dry_run)
            else:
                if config.DELETE_IF_NO_UNSUB:
                    try:
                        requests.delete(
                            f"{GRAPH_BASE}/me/messages/{msg_id}",
                            headers={"Authorization": f"Bearer {access_token}"},
                        )
                        log.info("  No unsub found — deleted.")
                        stats["no_unsub"] += 1
                        processed.add(msg_id)
                    except Exception as e:
                        log.warning(f"  Delete failed: {e}")
                else:
                    log.info("  No unsubscribe mechanism found.")
                    stats["no_unsub"] += 1
                    processed.add(msg_id)
                continue

        if success:
            stats["success"] += 1
            processed.add(msg_id)
            if config.DELETE_AFTER_UNSUB:
                try:
                    requests.delete(
                        f"{GRAPH_BASE}/me/messages/{msg_id}",
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    log.info("  Deleted from Junk.")
                except Exception as e:
                    log.warning(f"  Delete failed: {e}")
            time.sleep(config.REQUEST_DELAY_SECONDS)
        else:
            stats["failed"] += 1
            if config.DELETE_AFTER_UNSUB:
                try:
                    requests.delete(
                        f"{GRAPH_BASE}/me/messages/{msg_id}",
                        headers={"Authorization": f"Bearer {access_token}"},
                    )
                    log.info("  Deleted from Junk (failed unsub).")
                except Exception as e:
                    log.warning(f"  Delete failed: {e}")

        count += 1

    if not dry_run:
            save_processed(processed)
    else:
        log.info("(dry-run: processed cache not updated)")

    log.info("=== Run complete ===")
    log.info(f"  Seen:               {stats['seen']}")
    log.info(f"  Already processed:  {stats['skipped_processed']}")
    log.info(f"  Allowlisted:        {stats['skipped_allowlist']}")
    log.info(f"  No unsub found:     {stats['no_unsub']}")
    log.info(f"  Unsubscribed (ok):  {stats['success']}")
    log.info(f"  Failed:             {stats['failed']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Outlook Junk Mail Unsubscriber")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without actually unsubscribing")
    parser.add_argument("--min-age", type=int, default=config.MIN_AGE_DAYS,
                        help="Only process emails older than N days (default: from config)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max number of emails to process in this run")
    args = parser.parse_args()

    run(dry_run=args.dry_run, min_age_days=args.min_age, limit=args.limit)
