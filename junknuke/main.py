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

# ── Run provider ───────────────────────────────────────────────────────────────
def run_provider(email: str, provider: str, dry_run: bool, min_age_days: int, limit: int | None):
    module_path = PROVIDER_MAP.get(provider)
    if not module_path:
        log.error("Unknown provider '%s' for account %s", provider, email)
        return

    try:
        module = importlib.import_module(module_path)
        result = module.run(email=email, dry_run=dry_run, min_age_days=min_age_days, limit=limit)
        stats = result["stats"]
        write_stats_to_influxdb(stats, email=email, provider=provider)
        geo_messages = result["geo_messages"]
        if geo_messages:
            for geo_data in geo_messages:
                write_msgs_to_influxdb(geo_data, email=email, provider=provider)
    except NotImplementedError:
        log.warning("Provider '%s' not yet implemented — skipping %s", provider, email)
    except Exception as e:
        log.error("Provider '%s' failed for %s: %s", provider, email, e, exc_info=True)

# ── Single run ────────────────────────────────────────────────────────────────

def run_once(dry_run: bool, min_age_days: int, limit: int | None):

    for email, provider in settings.ACCOUNTS.items():
        log.info(f"=== Run started | email={email} | provider={provider} | dry_run={dry_run} | min_age_days={min_age_days} ===")
        try:
            run_provider(
                email=email,
                provider=provider,
                dry_run=dry_run,      
                min_age_days=min_age_days,
                limit=limit,
            )
        except Exception as e:
            log.error("Failed processing %s: %s", email, e, exc_info=True)        

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

    run_kwargs = dict(
        dry_run=args.dry_run,
        min_age_days=args.min_age,
        limit=args.limit,
    )

    if loop:
        log.info(f"Running in Docker — looping every {settings.RUN_INTERVAL}s")
        while True:
            try:
                run_once(**run_kwargs)
            except Exception as e:
                log.error(f"Run failed: {e}", exc_info=True)
            log.info(f"Sleeping {settings.RUN_INTERVAL}s until next run...")
            time.sleep(settings.RUN_INTERVAL)
    else:
        run_once(**run_kwargs)

if __name__ == "__main__":
    main()
