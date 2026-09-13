#!/usr/bin/env bash
# Reword selected commits with detailed messages (used by filter-branch msg-filter).
case "$GIT_COMMIT" in
b14a08b*)
  cat <<'EOF'
Add RSA Telegram bot, Google Drive/Sheets sync, and Ubuntu installer

Initial release of Receipt Scanner Automation (RSA):

- bot.py: Telegram bot — send receipt photo, review extracted fields, edit, save
- bot.py: per-user Google OAuth connect flow with inline Connect button
- bot.py: list/remove saved receipts; conversation handler for scan and manual add
- scan_document.py: OpenCV perspective correction and document scan pipeline
- extract_receipt.py: Gemini vision extraction of date, category, amount, currency, merchant
- google_services.py: OAuth PKCE flow, Drive upload, Sheets append/list/delete per user
- google_services.py: sequential receipt naming and user token storage
- install.sh: Ubuntu installer — clone to /opt/rsa, systemd rsa-bot, env token prompts
- config.py: load .env and validate required secrets
- storage.py: per-user JSON persistence for OAuth tokens and settings
- README.md: Google Cloud setup, one-line install, bot usage
- requirements.txt: python-telegram-bot, Google APIs, OpenCV, Gemini, aiohttp
- .gitignore: exclude .env and local runtime data
- Cursor auto-commit hook scaffolding (scripts/autocommit.sh, .cursor/hooks/)
EOF
  ;;
8fe7fbd*)
  cat <<'EOF'
Add history rewrite script for detailed commit messages

- scripts/rewrite_history.sh: squash generic auto-commits into logical commits
- Each rewritten commit gets a descriptive title and bullet-point change list
- Documents git push --force-with-lease step after rewriting history
EOF
  ;;
*)
  cat
  ;;
esac
