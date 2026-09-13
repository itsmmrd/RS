#!/bin/bash
# Auto-commit and push RSA project changes. Secrets stay out via .gitignore.
cat >/dev/null
cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
git add -A
git reset -q -- .env 2>/dev/null || true
git diff --cached --quiet && git diff --quiet && {
  echo '{}'
  exit 0
}
if git diff --cached --quiet; then
  echo '{}'
  exit 0
fi
MSG="$(python3 scripts/commit_message.py 2>/dev/null || echo "Update project files")"
git commit -m "$MSG" >/dev/null 2>&1 || true
if git remote get-url origin >/dev/null 2>&1; then
  git push origin HEAD >/dev/null 2>&1 || true
fi
echo '{}'
exit 0
