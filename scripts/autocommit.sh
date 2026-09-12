#!/bin/bash
set -euo pipefail
cd "$(dirname "$0")/.."
git add -A
if git diff --cached --quiet; then
  echo "No changes to commit."
  exit 0
fi
git commit -m "Auto-commit RSA project updates."
if git remote get-url origin >/dev/null 2>&1; then
  git push origin HEAD
fi
