import logging
import time

from junknuke import settings
from junknuke.utils.geotrack import track_email
from junknuke.utils.influxdb import write_msgs_to_influxdb
from junknuke.utils.processed import load_processed, save_processed

from .msgraph import get_access_token, get_junk_messages
from .unsubscribe import (
    extract_list_unsubscribe,
    find_body_unsubscribe_link,
    do_http_unsubscribe,
    do_mailto_unsubscribe,
    delete_message,
    is_allowlisted,
)

log = logging.getLogger(__name__)


def run(email: str, dry_run: bool, min_age_days: int, limit: int | None) -> dict:

    access_token = get_access_token()
    processed    = load_processed()

    stats = {
        "total": 0, "seen": 0, "skipped_processed": 0, "skipped_allowlist": 0,
        "no_unsub": 0, "success": 0, "failed": 0,
    }

    for msg in get_junk_messages(access_token, min_age_days):
        msg_id  = msg["id"]
        subject = msg.get("subject", "(no subject)")
        sender  = msg.get("from", {}).get("emailAddress", {}).get("address", "(unknown)")
        stats["seen"] += 1

        if msg_id in processed:
            stats["skipped_processed"] += 1
            continue

        if limit and stats["total"] >= limit:
            break

        if is_allowlisted(msg):
            log.info(f"ALLOWLISTED  | {sender}")
            stats["skipped_allowlist"] += 1
            processed.add(msg_id)
            continue

        log.info(f"Processing   | {sender[:55]} | {subject[:45]}")

        if settings.ENABLE_GEOTRACK and not dry_run:
            geo_data = track_email(msg)
            if geo_data:
                write_msgs_to_influxdb(geo_data, email=email)

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
                stats["total"] += 1
                stats["no_unsub"] += 1
                if settings.DELETE_IF_NO_UNSUB:
                    delete_message(msg_id, access_token, dry_run)
                processed.add(msg_id)
                continue

        if success:
            stats["success"] += 1
        else:
            stats["failed"] += 1

        if settings.DELETE_AFTER_UNSUB:
            delete_message(msg_id, access_token, dry_run)

        processed.add(msg_id)
        stats["total"] += 1
        time.sleep(settings.REQUEST_DELAY_SECONDS)

    if not dry_run:
        save_processed(processed)
    else:
        log.info("(dry-run: processed cache not updated)")

    return stats
