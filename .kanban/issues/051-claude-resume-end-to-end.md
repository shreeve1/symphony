---
id: 051
title: Claude resume end-to-end
status: pending
blocked_by: [047, 048, 049, 050]
parent: null
priority: 0
created: 2026-06-13
---

## What to build

Extend `claude_runner.py` to support Session Resume on the tmux send-keys path, reusing the decision core (#048), delta renderer (#049), and the scheduler wiring/fallback/markers established in #050.

Create-vs-resume branch, chosen by a filesystem probe of the derived session file `~/.claude/projects/<encoded-cwd>/<id>.jsonl`:

- Session file absent → first run: launch `claude --permission-mode bypassPermissions --model <m> --session-id <derive_session_id(issue.id)>`.
- Session file present → resume run: launch `claude --permission-mode bypassPermissions --model <m> --resume <derive_session_id(issue.id)>`, render the delta-only resume prompt.
- Never `--continue` (silent-fresh hazard). A missing session under `--resume` errors loud → caught → fall back to fresh + full re-feed in the same tick (`resume_failed ... fell_back=true`).

Same eligibility predicate, same `resumed`/`agent_session_sha` recording, same compaction-skip-on-resume rule as #050. Worktree lifecycle untouched.

## Acceptance criteria

- [ ] When the derived session file is absent, the launch uses `--session-id <derived>`; when present, it uses `--resume <derived>`.
- [ ] `--continue` / `-c` is never used on either path.
- [ ] Resume run renders the delta-only prompt; fallback renders full re-feed.
- [ ] A simulated `--resume` failure (nonexistent/corrupt session) falls back to a fresh session + full re-feed in the same tick and logs `resume_failed ... fell_back=true`.
- [ ] `resumed` and `agent_session_sha` are recorded for resume and fallback runs.
- [ ] Existing Claude dispatch tests (probe, reaper, completion gate, paste/submit) still pass.

## Verification

`uv run pytest tests/test_claude_runner.py tests/test_session_continuity.py -q`

## Blocked by

- Blocked by #047, #048, #049, #050
