#!/usr/bin/env bash
# One-command installer for ReciptscannerAtuoamtiion RSA on Ubuntu.
# Usage: sudo bash install.sh
set -euo pipefail

APP_NAME="ReciptscannerAtuoamtiion RSA"
ROOT="$(cd "$(dirname "$0")" && pwd)"
SERVICE_NAME="rsa-bot"
ENV_FILE="$ROOT/.env"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run this once as root: sudo bash install.sh"
  exit 1
fi

RUN_USER="${SUDO_USER:-$USER}"
if [[ "$RUN_USER" == "root" ]]; then
  RUN_USER="ubuntu"
fi
RUN_HOME="$(eval echo "~$RUN_USER")"
if [[ ! -d "$RUN_HOME" ]]; then
  RUN_USER="root"
  RUN_HOME="/root"
fi

echo
echo "=== $APP_NAME installer ==="
echo "Project folder: $ROOT"
echo

export DEBIAN_FRONTEND=noninteractive
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git

if [[ ! -d "$ROOT/.venv" ]]; then
  sudo -u "$RUN_USER" python3 -m venv "$ROOT/.venv"
fi
sudo -u "$RUN_USER" "$ROOT/.venv/bin/pip" install --upgrade pip
sudo -u "$RUN_USER" "$ROOT/.venv/bin/pip" install -r "$ROOT/requirements.txt"

prompt() {
  local var="$1"
  local label="$2"
  local current="${!var:-}"
  if [[ -n "$current" ]]; then
    printf "%s [%s]: " "$label" "already set"
  else
    printf "%s: " "$label"
  fi
  local value
  read -r value
  if [[ -n "$value" ]]; then
    printf -v "$var" "%s" "$value"
  fi
}

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a && source "$ENV_FILE" && set +a
fi

echo
echo "Enter tokens. Press Enter to keep an existing value."
prompt TELEGRAM_BOT_TOKEN "Telegram bot token from @BotFather"
prompt GEMINI_API_KEY "Gemini API key from https://aistudio.google.com/apikey"
prompt GOOGLE_CLIENT_ID "Google OAuth client ID"
prompt GOOGLE_CLIENT_SECRET "Google OAuth client secret"
prompt PUBLIC_BASE_URL "Public server URL, for example http://YOUR_IP:8080"
prompt OAUTH_PORT "OAuth listen port (default 8080)"

OAUTH_PORT="${OAUTH_PORT:-8080}"

missing=0
for required in TELEGRAM_BOT_TOKEN GEMINI_API_KEY GOOGLE_CLIENT_ID GOOGLE_CLIENT_SECRET PUBLIC_BASE_URL; do
  if [[ -z "${!required:-}" ]]; then
    echo "Missing $required"
    missing=1
  fi
done
if [[ "$missing" -eq 1 ]]; then
  exit 1
fi

umask 077
cat > "$ENV_FILE" <<EOF
TELEGRAM_BOT_TOKEN=$TELEGRAM_BOT_TOKEN
GEMINI_API_KEY=$GEMINI_API_KEY
GOOGLE_CLIENT_ID=$GOOGLE_CLIENT_ID
GOOGLE_CLIENT_SECRET=$GOOGLE_CLIENT_SECRET
PUBLIC_BASE_URL=$PUBLIC_BASE_URL
OAUTH_PORT=$OAUTH_PORT
EOF
chown "$RUN_USER":"$RUN_USER" "$ENV_FILE"
chmod 600 "$ENV_FILE"

mkdir -p "$ROOT/data/users" "$ROOT/data/tmp" "$ROOT/data/oauth"
chown -R "$RUN_USER":"$RUN_USER" "$ROOT/data" "$ROOT/.venv"

cat > "/etc/systemd/system/${SERVICE_NAME}.service" <<EOF
[Unit]
Description=$APP_NAME Telegram bot
After=network.target

[Service]
Type=simple
User=$RUN_USER
WorkingDirectory=$ROOT
EnvironmentFile=$ENV_FILE
ExecStart=$ROOT/.venv/bin/python $ROOT/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl restart "$SERVICE_NAME"

REDIRECT="$PUBLIC_BASE_URL/oauth/callback"
echo
echo "Installed."
echo "In Google Cloud, enable Drive API and Sheets API."
echo "Add this authorized redirect URI to your OAuth client:"
echo "  $REDIRECT"
echo
echo "Open the Telegram bot and connect Google on first use."
echo "Status: sudo systemctl status $SERVICE_NAME"
echo
