#!/bin/bash
# Auto-commit and push RSA project changes. Secrets stay out via .gitignore.
cat >/dev/null
cd "$(git rev-parse --show-toplevel 2>/dev/null)" || exit 0
git rev-parse --is-inside-work-tree >/dev/null 2>&1 || exit 0
git add -A
git diff --cached --quiet && git diff --quiet && {
  echo '{}'
  exit 0
}
if git diff --cached --quiet; then
  echo '{}'
  exit 0
fi
git commit -m "$(cat <<'EOF'
Auto-commit RSA project updates.

EOF
)" >/dev/null 2>&1 || true
if git remote get-url origin >/dev/null 2>&1; then
  git push origin HEAD >/dev/null 2>&1 || true
fi
echo '{}'
exit 0
