# Receipt Scanner Automation RSA

Telegram bot that scans a receipt photo, extracts date / category / amount with Gemini, then saves the file to the user's Google Drive and a row to their Google Sheet.

Each saved receipt gets a sequential number (`#1`, `#2`, …). Dates are stored as `DD MM YYYY`. Food purchases can include a meal label such as `(lunch)`.

![image](https://github.com/itsmmrd/Receipt_Scanner_Automation_RSA/blob/4cc711db30c01c6215266babc78b5176e0fa09f2/scripts/1.png)
## One-line Ubuntu install

Paste this on the server. It downloads the project and starts the installer:

First install or later update:

```bash
curl -fsSL https://raw.githubusercontent.com/itsmmrd/RS/main/install.sh -o /tmp/rsa-install.sh && sudo bash /tmp/rsa-install.sh reinstall
```

Uninstall:

```bash
curl -fsSL https://raw.githubusercontent.com/itsmmrd/RS/main/install.sh -o /tmp/rsa-install.sh && sudo bash /tmp/rsa-install.sh uninstall
```

The installer asks for:

- Telegram bot token (`@BotFather`)
- Gemini API key
- Google OAuth client ID and secret

It detects the server public IP, sets up HTTPS with Caddy, and builds the Google callback. Example (replace with your server IP):

`https://203-0-113-50.nip.io/oauth/callback`

Then it clones into `/opt/rsa`, writes `.env` on the server only, and starts `rsa-bot` with systemd.

## Google Cloud setup

1. Create a project in Google Cloud.
2. Enable **Google Drive API** and **Google Sheets API**.
3. Create an **OAuth 2.0 Web client**.
4. Add the authorized redirect URI printed by the installer, for example:

   `https://203-0-113-50.nip.io/oauth/callback`

5. Open ports **80**, **443**, and **8090** in your cloud firewall if needed.

6. Test in a browser: `https://YOUR-IP-AS-NIP.IO/oauth/health` should show `OAuth server is running`.

7. Open the Telegram bot. Connect Google on first use via the **Connect Google account** button.

## Bot usage

| Action | What it does |
| --- | --- |
| Send a photo | Scan receipt, review, then save processed or original photo |
| **Edit text** | Button menu to edit date, category, amount, etc. (AI normalizes input) |
| **Link to existing** | Attach scanned photo to an existing receipt row |
| **📋 List** / `/list` | Recent receipts with Drive and delete buttons |
| **➕ Add** / `/add` | Paste receipt text in one message — AI formats it |
| **🗑 Remove** / `/delete` | Tap a receipt to remove from Sheet and Drive |
| **📊 Sheet** | Open your Google Sheet |
| `/connect` | Connect or refresh Google account |
| `/cancel` | Stop the current step |

## Local run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
cp .env.example .env   # fill in values locally; never commit .env
.venv/bin/python bot.py
```

## Security

- `.env`, `data/`, OAuth tokens, and credentials JSON files are gitignored.
- Do not paste bot tokens or API keys into issues, commits, or chat logs.
- If a token was exposed, regenerate it in @BotFather / Google Cloud and update `.env` on the server.

![image] (https://github.com/itsmmrd/Receipt_Scanner_Automation_RSA/blob/5b53cbf8815f50a16c3397f8babb371ed6663841/2.png)
