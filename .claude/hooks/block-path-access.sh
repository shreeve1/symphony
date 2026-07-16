#!/usr/bin/env bash
# block-path-access — block writes to protected paths + symlink escapes outside
# the project root. Writes only (no Read registration). Deterministic; no model calls.
# .env file exists in this repo (has:env-file) — protecting secret material.
# Fires in Claude (PreToolUse Edit|Write|MultiEdit) and Pi (harness-gates adapter).
set -u
input=$(cat)
tool=$(printf '%s' "$input" | jq -r '.tool_name // empty')
path=$(printf '%s' "$input" | jq -r '.tool_input.file_path // .tool_input.path // empty')
[ -z "$path" ] && exit 0

root="${CLAUDE_PROJECT_DIR:-$(pwd)}"
rootreal=$(cd "$root" 2>/dev/null && pwd -P) || rootreal="$root"

# Realpath of the deepest existing ancestor, then re-append the missing tail —
# catches new-file writes through a symlinked parent directory.
resolve_real() {
	local t cur tail base
	t="$1"
	case "$t" in /*) ;; *) t="$root/$t" ;; esac
	cur="$t"
	tail=""
	while [ ! -e "$cur" ] && [ "$cur" != "/" ]; do
		base=$(basename "$cur")
		cur=$(dirname "$cur")
		tail="$base${tail:+/$tail}"
	done
	if [ -d "$cur" ]; then cur=$(cd "$cur" 2>/dev/null && pwd -P); fi
	printf '%s' "${cur%/}${tail:+/$tail}"
}
real=$(resolve_real "$path")
rel="${real#"$rootreal"/}"
base=$(basename "$path")

write_block=(
	".env"
	".env.*"
	"*.pem"
	"id_rsa"
	"*.key"
	"*.keystore"
)
write_allow=(".env.example" ".env.sample" ".env.template")

matches() {
	local cand="$1"
	shift
	local p
	for p in "$@"; do case "$cand" in $p) return 0 ;; esac done
	return 1
}

case "$tool" in
Edit | Write | MultiEdit)
	# Symlink / traversal escape: a write resolving outside the project root is blocked.
	case "$real" in
	"$rootreal" | "$rootreal"/*) ;;
	*)
		echo "Blocked by harness-gate: write resolves outside project root ($real)." >&2
		exit 2
		;;
	esac
	if matches "$base" "${write_allow[@]}"; then exit 0; fi
	if matches "$base" "${write_block[@]}" || matches "$rel" "${write_block[@]}"; then
		echo "Blocked by harness-gate: writes to protected path '$rel' are blocked." >&2
		exit 2
	fi
	;;
esac
exit 0
