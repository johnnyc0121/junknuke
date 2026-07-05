"""
settings.py — reads all configuration from environment variables.
No secrets or personal data are stored in code or committed to git.
"""

import logging
import os
import toml

log = logging.getLogger(__name__)

def _required(key: str) -> str:
    val = os.environ.get(key, "").strip()
    if not val:
        raise RuntimeError(f"Required environment variable '{key}' is not set.")
    return val


def _optional(key: str, default: str = "") -> str:
    return os.environ.get(key, default).strip()


def _bool(key: str, default: bool = False) -> bool:
    return os.environ.get(key, str(default)).lower() in ("true", "1", "yes")


def _int(key: str, default: int = 0) -> int:
    try:
        return int(os.environ.get(key, str(default)))
    except ValueError:
        return default

def parse_accounts() -> dict:
    """
    Parse MAIL_ACCOUNTS env var into a dict of email -> provider.
    Format: email:provider
    Multiple accounts are comma-separated.
    Example: MAIL_ACCOUNTS=jmwedding2005@hotmail.com:microsoft,name@gmail.com:google
    """
    raw = os.getenv("MAIL_ACCOUNTS", "").strip().strip('"').strip("'")
    accounts = {}

    for entry in raw.split(","):
        entry = entry.strip()
        if not entry or ":" not in entry:
            continue
        email, provider = entry.split(":", 1)
        email    = email.strip()
        provider = provider.strip().lower()
        accounts[email] = provider

    return accounts

ACCOUNTS = parse_accounts()


# ── Microsoft / Graph ─────────────────────────────────────────────────────────
AZURE_CLIENT_ID     = _optional("AZURE_CLIENT_ID", "")

# ── Behaviour ─────────────────────────────────────────────────────────────────
MIN_AGE_DAYS          = _int("MIN_AGE_DAYS", 7)
REQUEST_DELAY_SECONDS = _int("REQUEST_DELAY_SECONDS", 2)
DELETE_AFTER_UNSUB    = _bool("DELETE_AFTER_UNSUB", True)
DELETE_IF_NO_UNSUB    = _bool("DELETE_IF_NO_UNSUB", True)
RUN_INTERVAL          = _int("RUN_INTERVAL", 86400)   # seconds between runs (default: daily)

# Comma-separated list of sender addresses/domains to protect
_allowlist_raw = _optional("ALLOWLIST", "")
ALLOWLIST = [s.strip() for s in _allowlist_raw.split(",") if s.strip()]

# ── File paths (inside container: /app/data/) ─────────────────────────────────
DATA_DIR       = _optional("DATA_DIR", "data")
LOG_FILE       = os.path.join(DATA_DIR, "junknuke.log")
PROCESSED_FILE = os.path.join(DATA_DIR, "processed.json")
TOKEN_FILE     = os.path.join(DATA_DIR, "token.json")

# ── InfluxDB ──────────────────────────────────────────────────────────────────
ENABLE_GEOTRACK = _bool("ENABLE_GEOTRACK", True)

INFLUX_URL    = _optional("INFLUXDB_URL", "http://influxdb2:8086")
INFLUX_ORG    = _optional("INFLUXDB_ORG", "junknuke")
INFLUX_BUCKET = _optional("INFLUXDB_BUCKET", "junknuke")
INFLUX_MESSAGES_BUCKET = _optional("INFLUXDB_MESSAGES_BUCKET", "messages")
INFLUX_STATS_BUCKET    = _optional("INFLUXDB_STATS_BUCKET", "stats")
