# JunkNuke

Automatically scans your Outlook/Hotmail Junk folder, unsubscribes from
mailing lists, and deletes the emails. Runs on a Raspberry Pi (or any Linux
machine) on a schedule via cron.

---

## How it works

- Connects to your Outlook/Hotmail account via the **Microsoft Graph REST API**
- Reads your Junk Email folder and processes emails older than a configured age
- Unsubscribes using (in priority order):
  1. `List-Unsubscribe-Post` header — RFC 8058 one-click POST (best)
  2. `List-Unsubscribe` HTTP URL — GET request
  3. `List-Unsubscribe` mailto — sends an unsubscribe email via Graph
  4. Body link scan — fallback for emails without headers
- Deletes emails from Junk after processing (configurable)
- Remembers which emails have been handled so they're never processed twice
- Logs everything to `unsubscriber.log`

---

## Files

| File | Purpose |
|---|---|
| `unsubscriber.py` | Main script |
| `config.py` | Your settings — edit this before first run |
| `config.example.py` | Template showing required config keys |
| `requirements.txt` | Python dependencies |
| `token.json` | OAuth2 tokens (auto-created, keep private) |
| `processed.json` | Cache of handled email IDs (auto-created) |
| `unsubscriber.log` | Log of every run (auto-created) |

---

## Setup

### Step 1 — Clone and create a virtual environment

```bash
git clone https://github.com/yourusername/junknuke.git
cd junknuke
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### Step 2 — Register an Azure app (one-time, ~10 minutes)

You need a free Azure app registration to get a Client ID for OAuth2.

1. Go to https://portal.azure.com and sign in with any Microsoft account

2. Search for **"App registrations"** → click **New registration**

3. Fill in:
   - **Name**: `JunkNuke` (or anything you like)
   - **Supported account types**: `Accounts in any organizational directory and personal Microsoft accounts`
   - **Redirect URI**: leave blank for now

4. Click **Register** — copy the **Application (client) ID**

5. Go to **Authentication** in the left sidebar:
   - Click **Add a platform → Mobile and desktop applications**
   - Check: `https://login.microsoftonline.com/common/oauth2/nativeclient`
   - Click **Configure**
   - Click **Add URI** and add: `http://localhost:8765/callback`
   - Under **Advanced settings** set **Allow public client flows** to **Yes**
   - Click **Save**

6. Go to **API permissions** in the left sidebar:
   - Click **Add a permission → Microsoft Graph → Delegated permissions**
   - Add: `Mail.ReadWrite`, `Mail.Send`, `offline_access`
   - Click **Add permissions**

### Step 3 — Configure

Copy the example config and edit it:

```bash
cp config.example.py config.py
nano config.py
```

Set your email address and the Client ID from Step 2.

### Step 4 — First run (authenticates via browser)

```bash
source venv/bin/activate
python3 unsubscriber.py --dry-run
```

A browser will open on the Pi (or print a URL to open manually). Sign in
with your Hotmail/Outlook account and grant permissions. The script saves
a `token.json` — you won't need to do this again until the token expires
(~90 days), and even then just run manually once to re-authenticate.

Review the dry-run output. When happy, run for real with a limit first:

```bash
python3 unsubscriber.py --limit 20
```

Then without limit:

```bash
python3 unsubscriber.py
```

---

## Command-line options

```
--dry-run       Show what would happen without unsubscribing or deleting
--min-age N     Only process emails older than N days (default: from config.py)
--limit N       Process at most N unprocessed emails per run
```

---

## Scheduling on Raspberry Pi (cron)

Run every day at 7am:

```bash
crontab -e
```

Add:
```
0 7 * * * cd /home/pi/junknuke && /home/pi/junknuke/venv/bin/python3 unsubscriber.py >> /home/pi/junknuke/cron.log 2>&1
```

Adjust the path to match where you cloned the repo.

The `cd` before the command is important — the script saves `token.json`,
`processed.json`, and logs relative to the working directory.

Verify it saved:
```bash
crontab -l
```

Cron picks up changes immediately — no restart needed.

---

## Token expiry

The refresh token lasts ~90 days. When it expires the cron job will fail
silently. Check `cron.log` occasionally, or set a calendar reminder to
re-authenticate every 3 months by running the script manually once:

```bash
cd junknuke
source venv/bin/activate
rm token.json
python3 unsubscriber.py --dry-run
```

---

## Security

- `token.json` contains your OAuth2 refresh token — treat it like a password
- `config.py` contains your email and Client ID — don't commit it to git
- Both are in `.gitignore` by default
- The script never stores your Microsoft password

---

## .gitignore

```
token.json
processed.json
*.log
config.py
cron.log
```
