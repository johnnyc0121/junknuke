# JunkNuke

Automatically scans your Outlook/Hotmail Junk folder, unsubscribes from
mailing lists, tracks source IPs, and writes geo data to InfluxDB for
visualisation in Grafana. Runs as a Docker container on a Raspberry Pi.

---

## Architecture

```
main.py → graph.py (Graph API) → unsubscribe.py → delete
                               → geotrack.py → InfluxDB → Grafana
```

- **graph.py** — Microsoft Graph API auth and message fetching
- **unsubscribe.py** — List-Unsubscribe headers, mailto, body link fallback
- **geotrack.py** — Received: header parsing, ip-api.com geo lookup, InfluxDB writer
- **main.py** — orchestration, run loop, CLI

---

## Repo structure

```
junknuke/
├── junknuke/                   ← Python package
│   ├── __init__.py
│   ├── main.py
│   ├── graph.py
│   ├── unsubscribe.py
│   ├── geotrack.py
│   ├── settings.py
│   └── requirements.txt
├── grafana/
│   ├── grafana-entrypoint.sh
│   └── provisioning/dashboards/
├── data/                       ← gitignored; mounted as Docker volume
│   ├── token.json              ← OAuth2 token (generate once on host)
│   ├── processed.json          ← cache of handled email IDs
│   └── junknuke.log
├── .env                        ← gitignored; copy from .env.example
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
└── README.md
```

---

## Setup

### Step 1 — Azure app registration (one-time)

1. Go to https://portal.azure.com
2. **App registrations → New registration**
   - Name: `JunkNuke`
   - Supported account types: `Accounts in any organizational directory and personal Microsoft accounts`
3. Copy the **Application (client) ID**
4. **Authentication → Add a platform → Mobile and desktop applications**
   - Check: `https://login.microsoftonline.com/common/oauth2/nativeclient`
   - Add URI: `http://localhost:8765/callback`
   - Allow public client flows: **Yes**
   - Save
5. **API permissions → Add → Microsoft Graph → Delegated**
   - `Mail.ReadWrite`, `Mail.Send`, `offline_access`

### Step 2 — Configure

```bash
cp .env.example .env
nano .env
```

Fill in `EMAIL_ADDRESS`, `AZURE_CLIENT_ID`, and the InfluxDB/Grafana credentials.

### Step 3 — Authenticate (host only, one-time)

This must be run on the host (not in Docker) to open a browser:

```bash
export EMAIL_ADDRESS="ADD_IT_HERE"
export AZURE_CLIENT_ID="ADD_IT_HERE"
python3 -m venv venv
source venv/bin/activate
pip install -r junknuke/requirements.txt

python -m junknuke.main --auth-only
```

Sign in with your Hotmail/Outlook account when the browser opens.
A `data/token.json` file is created — this is mounted into the container.

### Step 4 — Start the stack

```bash
docker compose up --build -d
```

Services:
- **junknuke** — runs daily, loops automatically
- **influxdb2** → http://localhost:8086
- **grafana** → http://localhost:3000 (admin/admin, change on first login)

---

## Running locally (no Docker)

```bash
source venv/bin/activate

# Dry run — see what it would do
python -m junknuke.main --dry-run

# Real run, limit to 20 emails
python -m junknuke.main --limit 20

# Full run, exit after one pass
python -m junknuke.main --no-loop
```

---

## Environment variables

| Variable | Description | Default |
|---|---|---|
| `EMAIL_ADDRESS` | Your Hotmail/Outlook address | required |
| `AZURE_CLIENT_ID` | Azure app client ID | required |
| `RUN_INTERVAL` | Seconds between runs in Docker | `86400` |
| `MIN_AGE_DAYS` | Process emails older than N days | `7` |
| `DELETE_AFTER_UNSUB` | Delete email after unsubscribe | `true` |
| `DELETE_IF_NO_UNSUB` | Delete if no unsubscribe found | `true` |
| `ALLOWLIST` | Comma-separated senders to protect | `""` |
| `ENABLE_GEOTRACK` | Track source IPs in InfluxDB | `true` |
| `INFLUXDB_URL` | InfluxDB URL (Docker: use `_DOCKER` variant) | |
| `INFLUXDB_TOKEN` | InfluxDB API token | |
| `INFLUXDB_ORG` | InfluxDB org | `junknuke` |
| `INFLUXDB_BUCKET` | InfluxDB bucket | `junknuke` |

---

## Token expiry

The OAuth2 refresh token lasts ~90 days. When it expires:

```bash
cd junknuke
source venv/bin/activate
rm data/token.json
python -m junknuke.main --auth-only
docker compose restart junknuke
```

---

## Grafana dashboards

The `grafana/provisioning/dashboards/` directory is mounted into Grafana.
Place dashboard JSON files there and they'll appear automatically.

Suggested panels for the `spam_geo` measurement:
- **Geomap** — world map with lat/lon fields, sized by count
- **Bar chart** — top countries by spam volume
- **Bar chart** — top ISPs/ASNs
- **Time series** — spam volume over time, grouped by country

---

## Viewing logs

```bash
# Docker logs (stdout)
docker logs junknuke -f

# File log (inside mounted volume)
tail -f data/junknuke.log
```

---

## Security notes

- `data/token.json` contains your OAuth2 refresh token — treat like a password
- `.env` contains credentials — never commit it
- Both are in `.gitignore`
- The script never stores your Microsoft password

---

## Roadmap

- Gmail support via Google Gmail API
- Yahoo Mail support
- Additional provider support planned — contributions welcome

---

## License
MIT
