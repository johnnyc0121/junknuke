#!/usr/bin/env python3
"""
main.py — JunkNuke entrypoint.

Usage:
  # First-time auth on host (generates data/token.json):
  python -m junknuke.main --auth-only

  # Normal run:
  python -m junknuke.main [--dry-run] [--min-age N] [--limit N] [--no-loop]

  # In Docker (via docker compose):
  CMD ["python", "-m", "junknuke.main"]
"""

import argparse
import importlib
import json
import logging
import os
import time
from pathlib import Path

from junknuke import settings
from junknuke.providers.microsoft.msgraph import browser_auth, get_access_token, get_junk_messages
from junknuke.providers.microsoft.unsubscribe import (
    extract_list_unsubscribe,
    find_body_unsubscribe_link,
    do_http_unsubscribe,
    do_mailto_unsubscribe,
    delete_message,
    is_allowlisted,
)
from junknuke.utils.geotrack import track_email
from junknuke.utils.influxdb import write_msgs_to_influxdb, write_stats_to_influxdb

PROVIDER_MAP = {
    "microsoft": "junknuke.providers.microsoft",
    "google":    "junknuke.providers.google",
    "yahoo":     "junknuke.providers.yahoo",
}

# ── Logging ───────────────────────────────────────────────────────────────────

Path(settings.DATA_DIR).mkdir(parents=True, exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s  %(message)s",
    handlers=[
        logging.FileHandler(settings.LOG_FILE),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── Processed cache ───────────────────────────────────────────────────────────

def load_processed() -> set:
    p = Path(settings.PROCESSED_FILE)
    if p.exists():
        with open(p) as f:
            return set(json.load(f))
    return set()

def save_processed(ids: set):
    with open(settings.PROCESSED_FILE, "w") as f:
        json.dump(list(ids), f, indent=2)

# ── Run provider ────────────────────────────────────────────────────────────────

def run_provider(email: str, provider: str):
    module_path = PROVIDER_MAP.get(provider)
    if not module_path:
        log.error("Unknown provider '%s' for account %s", provider, email)
        return

    try:
        module = importlib.import_module(module_path)
        module.run(email)
    except NotImplementedError:
        log.warning("Provider '%s' not yet implemented — skipping %s", provider, email)
    except Exception as e:
        log.error("Provider '%s' failed for %s: %s", provider, email, e, exc_info=True)

# ── Single run ────────────────────────────────────────────────────────────────

def run_once(dry_run: bool, min_age_days: int, limit: int | None):
    log.info(f"=== Run started | dry_run={dry_run} | min_age_days={min_age_days} ===")

    all_stats = {}

    for email, provider in settings.ACCOUNTS.items():
        log.info("=== Processing %s via %s ===", email, provider)
        try:
            stats = run_provider(
                email=email,
                provider=provider,
                dry_run=dry_run,
                min_age_days=min_age_days,
                limit=limit,
            )
            all_stats[email] = stats
        except Exception as e:
            log.error("Failed processing %s: %s", email, e, exc_info=True)

    # Write stats to InfluxDB for each account
    for email, stats in all_stats.items():
        write_stats_to_influxdb(stats, email=email)

# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="JunkNuke — Outlook junk mail unsubscriber")
    parser.add_argument("--auth-only", action="store_true",
                        help="Authenticate via browser and save token, then exit")
    parser.add_argument("--dry-run", action="store_true",
                        help="Show what would happen without making changes")
    parser.add_argument("--min-age", type=int, default=settings.MIN_AGE_DAYS,
                        help="Only process emails older than N days")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max emails to process per run")
    parser.add_argument("--no-loop", action="store_true",
                        help="Run once and exit (default in Docker is to loop)")
    args = parser.parse_args()

    # First-time auth — run on host, not in Docker
    if args.auth_only:
        log.info("Starting browser authentication flow...")
        browser_auth()
        log.info(f"Token saved to {settings.TOKEN_FILE} — you can now start Docker.")
        return

    # In Docker: loop forever. Local dev: run once.
    in_docker = os.path.exists("/.dockerenv")
    loop      = in_docker and not args.no_loop

    if loop:
        log.info(f"Running in Docker — looping every {settings.RUN_INTERVAL}s")
        while True:
            try:
                run_once(
                    dry_run=args.dry_run,
                    min_age_days=args.min_age,
                    limit=args.limit,
                )
            except Exception as e:
                log.error(f"Run failed: {e}", exc_info=True)
            log.info(f"Sleeping {settings.RUN_INTERVAL}s until next run...")
            time.sleep(settings.RUN_INTERVAL)
    else:
        run_once(
            dry_run=args.dry_run,
            min_age_days=args.min_age,
            limit=args.limit,
        )


if __name__ == "__main__":
    main()
