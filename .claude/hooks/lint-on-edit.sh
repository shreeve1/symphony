#!/usr/bin/env bash
# lint-on-edit — run ruff check on the edited .py file after every
# Edit/Write/MultiEdit. ADVISORY ONLY: warns on stderr but always exits 0,
# never blocks. Matches the project's autonomy-safe posture (commits 93630ba,
# 66a31bb demoted staged-static-check to advisory; commit 20fc650 removed
# blocking pre-git hooks — "hooks break autonomous runs"). The standing
# CLAUDE.md pre-commit obligation is the real gate. ruff only — no mypy
# (no project config -> per-file import noise). Fires in Claude (PostToolUse)
# and Pi (harness-gates adapter).
set -u
path=$(jq -r '.tool_input.file_path // empty')
[ -z "$path" ] && exit 0
[ -f "$path" ] || exit 0

case "$path" in
*.py)
	command -v ruff >/dev/null 2>&1 || exit 0
	# Only emit on findings — `ruff check` writes "All checks passed!" to stderr
	# even when clean, which would be noise on every Edit.
	if ! out=$(ruff check "$path" 2>&1); then
		printf 'harness-gate lint-on-edit (advisory, non-blocking):\n%s\n' "$out" >&2
	fi
	;;
esac
exit 0
