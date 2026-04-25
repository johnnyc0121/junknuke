# config.py — Edit this file before running unsubscriber.py

# ── Your Hotmail/Outlook address (Account B — the junk account) ───────────────
EMAIL_ADDRESS = ""      # ← change this

# ── Azure app Client ID (from your JunkUnsubscriber app registration) ─────────
CLIENT_ID = ""     # ← change this


# ── Behaviour ─────────────────────────────────────────────────────────────────

# Only process emails older than this many days
MIN_AGE_DAYS = 0

# Seconds to wait between unsubscribe requests
REQUEST_DELAY_SECONDS = 2

# Delete emails from junk folder if no unsubscribe mechanism is found
DELETE_IF_NO_UNSUB = True

# Delete email from junk after a successful unsubscribe attempt
DELETE_AFTER_UNSUB = True

# ── Senders / domains to never unsubscribe from ───────────────────────────────
ALLOWLIST = [
    # "newsletter@companyyoulike.com",
    # "updates@bank.com",
]

# ── File paths ────────────────────────────────────────────────────────────────
LOG_FILE        = "unsubscriber.log"
PROCESSED_FILE  = "processed.json"
TOKEN_FILE      = "token.json"         # keep this private — treat like a password
