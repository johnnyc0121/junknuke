"""
unsubscribe.py — unsubscribe mechanisms for JunkNuke.
Supports HTTP POST (RFC 8058), HTTP GET, mailto, and body link fallback.
"""

import logging
import re

import requests

from junknuke import settings
from junknuke.providers.microsoft.msgraph import graph_post, graph_delete, graph_get, GRAPH_BASE

log = logging.getLogger(__name__)

# ── Header parsing ────────────────────────────────────────────────────────────

def get_header(msg: dict, name: str) -> str:
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

def find_body_unsubscribe_link(msg_id: str, access_token: str) -> str | None:
    """Fetch the full message body and scan for unsubscribe URLs."""
    try:
        data = graph_get(f"/me/messages/{msg_id}", access_token,
                         params={"$select": "body"})
        body = data.get("body", {}).get("content", "")
    except Exception:
        return None

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

# ── Unsubscribe actions ───────────────────────────────────────────────────────

def do_http_unsubscribe(url: str, post_required: bool, dry_run: bool) -> bool:
    if dry_run:
        log.info(f"  [DRY-RUN] Would {'POST' if post_required else 'GET'} {url[:80]}")
        return True
    try:
        headers = {"User-Agent": "Mozilla/5.0 (compatible; junknuke/1.0)"}
        if post_required:
            resp = requests.post(
                url,
                data="List-Unsubscribe=One-Click",
                headers={**headers, "Content-Type": "application/x-www-form-urlencoded"},
                timeout=15,
                allow_redirects=True,
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
        graph_post("/me/sendMail", access_token, {
            "message": {
                "subject": subject,
                "body": {"contentType": "Text", "content": body},
                "toRecipients": [{"emailAddress": {"address": addr}}],
            },
            "saveToSentItems": False,
        })
        log.info(f"  Unsubscribe email sent to {addr}")
        return True
    except Exception as e:
        log.warning(f"  mailto unsubscribe failed: {e}")
        return False

def delete_message(msg_id: str, access_token: str, dry_run: bool):
    if dry_run:
        log.info("  [DRY-RUN] Would delete message.")
        return
    try:
        graph_delete(f"/me/messages/{msg_id}", access_token)
        log.info("  Deleted from Junk.")
    except Exception as e:
        log.warning(f"  Delete failed: {e}")

# ── Allowlist ─────────────────────────────────────────────────────────────────

def is_allowlisted(msg: dict) -> bool:
    sender = msg.get("from", {}).get("emailAddress", {}).get("address", "")
    return any(term.lower() in sender.lower() for term in settings.ALLOWLIST)
