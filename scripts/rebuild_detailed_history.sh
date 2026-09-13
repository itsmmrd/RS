#!/usr/bin/env bash
# Rebuild main with detailed commit messages for every commit.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

if [[ "${1:-}" != "run" ]]; then
  echo "Usage: bash scripts/rebuild_detailed_history.sh run"
  exit 1
fi

# Use current main tip tree for script commits; logical commits by fixed hashes.
BASE="b14a08b7d62ac61562acfe136567bd65f2f636fe"
LOGICAL=(
  70b1929fa4705cfd7e3363dbdff3b92fd7e2432a
  fb667e124e9861d4663785664bcd87c77a18688c
  f6a585f2430fb801f1b2873a3347ba06e88bbc28
  9921e1c3ffe32333758df6c944d65673311c969c
  304d32af5d8d07b01e3cf271a945a248ba8e79eb
  31c2e72a25fbcd54b7a59ead894f29ab3dab3636
)
FINAL_TREE="$(git rev-parse HEAD^{tree})"
FINAL_META="$(git rev-parse HEAD)"

initial_msg() {
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
}

scripts_msg() {
  cat <<'EOF'
Add history rewrite scripts for detailed commit messages

- scripts/rewrite_history.sh: squash generic auto-commits into logical commits
- scripts/reword_messages.sh: msg-filter helper for amending commit bodies
- Documents git push --force-with-lease step after rewriting history
EOF
}

commit_tree() {
  local tree="$1"
  local msg="$2"
  local src="$3"
  export GIT_AUTHOR_NAME="$(git log -1 --format=%an "$src")"
  export GIT_AUTHOR_EMAIL="$(git log -1 --format=%ae "$src")"
  export GIT_AUTHOR_DATE="$(git log -1 --format=%at "$src")"
  export GIT_COMMITTER_NAME="$(git log -1 --format=%cn "$src")"
  export GIT_COMMITTER_EMAIL="$(git log -1 --format=%ce "$src")"
  export GIT_COMMITTER_DATE="$(git log -1 --format=%ct "$src")"
  if [[ -z "${PARENT:-}" ]]; then
    git commit-tree "$tree" -F - <<<"$msg"
  else
    git commit-tree "$tree" -p "$PARENT" -F - <<<"$msg"
  fi
}

BACKUP="backup-before-rebuild-$(date +%Y%m%d%H%M%S)"
git branch "$BACKUP" HEAD
echo "Backup branch: $BACKUP"

git checkout --orphan rebuild-main
git reset --hard
PARENT=""

# 1 — initial commit with detailed body
TREE="$(git rev-parse "${BASE}^{tree}")"
PARENT="$(commit_tree "$TREE" "$(initial_msg)" "$BASE")"
echo "1/8 initial -> ${PARENT:0:7}"

# 2–7 — keep existing title + body from rewritten commits
for i in "${!LOGICAL[@]}"; do
  src="${LOGICAL[$i]}"
  TREE="$(git rev-parse "${src}^{tree}")"
  MSG="$(git log -1 --format=%B "$src")"
  PARENT="$(commit_tree "$TREE" "$MSG" "$src")"
  echo "$((i + 2))/8 $(git log -1 --format=%s "$src") -> ${PARENT:0:7}"
done

# 8 — current tree (all rewrite scripts), single detailed commit
PARENT="$(commit_tree "$FINAL_TREE" "$(scripts_msg)" "$FINAL_META")"
echo "8/8 scripts -> ${PARENT:0:7}"

git branch -f main "$PARENT"
git checkout main
git branch -D rebuild-main 2>/dev/null || true

echo
echo "Done. New history:"
git log --oneline
echo
echo "Backup kept at: $BACKUP"
echo "Push with: git push origin main --force-with-lease"
