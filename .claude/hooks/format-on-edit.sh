#!/usr/bin/env bash
# format-on-edit — run ruff format on the edited .py file after every
# Edit/Write/MultiEdit. Fail-open: missing tool / non-.py = no-op, never blocks.
# Fires in Claude (PostToolUse) and Pi (harness-gates adapter).
set -u
path=$(jq -r '.tool_input.file_path // empty')
[ -z "$path" ] && exit 0
[ -f "$path" ] || exit 0

case "$path" in
  *.py)
    command -v ruff >/dev/null 2>&1 && ruff format --quiet "$path" >/dev/null 2>&1 ;;
esac
exit 0
