# Running JunkNuke on Windows or macOS

## Prerequisites

**Both platforms:**
- Docker Desktop installed and running
- Git installed
- A Microsoft account (Hotmail/Outlook)
- An Azure app registration with Microsoft Graph API permissions

**Windows:**
- [Docker Desktop for Windows](https://www.docker.com/products/docker-desktop/)
- [Git for Windows](https://git-scm.com/download/win)

**macOS:**
- [Docker Desktop for Mac](https://www.docker.com/products/docker-desktop/)
- Git (pre-installed on most Macs, or via Homebrew: `brew install git`)

---

## Installation

**1. Clone the repo**
```bash
git clone https://github.com/johnnyc0121/junknuke
cd junknuke
```

**2. Configure environment variables**
Copy the example env file and fill in your values:
```bash
cp .env.example .env
```

Edit `.env` with your:
- Azure client ID and secret
- InfluxDB token and org
- Any other settings from `settings.py`

**3. Start JunkNuke**
```bash
docker compose up -d
```

That's it — JunkNuke is running.

---

## Accessing Grafana

Once running, open your browser and go to:
```
http://localhost:3000
```

Default Grafana credentials on first run:
- Username: `admin`
- Password: `admin`

You'll be prompted to change the password on first login.

---

## Importing the Dashboards

1. Log into Grafana at `http://localhost:3000`
2. Go to **Dashboards** → **Import**
3. Upload the dashboard JSON files included in the repo
4. Select your InfluxDB datasource when prompted
5. Click **Import**

> **Note:** Dashboard JSON files have been pre-stripped of instance-specific wrapper data for clean portability across environments.

---

## Stopping JunkNuke

```bash
docker compose down
```

Data persists in Docker volumes so nothing is lost between runs.

---

## Troubleshooting

**Docker Desktop not running:**
Make sure Docker Desktop is open and fully started before running `docker compose up`

**Port 3000 already in use:**
Another app may be using that port. Stop the conflicting app or change the Grafana port mapping in `docker-compose.yml`

**Authentication errors:**
Double check your Azure app registration scopes include `Mail.Read` and `Mail.Send` if using the weekly digest feature
