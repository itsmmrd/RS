#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
git add -A
git reset -q -- .env 2>/dev/null || true
if git diff --cached --quiet; then
  echo "No changes to commit."
  exit 0
fi
MSG="$(python3 scripts/commit_message.py)"
git commit -m "$MSG"
if git remote get-url origin >/dev/null 2>&1; then
  git push origin HEAD
fi
