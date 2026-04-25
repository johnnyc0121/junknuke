# Outlook Junk Mail Unsubscriber

Automatically scans your Outlook/Hotmail Junk folder and unsubscribes from
mailing lists using `List-Unsubscribe` headers (the same mechanism as Apple
Mail's unsubscribe button), with a body-link fallback.

---

## Files

| File | Purpose |
|---|---|
| `unsubscriber.py` | Main script |
| `config.py` | Your settings — edit this first |
| `requirements.txt` | Python dependencies |
| `token.json` | OAuth2 tokens (auto-created, keep private) |
| `processed.json` | Cache of handled email IDs (auto-created) |
| `unsubscriber.log` | Log of every run (auto-created) |

---

## Step 1 — Install Python dependencies

```bash
pip install -r requirements.txt
```

On a Raspberry Pi you may need:
```bash
pip3 install -r requirements.txt
```

---

## Step 2 — Register a free Azure app (one-time, ~10 minutes)

Microsoft requires OAuth2 for IMAP/SMTP access on personal Outlook/Hotmail
accounts. You need a free "app registration" to get a Client ID.

1. Go to https://portal.azure.com and sign in with **any** Microsoft account
   (doesn't have to be the Hotmail account you're unsubscribing from).

2. Search for **"App registrations"** → click **New registration**.

3. Fill in:
   - **Name**: `JunkUnsubscriber` (anything you like)
   - **Supported account types**: Select **"Personal Microsoft accounts only"**
   - **Redirect URI**: leave blank

4. Click **Register**. Copy the **Application (client) ID** — paste it into
   `config.py` as `CLIENT_ID`.

5. In the left sidebar, go to **Authentication**:
   - Under **Advanced settings**, set **"Allow public client flows"** to **Yes**
   - Click **Save**

6. In the left sidebar, go to **API permissions**:
   - Click **Add a permission → APIs my organization uses**
   - Search for **"Office 365 Exchange Online"** and select it
   - Choose **Delegated permissions**
   - Check: `IMAP.AccessAsUser.All` and `SMTP.Send`
   - Click **Add permissions**
   - *(You do NOT need to click "Grant admin consent" for personal accounts)*

That's it — no client secret needed for this public client flow.

---

## Step 3 — Edit config.py

```python
EMAIL_ADDRESS = "you@hotmail.com"      # your actual address
CLIENT_ID     = "xxxxxxxx-xxxx-..."    # from Step 2
```

Add any senders you want to protect to `ALLOWLIST`.

---

## Step 4 — First run (authenticate)

Run with `--dry-run` first so nothing happens until you're confident:

```bash
# Create the venv (once)
cd /home/pi/unsubscriber
python3 -m venv venv

# Activate it
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the script (venv still active)
python3 unsubscriber.py --dry-run

# Deactivate when done
deactivate
```

On first run it will print something like:

```
ACTION REQUIRED — Open this URL in a browser:
  https://microsoft.com/devicelogin

Enter code: ABCD-1234
```

Open that URL on any device, enter the code, and sign in with your Hotmail
account. Grant the permissions. The script will detect the login and save a
`token.json` file — you won't need to do this again until the token expires
(typically 90 days).

Review the dry-run log output. When you're happy, run for real:

```bash
python3 unsubscriber.py
```

---

## Command-line options

```
--dry-run          Show what would happen without unsubscribing
--min-age N        Only process emails older than N days (default: from config.py)
--limit N          Process at most N emails per run (good for first real run)
```

Examples:
```bash
# Safe first real run — only do 20 emails
python3 unsubscriber.py --limit 20

# Process everything older than 3 days
python3 unsubscriber.py --min-age 3

# See what it would do with emails older than 14 days
python3 unsubscriber.py --dry-run --min-age 14
```

---

## Scheduling on Raspberry Pi (cron)

Run every Sunday at 8am:

```bash
crontab -e
```

Add this line (adjust the path to where you put the files):

```
0 8 * * 0 /usr/bin/python3 /home/pi/outlook-unsubscriber/unsubscriber.py >> /home/pi/outlook-unsubscriber/cron.log 2>&1
```

Or daily at 7am:
```
0 7 * * * /usr/bin/python3 /home/pi/outlook-unsubscriber/unsubscriber.py
```

---

## How unsubscribing works (priority order)

1. **`List-Unsubscribe-Post` + `List-Unsubscribe` HTTP** — RFC 8058 one-click
   POST. The gold standard. Used by all reputable senders. Silent and instant.

2. **`List-Unsubscribe` HTTP URL** — GET request to the unsubscribe URL.

3. **`List-Unsubscribe` mailto** — Sends a short unsubscribe email on your
   behalf via SMTP.

4. **Body link scan** — Searches the email body for URLs containing
   "unsubscribe", "opt-out", or "remove". Less reliable — some pages need
   a browser click — but better than nothing.

---

## Security notes

- `token.json` contains your OAuth2 refresh token. Treat it like a password.
  Don't commit it to git. Add it to `.gitignore`:
  ```
  token.json
  processed.json
  *.log
  ```
- The script never stores your password.
- Azure app permissions are delegated (act as you), not admin.
- You can revoke access anytime at https://account.live.com/consent/Manage

---

## Troubleshooting

**"Could not find Junk folder"**
Run this snippet to see your folder names:
```python
import imaplib, json
# ... connect as in unsubscriber.py ...
print(imap.list())
```
Then update the folder list in `fetch_junk_messages()`.

**Token keeps expiring**
Make sure you granted `offline_access` scope and that "Allow public client
flows" is enabled in Azure → Authentication.

**Emails not being found**
Check `--min-age`. By default only emails older than 7 days are processed.
Try `--min-age 1` to catch everything.
