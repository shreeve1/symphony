#!/usr/bin/env bash
# block-bash-pattern — hard-block (exit 2) dangerous Bash commands.
# Repo is uv-managed (uv.lock); blocks wrong package managers + catastrophic rm.
# Note: `uv pip install` is allowed — the pip pattern only matches pip at a
# command boundary (start or after ; & |), not the pip inside `uv pip ...`.
set -u
cmd=$(jq -r '.tool_input.command // empty')
[ -z "$cmd" ] && exit 0

# rm patterns match ONLY catastrophic targets — root (/), home (~ or $HOME) —
# at a token boundary. They do NOT match safe absolute deletes like `rm -f /tmp/x`.
patterns=(
  'rm[[:space:]]+-[a-zA-Z]*[rf][a-zA-Z]*[[:space:]]+(/|~|\$HOME)([[:space:]]|;|&|\||$)'
  'rm[[:space:]]+-[a-zA-Z]*[rf][a-zA-Z]*[[:space:]]+(/|~|\$HOME)\*'
  '(^|[;&|])[[:space:]]*pip[0-9.]*[[:space:]]+install'
  '(^|[;&|])[[:space:]]*pipenv[[:space:]]+install'
  '(^|[;&|])[[:space:]]*poetry[[:space:]]+add'
)

for pat in "${patterns[@]}"; do
  if echo "$cmd" | grep -qE "$pat"; then
    echo "Blocked by personalize-harness: matches /$pat/ (repo is uv-managed; use 'uv add' / 'uv pip install', and avoid recursive deletes of / or ~)." >&2
    exit 2
  fi
done
exit 0
