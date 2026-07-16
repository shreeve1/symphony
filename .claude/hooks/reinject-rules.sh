#!/usr/bin/env bash
# reinject-rules — print the post-compact reinject text to stdout.
# Single-quoted heredoc with a unique sentinel — prevents shell expansion AND
# prevents early termination if the injected text contains a line starting
# with "EOF". Auto-drafted from project CLAUDE.md invariants (no LLM rewriting).
# Fires in Claude (SessionStart compact) and Pi.
cat <<'REINJECT_EOF_SENTINEL'
Symphony standing rules (re-injected after compact):

- Git remote: use `github-personal` SSH host alias (authenticates as `shreeve1`); the default `github.com` key authenticates as `shreeve1/SSH` (wrong account).
- Modal handling: `.claude/` edits and the `rm -rf /` / `rm -rf ~` circuit breakers still prompt under `--permission-mode bypassPermissions`. `claude_runner.py` `_poll_claude_until_done` drives parked modals — Permission/Yes-No modal → Enter (blanket auto-approve, operator decision 2026-06-19); multi-choice question picker → Escape + wait `MODAL_QUESTION_SETTLE_SECONDS` + paste "proceed with your recommendations". Hard cap at `MODAL_STUCK_LIMIT` automated interactions before aborting.
- Wiki maintenance is a standing obligation before reporting done. If running as a Podium slice (ADR-0028): do NOT run `/wiki-update`, capture the "why" in the issue comment only (per-slice wiki edits collide at land time).
- Wiki auto-promotion is enabled (no James gate); promote candidates only after lint passes.
- Wiki-backed queries: read `wiki/index.md` first, then `wiki/ROUTING.md` to narrow; cite with `[source: path/to/file.md#section]`.
- Hook scripts reading stdin must use `jq -r '.tool_input.file_path // empty'` (matches the existing `.claude/hooks/format-on-edit.sh` contract).
REINJECT_EOF_SENTINEL
