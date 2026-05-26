"""
geotrack.py — Email source IP extraction and geo-lookup for JunkNuke.
Returns enriched geo data dict. InfluxDB writing is handled by influxdb.py.
"""

import ipaddress
import logging
import re
from datetime import datetime, timezone

import requests

log = logging.getLogger(__name__)

# ── Private IP ranges to skip ─────────────────────────────────────────────────

PRIVATE_RANGES = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
]

MICROSOFT_PATTERNS = [
    "microsoft.com", "outlook.com", "hotmail.com",
    "office365.com", "protection.outlook.com",
    "prod.exchangelabs.com", "namprd", "eurprd", "apcprd",
]

def _is_private(ip_str: str) -> bool:
    try:
        addr = ipaddress.ip_address(ip_str)
        return any(addr in net for net in PRIVATE_RANGES)
    except ValueError:
        return True

def _is_microsoft(hostname: str) -> bool:
    return any(p in hostname.lower() for p in MICROSOFT_PATTERNS)

# ── Received: header parsing ──────────────────────────────────────────────────

RECEIVED_IP_RE = re.compile(
    r'from\s+\S+\s+\(.*?\[(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\]|'
    r'from\s+\[(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})\]',
    re.IGNORECASE,
)
RECEIVED_HOST_RE = re.compile(r'from\s+(\S+)', re.IGNORECASE)

def extract_originating_ip(headers: list[dict]) -> dict | None:
    received = [h["value"] for h in headers if h.get("name", "").lower() == "received"]
    for header in reversed(received):   # reversed = oldest first
        host_match = RECEIVED_HOST_RE.search(header)
        hostname   = host_match.group(1) if host_match else ""
        if _is_microsoft(hostname):
            continue
        ip_match = RECEIVED_IP_RE.search(header)
        if not ip_match:
            continue
        ip = next((g for g in ip_match.groups() if g), None)
        if not ip or _is_private(ip):
            continue
        return {"ip": ip, "hostname": hostname}
    return None

# ── Geo lookup ────────────────────────────────────────────────────────────────

_GEO_CACHE: dict[str, dict] = {}

def lookup_geo(ip: str) -> dict:
    if ip in _GEO_CACHE:
        return _GEO_CACHE[ip]
    try:
        resp = requests.get(
            f"http://ip-api.com/json/{ip}",
            params={"fields": "status,country,countryCode,regionName,city,lat,lon,isp,org,as,query"},
            timeout=10,
        )
        data = resp.json()
        if data.get("status") == "success":
            _GEO_CACHE[ip] = data
            return data
        log.warning("Geo lookup failed for %s: %s", ip, data.get("message"))
    except Exception as e:
        log.warning("Geo lookup error for %s: %s", ip, e)
    return {}

# ── Public entry point ────────────────────────────────────────────────────────

def track_email(msg: dict) -> dict | None:
    """
    Extract source IP from email headers, resolve geo data, and return
    an enriched dict ready for writing to InfluxDB.
    Returns None if no external IP could be found.
    """
    origin = extract_originating_ip(msg.get("internetMessageHeaders", []))
    if not origin:
        log.debug("No originating IP found in headers.")
        return None

    geo = lookup_geo(origin["ip"])
    if not geo:
        return None

    from_addr     = msg.get("from", {}).get("emailAddress", {}).get("address", "")
    sender_domain = from_addr.split("@")[-1] if "@" in from_addr else from_addr

    data = {
        **geo,
        "ip":            origin["ip"],
        "hostname":      origin.get("hostname", ""),
        "sender":        from_addr,
        "sender_domain": sender_domain,
        "subject":       msg.get("subject", ""),
        "timestamp":     datetime.now(timezone.utc).timestamp(),
    }

    log.info("Origin: %s → %s, %s [%s]",
             origin["ip"], geo.get("city", "?"), geo.get("country", "?"), geo.get("isp", "?"))

    return data
