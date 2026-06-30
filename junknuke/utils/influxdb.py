"""
influxdb.py — InfluxDB token reading and data writing for JunkNuke.

Token is read lazily from the shared influxdb2-config volume at write time,
not at import time, so it is available after InfluxDB has started up.
Connection settings come from settings.py.
"""

import logging
import os
from datetime import datetime, timezone

import toml
from influxdb_client import InfluxDBClient, Point, WritePrecision
from influxdb_client.client.write_api import SYNCHRONOUS

from junknuke import settings

log = logging.getLogger(__name__)

INFLUX_CONFIG_FILE = "/etc/influxdb2/influx-configs"

# ── Prep steps ──────────────────────────────────────────────────────────────

def ensure_bucket_exists(bucket_name: str):
    token = _get_influx_token()
    if not token:
        return

    try:
        with InfluxDBClient(url=settings.INFLUX_URL, token=token, org=settings.INFLUX_ORG) as client:
            buckets_api = client.buckets_api()
            existing = buckets_api.find_bucket_by_name(bucket_name)
            if not existing:
                buckets_api.create_bucket(bucket_name=bucket_name, org=settings.INFLUX_ORG)
                log.info("Created InfluxDB bucket: %s", bucket_name)
            else:
                log.info("InfluxDB bucket already exists: %s", bucket_name)
    except Exception as e:
        log.error("Failed to ensure bucket %s: %s", bucket_name, e, exc_info=True)

# ── Token reader ──────────────────────────────────────────────────────────────

def _get_influx_token() -> str:
    """
    Return the InfluxDB token. Checks in order:
    1. INFLUXDB_TOKEN env var — for local dev / override
    2. /etc/influxdb2/influx-configs — shared Docker volume (production)
       InfluxDB generates this token at runtime, matching the telemetry-agent pattern.
    """
    env_token = os.environ.get("INFLUXDB_TOKEN", "").strip()
    if env_token:
        return env_token

    try:
        with open(INFLUX_CONFIG_FILE, "r") as f:
            token_config = toml.load(f)
        token = token_config.get("default", {}).get("token", "").strip('"')
        if token:
            log.info("InfluxDB token loaded from %s", INFLUX_CONFIG_FILE)
            return token
        log.warning("Token key not found in %s", INFLUX_CONFIG_FILE)
    except FileNotFoundError:
        log.warning("InfluxDB config not found at %s — is the volume mounted?", INFLUX_CONFIG_FILE)
    except Exception as e:
        log.warning("Could not read InfluxDB token: %s", e)

    return ""

# ── Writer ────────────────────────────────────────────────────────────────────

def write_msgs_to_influxdb(data: dict, email: str, provider: str):
    """
    Write a spam geo data point to InfluxDB.
    Connection settings come from settings.py.
    Token is read lazily so InfluxDB has time to start before it's needed.
    """

    ensure_bucket_exists("messages")

    token = _get_influx_token()
    if not token:
        log.warning("No InfluxDB token available — skipping write.")
        return

    try:
        with InfluxDBClient(url=settings.INFLUX_URL, token=token, org=settings.INFLUX_ORG) as client:
            write_api = client.write_api(write_options=SYNCHRONOUS)

            point = (
                Point("spam_geo")
                .tag("email", email)
                .tag("provider", provider)
                .tag("country_code",  data.get("countryCode", "XX"))
                .tag("country",       data.get("country", "Unknown"))
                .tag("city",          data.get("city", "Unknown"))
                .tag("isp",           data.get("isp", "Unknown")[:50])
                .tag("sender_domain", data.get("sender_domain", "unknown"))
                .field("ip",      data.get("ip", ""))
                .field("lat",     float(data.get("lat", 0.0)))
                .field("lon",     float(data.get("lon", 0.0)))
                .field("org",     data.get("org", ""))
                .field("asn",     data.get("as", ""))
                .field("sender",  data.get("sender", ""))
                .field("subject", data.get("subject", "")[:100])
                .time(datetime.now(timezone.utc), WritePrecision.NS)
            )

            write_api.write(bucket=settings.INFLUX_MESSAGES_BUCKET, org=settings.INFLUX_ORG, record=point)
            log.info("InfluxDB write OK — %s, %s [%s]",
                     data.get("city"), data.get("country"), data.get("ip"))

    except Exception as e:
        log.error("InfluxDB write failed: %s", e, exc_info=True)

def write_stats_to_influxdb(data: dict, email: str, provider: str):
    """
    Write a stats data point to InfluxDB.
    Connection settings come from settings.py.
    Token is read lazily so InfluxDB has time to start before it's needed.
    """

    ensure_bucket_exists("stats")

    token = _get_influx_token()
    if not token:
        log.warning("No InfluxDB token available — skipping write.")
        return

    try:
        with InfluxDBClient(url=settings.INFLUX_URL, token=token, org=settings.INFLUX_ORG) as client:
            write_api = client.write_api(write_options=SYNCHRONOUS)

            point = (
                Point("run_summary")
                .tag("email", email)
                .tag("provider", provider)
                .field("total",              data.get("total", 0))
                .field("seen",               data.get("seen", 0))
                .field("already_processed",  data.get("already_processed", 0))
                .field("allowlisted",        data.get("allowlisted", 0))
                .field("no_unsub_found",     data.get("no_unsub_found", 0))
                .field("unsubscribed_ok",    data.get("unsubscribed_ok", 0))
                .field("failed",             data.get("failed", 0))
                .time(datetime.now(timezone.utc), WritePrecision.NS)
            )

            write_api.write(bucket=settings.INFLUX_STATS_BUCKET, org=settings.INFLUX_ORG, record=point)
            log.info("InfluxDB stats write OK — seen: %s, unsubscribed: %s, failed: %s",
                     data.get("seen"), data.get("unsubscribed_ok"), data.get("failed"))

            log.info("=== Run complete ===")
            log.info(f"  Account:            {email}")
            log.info(f"  Total processed:    {data.get('total', 0)}")
            log.info(f"  Seen:               {data.get('seen', 0)}")
            log.info(f"  Already processed:  {data.get('already_processed', 0)}")
            log.info(f"  Allowlisted:        {data.get('allowlisted', 0)}")
            log.info(f"  No unsub found:     {data.get('no_unsub_found', 0)}")
            log.info(f"  Unsubscribed (ok):  {data.get('unsubscribed_ok', 0)}")
            log.info(f"  Failed:             {data.get('failed', 0)}")

    except Exception as e:
        log.error("InfluxDB write failed: %s", e, exc_info=True)
