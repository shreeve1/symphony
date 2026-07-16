#!/usr/bin/env bash
# block-bash-pattern — block Bash commands matching build-tool guardrail patterns.
# Detected build tool: uv (uv.lock present). Forbidden: pip install, pipenv install,
# poetry add — agents running in this repo must use uv, not those.
# Fires in Claude (PreToolUse Bash) and Pi (harness-gates adapter).
set -u
cmd=$(jq -r '.tool_input.command // empty')
[ -z "$cmd" ] && exit 0

patterns=(
	'(^|[;&|[:space:]])pip[[:space:]]+install([[:space:]]|$)'
	'(^|[;&|[:space:]])pipenv[[:space:]]+install([[:space:]]|$)'
	'(^|[;&|[:space:]])poetry[[:space:]]+add([[:space:]]|$)'
)

for pat in "${patterns[@]}"; do
	if echo "$cmd" | grep -qE "$pat"; then
		echo "Blocked by harness-gate: matches /$pat/ (project build tool is uv; use 'uv add' / 'uv sync' instead)" >&2
		exit 2
	fi
done
exit 0
