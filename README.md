# ReciptscannerAtuoamtiion RSA

Telegram bot that scans a receipt photo, extracts date / category / amount with Gemini, then saves the file to the user's Google Drive and a row to their Google Sheet.

The saved name starts at `1` and includes the receipt month and year, for example `1-09-2026`. That name is used for the Drive file and the sheet row.

## One-line Ubuntu install

```bash
sudo bash install.sh
```

The installer asks for:

- Telegram bot token (`@BotFather`)
- Gemini API key
- Google OAuth client ID and secret
- Public server URL, for example `http://YOUR_SERVER_IP:8080`

Then it creates a virtualenv, writes `.env`, and starts `rsa-bot` with systemd.

## Google Cloud setup

1. Create a project in Google Cloud.
2. Enable **Google Drive API** and **Google Sheets API**.
3. Create an **OAuth 2.0 Web client**.
4. Add this authorized redirect URI (same as the public URL you typed):

   `http://YOUR_SERVER_IP:8080/oauth/callback`

5. Open the Telegram bot. The first message asks you to connect your Google account.

## Bot commands

| Command | Action |
| --- | --- |
| Send a photo | Scan, extract text, then ask if the result is OK |
| Save result | Upload the processed photo |
| Save original photo | Upload the original photo instead |
| Edit text | Change date, category, amount, or merchant before saving |
| `/add` | Add a record manually, then optionally send a photo |
| `/text` | Add only text, no picture |
| `/delete` | Remove a record by name, for example `1-09-2026` |
| `/list` | Show recent records |
| `/connect` | Reconnect Google |
| `/cancel` | Stop the current step |

## Local run

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
# create .env with the same keys as install.sh
.venv/bin/python bot.py
```
