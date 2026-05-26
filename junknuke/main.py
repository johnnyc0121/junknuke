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
import json
import logging
import os
import time
from pathlib import Path

from junknuke import settings
from junknuke.utils.graph import browser_auth, get_access_token, get_junk_messages
from junknuke.utils.unsubscribe import (
    extract_list_unsubscribe,
    find_body_unsubscribe_link,
    do_http_unsubscribe,
    do_mailto_unsubscribe,
    delete_message,
    is_allowlisted,
)
from junknuke.utils.geotrack import track_email
from junknuke.utils.influxdb import write_to_influxdb

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

# ── Single run ────────────────────────────────────────────────────────────────

def run_once(dry_run: bool, min_age_days: int, limit: int | None):
    log.info(f"=== Run started | dry_run={dry_run} | min_age_days={min_age_days} ===")

    access_token = get_access_token()
    processed    = load_processed()

    stats = {
        "seen": 0, "skipped_processed": 0, "skipped_allowlist": 0,
        "no_unsub": 0, "success": 0, "failed": 0,
    }
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

        # Geo-track source IP
        if settings.ENABLE_GEOTRACK and not dry_run:
            geo_data = track_email(msg)
            if geo_data:
                write_to_influxdb(geo_data)

        # Unsubscribe
        unsub   = extract_list_unsubscribe(msg)
        success = False

        if unsub["http"] and unsub["post_required"]:
            success = do_http_unsubscribe(unsub["http"], post_required=True, dry_run=dry_run)
        elif unsub["http"]:
            success = do_http_unsubscribe(unsub["http"], post_required=False, dry_run=dry_run)
        elif unsub["mailto"]:
            success = do_mailto_unsubscribe(unsub["mailto"], access_token, dry_run=dry_run)
        else:
            link = find_body_unsubscribe_link(msg_id, access_token)
            if link:
                log.info(f"  Body fallback: {link[:80]}")
                success = do_http_unsubscribe(link, post_required=False, dry_run=dry_run)
            else:
                log.info("  No unsubscribe mechanism found.")
                stats["no_unsub"] += 1
                if settings.DELETE_IF_NO_UNSUB:
                    delete_message(msg_id, access_token, dry_run)
                processed.add(msg_id)
                continue

        if success:
            stats["success"] += 1
        else:
            stats["failed"] += 1

        # Delete regardless of unsub success/failure
        if settings.DELETE_AFTER_UNSUB:
            delete_message(msg_id, access_token, dry_run)

        processed.add(msg_id)
        count += 1
        time.sleep(settings.REQUEST_DELAY_SECONDS)

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
