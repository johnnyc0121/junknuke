# JunkNuke

Automatically scans your Outlook/Hotmail Junk folder, unsubscribes from
mailing lists, tracks source IPs, and writes geo data to InfluxDB for
visualisation in Grafana. Runs as a Docker container on a Raspberry Pi.

---

## Architecture

```
main.py → runner.py → providers/microsoft/ → msgraph.py (Graph API)
                                            → unsubscribe.py → delete
                    → utils/geotrack.py → InfluxDB → Grafana
                    → utils/influxdb.py
```

- **main.py** — CLI, orchestration, run loop
- **runner.py** — multi-account/multi-provider dispatcher
- **providers/microsoft/** — Microsoft-specific auth, Graph API, and unsubscribe logic
- **utils/geotrack.py** — Received: header parsing, ip-api.com geo lookup
- **utils/influxdb.py** — InfluxDB writer for geo and run stats
- **settings.py** — all configuration from environment variables

---

## Repo structure

```
junknuke/
├── junknuke/                        ← Python package
│   ├── __init__.py
│   ├── main.py
│   ├── runner.py
│   ├── settings.py
│   ├── requirements.txt
│   ├── providers/
│   │   ├── __init__.py
│   │   └── microsoft/
│   │       ├── __init__.py          ← run() entry point
│   │       ├── msgraph.py           ← Graph API auth + message fetching
│   │       └── unsubscribe.py       ← unsubscribe logic
│   ├── utils/
│   │   ├── __init__.py
│   │   ├── geotrack.py
│   │   └── influxdb.py
│   └── tests/
│       ├── __init__.py
│       ├── conftest.py
│       ├── test_settings.py
│       ├── test_geotrack.py
│       ├── test_influxdb.py
│       └── test_unsubscribe.py
├── grafana/
│   ├── grafana-entrypoint.sh
│   └── provisioning/dashboards/     ← dashboard JSON files auto-imported
├── data/                            ← gitignored; mounted as Docker volume
│   ├── token_<email>.json           ← OAuth2 token (generated once on host)
│   ├── processed_<email>.json       ← cache of handled email IDs
│   └── junknuke.log
├── .env                             ← gitignored; copy from .env.example
├── .env.example
├── .gitignore
├── Dockerfile
├── docker-compose.yml
├── DEPLOY_LOCAL.md                  ← running on Windows/macOS
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
   - `Mail.Read`, `Mail.ReadWrite`, `Mail.Send`, `User.Read`, `offline_access`

### Step 2 — Configure

```bash
cp .env.example .env
nano .env
```

Fill in `MAIL_ACCOUNTS`, `AZURE_CLIENT_ID`, and the InfluxDB/Grafana credentials.

`MAIL_ACCOUNTS` format: `email:provider` — comma-separated for multiple accounts:

```
MAIL_ACCOUNTS=yourname@outlook.com:microsoft
```

### Step 3 — Set up virtual environment and install dependencies

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r junknuke/requirements.txt
```

### Step 4 — Authenticate (host only, one-time)

This must be run on the host (not in Docker) to open a browser:

```bash
export MAIL_ACCOUNTS="yourname@outlook.com:microsoft"
export AZURE_CLIENT_ID="your-client-id-here"

python -m junknuke.main --auth-only
```

Sign in with your Hotmail/Outlook account when the browser opens.
A `data/token_<email>.json` file is created — this is mounted into the container.

To re-authenticate a specific account only:

```bash
python -m junknuke.main --auth-only --account yourname@outlook.com
```

### Step 5 — Create InfluxDB buckets

JunkNuke uses two buckets. Create both before starting the stack:

- `messages` — geo data for each processed email
- `stats` — per-run summary statistics

Create them via the InfluxDB UI at http://localhost:8086 → Load Data → Buckets → Create Bucket.

### Step 6 — Start the stack

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
| `MAIL_ACCOUNTS` | Comma-separated `email:provider` pairs | required |
| `AZURE_CLIENT_ID` | Azure app client ID | required |
| `RUN_INTERVAL` | Seconds between runs in Docker | `86400` |
| `MIN_AGE_DAYS` | Process emails older than N days | `7` |
| `DELETE_AFTER_UNSUB` | Delete email after unsubscribe attempt | `true` |
| `DELETE_IF_NO_UNSUB` | Delete if no unsubscribe found | `true` |
| `ALLOWLIST` | Comma-separated senders to protect | `""` |
| `ENABLE_GEOTRACK` | Track source IPs in InfluxDB | `true` |
| `INFLUXDB_URL` | InfluxDB URL | |
| `INFLUXDB_TOKEN` | InfluxDB API token | |
| `INFLUXDB_ORG` | InfluxDB org | `junknuke` |
| `INFLUXDB_MESSAGES_BUCKET` | Bucket for geo/message data | `messages` |
| `INFLUXDB_STATS_BUCKET` | Bucket for run statistics | `stats` |

---

## Token expiry

The OAuth2 refresh token lasts ~90 days. When it expires:

```bash
cd junknuke
source venv/bin/activate
rm data/token_yourname@outlook.com.json
python -m junknuke.main --auth-only
docker compose restart junknuke
```

---

## Grafana dashboards

Dashboard JSON files in `grafana/provisioning/dashboards/` are automatically
imported when Grafana starts. Two dashboards are included:

- **JunkNuke** — world map, top countries, spam volume over time
- **JunkNuke Stats** — per-run summary, unsubscribe success rate trends

> **Note:** Dashboard JSON files have been stripped of instance-specific
> wrapper data for clean portability across environments.

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

## Running tests

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r junknuke/requirements.txt
pip install pytest pytest-mock
pytest junknuke/tests/ -v
```

---

## Security notes

- `data/token_<email>.json` contains your OAuth2 refresh token — treat like a password
- `.env` contains credentials — never commit it
- Both are in `.gitignore`
- The script never stores your Microsoft password

---

## Roadmap

- Gmail support via Google Gmail API
- Yahoo Mail support
- Weekly digest notification via email
- Azure cloud deployment guide
- Additional provider support planned — contributions welcome

---

## License

MIT
