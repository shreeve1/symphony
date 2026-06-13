---
id: 048
title: Continuity decision core (derive session id + resume eligibility)
status: review
blocked_by: []
parent: null
priority: 0
created: 2026-06-13
---

## What to build

A pure, fully unit-testable module (`session_continuity.py`) holding the Session Resume decision logic, with no dispatch/subprocess wiring:

- `derive_session_id(issue_id) -> str` — deterministic `UUIDv5(NAMESPACE, issue_id)`. Same issue always yields the same id; valid UUID for both Pi (`--session-id`) and Claude (`--session-id`/`--resume`).
- `session_file_path(agent_kind, cwd, session_id) -> Path` — resolve the agent's session-store path. Claude: `~/.claude/projects/<encoded-cwd>/<id>.jsonl` where `<encoded-cwd>` is the absolute cwd with every non-alphanumeric char replaced by `-`. Pi: under `~/.pi/agent/sessions/<cwd-slug>/` (honor `PI_CODING_AGENT_SESSION_DIR` if set).
- `evaluate_resume_eligibility(...) -> ResumeDecision` — returns `resume` or `refeed` plus a machine-readable reason, given: previous-run agent kind vs current agent kind, cwd existence/stability, session-file presence (filesystem probe), and `agent_session_sha` vs current git HEAD. ALL conditions must hold for `resume`: same agent kind ∧ cwd exists+unchanged ∧ session file present ∧ HEAD unchanged. Any failure → `refeed` with the specific reason.

This module never decides to use `--continue` — only explicit derived ids exist in its vocabulary (silent-fresh hazard banned by construction).

## Acceptance criteria

- [ ] `derive_session_id` is deterministic and returns a valid UUID string; identical for repeated calls on the same issue id, distinct across issue ids.
- [ ] `session_file_path` produces the documented Claude `<encoded-cwd>` encoding and the Pi path (with env override honored).
- [ ] `evaluate_resume_eligibility` returns `resume` only when all four conditions hold; each single-condition failure returns `refeed` with a distinct reason (agent-mismatch, cwd-missing, session-absent, sha-drift).
- [ ] No subprocess, no network, no scheduler imports in the module (pure + filesystem probe only).
- [ ] Reasons are stable string constants suitable for log markers.

## Verification

`uv run pytest tests/test_session_continuity.py -q`

## Blocked by

None — can start immediately.
