#!/usr/bin/env bash
# pre-git-checks — deferred project checks gated to `git commit` / `git push`.
# Runs once, at commit/push time; blocks (exit 2) the git command if a check fails.
#   1. ruff format --check on STAGED *.py only (avoids the red repo-wide baseline)
#   2. ruff check on STAGED *.py only
#   3. `uv run pytest` over the full suite (uv venv has the deps; system python3 does not)
set -u
input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // empty')
[ -z "$cmd" ] && exit 0
# Only act on git commit / push (word-boundary, allows leading env/&&/; prefixes).
echo "$cmd" | grep -qE '(^|[;&|[:space:]])git[[:space:]]+(commit|push)([[:space:]]|$)' || exit 0

root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
cd "$root" || exit 0

# Per-check wall-clock cap (seconds). A hung check must never wedge the commit.
TIMEOUT_S=180
run_to() {  # run_to <cmd>; honors timeout/gtimeout when present, else runs bare.
  if command -v timeout >/dev/null 2>&1; then timeout "$TIMEOUT_S" bash -c "$1"
  elif command -v gtimeout >/dev/null 2>&1; then gtimeout "$TIMEOUT_S" bash -c "$1"
  else bash -c "$1"; fi
}

# --- 1 + 2: ruff on staged python files only -------------------------------
staged_py=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep -E '\.py$' || true)
if [ -n "$staged_py" ] && command -v ruff >/dev/null 2>&1; then
  if ! out=$(printf '%s\n' "$staged_py" | xargs ruff format --check 2>&1); then
    echo "Blocked by personalize-harness pre-git check: \`ruff format --check\` failed on staged files. Run \`ruff format <files>\` then re-stage before committing." >&2
    printf '%s\n' "$out" | tail -40 >&2
    exit 2
  fi
  if ! out=$(printf '%s\n' "$staged_py" | xargs ruff check 2>&1); then
    echo "Blocked by personalize-harness pre-git check: \`ruff check\` failed on staged files. Run \`ruff check --fix <files>\` then re-stage before committing." >&2
    printf '%s\n' "$out" | tail -40 >&2
    exit 2
  fi
fi

# --- 3: full test suite under the uv venv ----------------------------------
out=$(run_to "uv run pytest -q" 2>&1); rc=$?
if [ "$rc" -ne 0 ]; then
  [ "$rc" = 124 ] && note=" (timed out after ${TIMEOUT_S}s)" || note=""
  echo "Blocked by personalize-harness pre-git check: \`uv run pytest\` failed${note}. Fix before committing." >&2
  printf '%s\n' "$out" | tail -40 >&2
  exit 2
fi
exit 0
