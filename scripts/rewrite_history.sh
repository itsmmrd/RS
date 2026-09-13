#!/usr/bin/env bash
# Rewrite post-initial commits into detailed logical commits.
# Usage: bash scripts/rewrite_history.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

BASE="b14a08b"
SAVE="$(git rev-parse HEAD~0 2>/dev/null || git rev-parse HEAD)"

# When re-running, set SAVE to the tip before rewrite manually.

if ! git rev-parse "$BASE" >/dev/null 2>&1; then
  echo "Base commit $BASE not found."
  exit 1
fi

if [[ "${1:-}" == "" ]]; then
  echo "Usage: SAVE=<commit-before-rewrite> bash scripts/rewrite_history.sh run"
  echo "This script is destructive. Only run when intentionally cleaning history."
  exit 1
fi

SAVE="${SAVE_COMMIT:-$1}"
echo "Rewriting history from $BASE (saved tip: $SAVE)..."

git reset --hard "$BASE"

restore() {
  git checkout "$SAVE" -- "$@"
}

commit_files() {
  local title="$1"
  local body="$2"
  shift 2
  restore "$@"
  git add "$@"
  if git diff --cached --quiet; then
    echo "Skip empty: $title"
    git reset HEAD -- "$@" 2>/dev/null || true
    return 0
  fi
  git commit -m "$title" -m "$body"
  echo "Committed: $title"
}

commit_files \
  "Add HTTPS installer, OAuth PKCE, and Google sync improvements" \
  "- install.sh: Caddy HTTPS via nip.io, UFW ports 80/443, fuser on 8090 before start
- install.sh: reinstall/uninstall args, token prompts via /dev/tty, health check
- google_services.py: persist OAuth PKCE code_verifier between start and callback
- google_services.py: numeric receipt names, DD MM YYYY sheet dates, attach/replace Drive photos
- google_services.py: delete Drive images when removing sheet rows" \
  install.sh google_services.py

commit_files \
  "Add receipt formatting helpers" \
  "- receipt_format.py: display dates (DD MM YYYY), meal labels, category display
- receipt_format.py: parse flexible manual date input" \
  receipt_format.py

commit_files \
  "Extend Gemini extraction for text entry and field edits" \
  "- extract_receipt.py: extract_receipt_from_text for manual one-block entry
- extract_receipt.py: normalize_edit_field for AI cleanup of date, spelling, amounts
- extract_receipt.py: purchase_time and meal fields on receipt model" \
  extract_receipt.py

commit_files \
  "Expand Telegram bot review, menu, and save flows" \
  "- bot.py: reply keyboard (List, Add, Remove, Sheet) and /command menu
- bot.py: connect via button only; minimal save summary with Drive/Sheet links
- bot.py: manual add — paste one text block, AI parses, save with/without photo
- bot.py: link scanned photo to existing receipt row (add or replace)
- bot.py: button-based field editing; preserve photos through edit/save
- bot.py: edit_callback_message fixes caption vs text save after review
- bot.py: review session stored in bot_data for edit continuity
- config.py: minor settings alignment" \
  bot.py config.py requirements.txt

commit_files \
  "Document setup and keep secrets out of git" \
  "- README.md: example IP 203-0-113-50.nip.io, updated bot usage table, security notes
- .env.example: placeholder env vars for server setup
- .gitignore: ignore .env.local and production env files" \
  README.md .env.example .gitignore

commit_files \
  "Improve auto-commit message generation" \
  "- scripts/commit_message.py: descriptive titles for bot, OAuth, and doc changes
- scripts/autocommit.sh, .cursor/hooks/auto-commit.sh: hook wiring" \
  scripts/commit_message.py scripts/autocommit.sh .cursor/hooks/auto-commit.sh

restore .cursor/hooks.json 2>/dev/null || true
git add .cursor/hooks.json 2>/dev/null || true
if ! git diff --cached --quiet; then
  git commit -m "Wire Cursor auto-commit hook" -m "Register hooks.json for staged auto-commits."
fi

echo
echo "Done. New history:"
git log --oneline "$BASE"..HEAD
echo
echo "To update GitHub: git push origin main --force-with-lease"
