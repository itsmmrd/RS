#!/usr/bin/env bash
# Receipt Scanner Automation RSA — Ubuntu installer
# One line:
#   curl -fsSL https://raw.githubusercontent.com/itsmmrd/RS/main/install.sh -o /tmp/rsa-install.sh && sudo bash /tmp/rsa-install.sh reinstall
set -euo pipefail

APP_NAME="Receipt Scanner Automation RSA"
REPO_URL="${RSA_REPO_URL:-https://github.com/itsmmrd/RS.git}"
RAW_URL="${RSA_RAW_URL:-https://raw.githubusercontent.com/itsmmrd/RS/main/install.sh}"
INSTALL_DIR="${RSA_HOME:-/opt/rsa}"
SERVICE_NAME="rsa-bot"
REQUESTED_ACTION="${1:-}"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "Run as root:"
  echo "  curl -fsSL $RAW_URL -o /tmp/rsa-install.sh && sudo bash /tmp/rsa-install.sh"
  exit 1
fi

# Always refresh this script, then reopen the real keyboard.
# curl | bash and sudo can leave stdin on a pipe, so typed 1/2/3 never arrive.
if [[ "${RSA_BOOTSTRAPPED:-}" != "1" ]]; then
  curl -fsSL "$RAW_URL" -o /tmp/rsa-install.sh
  chmod +x /tmp/rsa-install.sh
  export RSA_BOOTSTRAPPED=1
  if [[ -e /dev/tty ]]; then
    exec bash /tmp/rsa-install.sh ${REQUESTED_ACTION:+"$REQUESTED_ACTION"} </dev/tty >/dev/tty 2>/dev/tty
  fi
  exec bash /tmp/rsa-install.sh ${REQUESTED_ACTION:+"$REQUESTED_ACTION"}
fi

trim() {
  local text="${1:-}"
  text="${text%$'\r'}"
  text="${text#"${text%%[![:space:]]*}"}"
  text="${text%"${text##*[![:space:]]}"}"
  printf "%s" "$text"
}

# Prompts must go to /dev/tty. If they go to stdout, $(ask) captures the
# prompt text and "1"/"2"/"3" never match.
ask() {
  local prompt="$1"
  local value=""
  printf "%s" "$prompt" >/dev/tty
  IFS= read -r value </dev/tty || true
  trim "$value"
}

already_installed() {
  [[ -f "$INSTALL_DIR/bot.py" ]] || [[ -f "/etc/systemd/system/${SERVICE_NAME}.service" ]]
}

uninstall_rsa() {
  echo "Stopping and removing $APP_NAME..."
  systemctl stop "$SERVICE_NAME" 2>/dev/null || true
  systemctl disable "$SERVICE_NAME" 2>/dev/null || true
  rm -f "/etc/systemd/system/${SERVICE_NAME}.service"
  systemctl daemon-reload || true
  rm -rf "$INSTALL_DIR"
  echo "Uninstalled. $INSTALL_DIR and the $SERVICE_NAME service are gone."
}

setup_caddy_proxy() {
  local host="$1"
  local port="$2"
  if ! command -v caddy >/dev/null 2>&1; then
    echo "Installing Caddy for HTTPS..."
    apt-get install -y debian-keyring debian-archive-keyring apt-transport-https
    curl -1sLf "https://dl.cloudsmith.io/public/caddy/stable/gpg.key" \
      | gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
    curl -1sLf "https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt" \
      | tee /etc/apt/sources.list.d/caddy-stable.list >/dev/null
    apt-get update -y
    apt-get install -y caddy
  fi
  if command -v ufw >/dev/null 2>&1; then
    ufw allow 80/tcp comment "RSA Caddy HTTP" >/dev/null 2>&1 || true
    ufw allow 443/tcp comment "RSA Caddy HTTPS" >/dev/null 2>&1 || true
  fi
  cat > /etc/caddy/Caddyfile <<EOF
${host} {
    reverse_proxy 127.0.0.1:${port}
}
EOF
  systemctl enable caddy
  if ! systemctl restart caddy; then
    echo "Caddy failed to start. Check: journalctl -u caddy -n 30 --no-pager"
    return 1
  fi
  PUBLIC_BASE_URL="https://${host}"
  return 0
}

wait_for_oauth_health() {
  local url="$1"
  local attempt
  for attempt in $(seq 1 12); do
    if curl -fsSk --max-time 8 "$url" 2>/dev/null | grep -q "OAuth server is running"; then
      return 0
    fi
    sleep 5
  done
  return 1
}

free_oauth_port() {
  local port="$1"
  apt-get install -y psmisc >/dev/null 2>&1 || true
  if command -v fuser >/dev/null 2>&1; then
    fuser -k "${port}/tcp" 2>/dev/null || true
  fi
  sleep 1
}

detect_public_ip() {
  local ip=""
  local service
  for service in \
    "https://api.ipify.org" \
    "https://ifconfig.me/ip" \
    "https://icanhazip.com"; do
    ip="$(curl -4 -fsS --max-time 8 "$service" 2>/dev/null || true)"
    ip="$(trim "$ip")"
    if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
      printf "%s" "$ip"
      return 0
    fi
  done
  ip="$(hostname -I 2>/dev/null | awk '{print $1}')"
  ip="$(trim "$ip")"
  if [[ "$ip" =~ ^[0-9]+\.[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    printf "%s" "$ip"
    return 0
  fi
  return 1
}

prompt_required() {
  local var="$1"
  local label="$2"
  local current="${!var:-}"
  local value=""
  while true; do
    echo
    echo "$label"
    if [[ -n "$current" ]]; then
      echo "  A value is already saved. Press Enter to keep it, or paste a new one."
    fi
    value="$(ask "  > ")"
    if [[ -n "$value" ]]; then
      printf -v "$var" "%s" "$value"
      echo "  Saved."
      return 0
    fi
    if [[ -n "${!var:-}" ]]; then
      echo "  Kept the existing value."
      return 0
    fi
    echo "  This value is required."
  done
}

prompt_optional() {
  local var="$1"
  local label="$2"
  local default="$3"
  local value=""
  echo
  echo "$label"
  value="$(ask "  > ")"
  if [[ -n "$value" ]]; then
    printf -v "$var" "%s" "$value"
  elif [[ -z "${!var:-}" ]]; then
    printf -v "$var" "%s" "$default"
  fi
  echo "  Using ${!var}"
}

ACTION="install"
case "$REQUESTED_ACTION" in
  1|reinstall|update) ACTION="reinstall" ;;
  2|uninstall|remove) ACTION="uninstall" ;;
  "")
    if already_installed; then
      echo "$APP_NAME is already installed in $INSTALL_DIR"
      echo
      echo "The number menu cannot read keys in this shell. Use one of these:"
      echo
      echo "  Reinstall / update:"
      echo "  curl -fsSL $RAW_URL -o /tmp/rsa-install.sh && sudo bash /tmp/rsa-install.sh reinstall"
      echo
      echo "  Uninstall:"
      echo "  curl -fsSL $RAW_URL -o /tmp/rsa-install.sh && sudo bash /tmp/rsa-install.sh uninstall"
      echo
      exit 0
    fi
    ;;
  *)
    echo "Unknown option: $REQUESTED_ACTION"
    echo "Use: reinstall | uninstall"
    exit 1
    ;;
esac

if [[ "$ACTION" == "uninstall" ]]; then
  uninstall_rsa
  exit 0
fi

export DEBIAN_FRONTEND=noninteractive
echo
echo "Installing packages..."
apt-get update -y
apt-get install -y python3 python3-venv python3-pip git curl libglib2.0-0 libgomp1 psmisc

if [[ -f "$INSTALL_DIR/bot.py" ]]; then
  ROOT="$INSTALL_DIR"
  if [[ -d "$ROOT/.git" ]]; then
    echo "Updating project files..."
    git -C "$ROOT" fetch --all --prune
    git -C "$ROOT" reset --hard origin/main
    git -C "$ROOT" clean -fd
  fi
else
  rm -rf "$INSTALL_DIR"
  echo "Downloading $APP_NAME..."
  git clone "$REPO_URL" "$INSTALL_DIR"
  ROOT="$INSTALL_DIR"
fi

ENV_FILE="$ROOT/.env"

RUN_USER="${SUDO_USER:-$USER}"
if [[ "$RUN_USER" == "root" ]]; then
  if id ubuntu >/dev/null 2>&1; then
    RUN_USER="ubuntu"
  else
    RUN_USER="root"
  fi
fi

echo
echo "=== $APP_NAME installer ==="
echo "Project folder: $ROOT"

if [[ ! -d "$ROOT/.venv" ]]; then
  sudo -u "$RUN_USER" python3 -m venv "$ROOT/.venv"
fi
sudo -u "$RUN_USER" "$ROOT/.venv/bin/pip" install --upgrade pip
sudo -u "$RUN_USER" "$ROOT/.venv/bin/pip" install -r "$ROOT/requirements.txt"

TELEGRAM_BOT_TOKEN="${TELEGRAM_BOT_TOKEN:-}"
GEMINI_API_KEY="${GEMINI_API_KEY:-}"
GOOGLE_CLIENT_ID="${GOOGLE_CLIENT_ID:-}"
GOOGLE_CLIENT_SECRET="${GOOGLE_CLIENT_SECRET:-}"
OAUTH_PORT="${OAUTH_PORT:-8090}"

if [[ -f "$ENV_FILE" ]]; then
  # shellcheck disable=SC1090
  set -a && source "$ENV_FILE" && set +a
fi

SERVER_IP="$(detect_public_ip || true)"
if [[ -z "$SERVER_IP" ]]; then
  echo "Could not detect the public IP of this server."
  exit 1
fi
OAUTH_PORT="${OAUTH_PORT:-8090}"
NIP_HOST="${SERVER_IP//./-}.nip.io"
if ! setup_caddy_proxy "$NIP_HOST" "$OAUTH_PORT"; then
  echo "Caddy HTTPS setup failed; falling back to HTTP on port $OAUTH_PORT"
  PUBLIC_BASE_URL="http://${NIP_HOST}:${OAUTH_PORT}"
fi
REDIRECT="${PUBLIC_BASE_URL}/oauth/callback"

echo
echo "Detected server IP: $SERVER_IP"
echo "Public URL: $PUBLIC_BASE_URL"
echo "Google OAuth callback URL:"
echo "  $REDIRECT"
echo
echo "Enter each token, then press Enter."
echo "They are saved only in $ENV_FILE on this server, never in git."
prompt_required TELEGRAM_BOT_TOKEN "1/4 Telegram bot token from @BotFather"
prompt_required GEMINI_API_KEY "2/4 Gemini API key"
prompt_required GOOGLE_CLIENT_ID "3/4 Google OAuth client ID"
prompt_required GOOGLE_CLIENT_SECRET "4/4 Google OAuth client secret"

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
chown -R "$RUN_USER":"$RUN_USER" "$ROOT" || true
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
ExecStartPre=-/usr/bin/fuser -k ${OAUTH_PORT}/tcp
ExecStart=$ROOT/.venv/bin/python $ROOT/bot.py
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

if command -v ufw >/dev/null 2>&1; then
  ufw allow "$OAUTH_PORT"/tcp comment "RSA Google OAuth" >/dev/null 2>&1 || true
fi

systemctl daemon-reload
systemctl enable "$SERVICE_NAME"
systemctl stop "$SERVICE_NAME" 2>/dev/null || true
free_oauth_port "$OAUTH_PORT"
systemctl restart "$SERVICE_NAME"
sleep 3

HEALTH_OK=0
if wait_for_oauth_health "${PUBLIC_BASE_URL}/oauth/health"; then
  HEALTH_OK=1
  echo "OAuth health check (HTTPS): OK"
else
  echo "WARNING: HTTPS health check failed at ${PUBLIC_BASE_URL}/oauth/health"
  echo "Checking direct HTTP on port ${OAUTH_PORT}..."
  if wait_for_oauth_health "http://127.0.0.1:${OAUTH_PORT}/oauth/health"; then
    echo "Bot OAuth server is up on port ${OAUTH_PORT}, but Caddy HTTPS is not reachable."
    echo "Try on the server:"
    echo "  sudo ufw allow 80/tcp && sudo ufw allow 443/tcp"
    echo "  sudo systemctl restart caddy"
    echo "  journalctl -u caddy -n 30 --no-pager"
    echo "Also open ports 80 and 443 in the Hetzner Cloud firewall if enabled."
  else
    echo "OAuth server is not responding. Check: journalctl -u rsa-bot -n 50 --no-pager"
  fi
fi

echo
echo "Installed."
echo "Tokens are only in $ENV_FILE (mode 600), not in git."
echo
echo "In Google Cloud Console, enable Drive API and Sheets API."
echo "Then open your OAuth 2.0 Web client and add this Authorized redirect URI:"
echo
echo "  $REDIRECT"
echo
echo "Open the Telegram bot and connect Google on first use."
echo "Status: sudo systemctl status $SERVICE_NAME"
echo
