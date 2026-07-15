#!/usr/bin/env bash
# staged-static-check — ruff check on staged .py files before git commit/push.
# ADVISORY ONLY: warns on stderr but always exits 0, never blocks the commit.
# symphony runs agents unattended (bypassPermissions) and deliberately removed
# blocking pre-git hooks (commits 20fc650, 704b4b4: "Hooks break autonomous
# runs"); the standing CLAUDE.md pre-commit obligation is the real gate.
# Reads {tool_input:{command}} on stdin. Only acts on git commit/push; every
# other bash command passes through (exit 0).
# Fires in Claude (PreToolUse Bash) and Pi. ruff only — mypy/pyright omitted
# (no project config → per-file import noise). Whole-project pytest is left to
# CI/dev-test (flaky concurrent test + ADR-0028 slice latency).
set -u
input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
[ -z "$cmd" ] && exit 0

# Only act on git commit / push (word-boundary, allows leading env/&&/; prefixes).
echo "$cmd" | grep -qE '(^|[;&|[:space:]])git[[:space:]]+(commit|push)([[:space:]]|$)' || exit 0

root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$root" 2>/dev/null || exit 0

command -v ruff >/dev/null 2>&1 || exit 0

# Collect staged paths (+ tracked-but-unstaged when git commit -a/-am).
mapfile -t files < <(git diff --cached --name-only --diff-filter=ACM 2>/dev/null)
if echo "$cmd" | grep -qE '(^|[[:space:]])(-a|-am)([[:space:]]|$)'; then
  mapfile -t unstaged < <(git diff --name-only --diff-filter=ACM 2>/dev/null)
  files+=( "${unstaged[@]}" )
fi
if [ "${#files[@]}" -gt 0 ]; then
  tmp=$(mktemp); printf '%s\n' "${files[@]}" | sort -u > "$tmp"; mapfile -t files < "$tmp"; rm -f "$tmp"
fi
[ "${#files[@]}" -eq 0 ] && exit 0

TIMEOUT_S=60
run_to() {
  if command -v timeout >/dev/null 2>&1; then timeout "$TIMEOUT_S" bash -c "$1"
  elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$TIMEOUT_S" bash -c "$1"
  else bash -c "$1"; fi
}

failed=0; failure_msg=""
for f in "${files[@]}"; do
  [ -e "$f" ] || continue
  case "$f" in
    *.py)
      if ! out=$(run_to "ruff check '$f'" 2>&1); then
        failed=1; failure_msg="${failure_msg}ruff on $f:\n${out}\n"
      fi ;;
  esac
done

if [ "$failed" -ne 0 ]; then
  printf 'harness-gate staged-static-check (advisory, non-blocking):\n%b' "$failure_msg" >&2
fi
exit 0
