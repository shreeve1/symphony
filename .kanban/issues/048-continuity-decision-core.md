---
id: 048
title: Continuity decision core (derive session id + resume eligibility)
status: done
blocked_by: []
parent: null
priority: 0
created: 2026-06-13
updated: 2026-06-13
actor: ralph
---

## What to build

A pure, fully unit-testable module (`session_continuity.py`) holding the Session Resume decision logic, with no dispatch/subprocess wiring:

- `derive_session_id(issue_id) -> str` — deterministic `UUIDv5(NAMESPACE, issue_id)`. Same issue always yields the same id; valid UUID for both Pi (`--session-id`) and Claude (`--session-id`/`--resume`).
- `session_file_path(agent_kind, cwd, session_id) -> Path` — resolve the agent's session-store path. Claude: `~/.claude/projects/<encoded-cwd>/<id>.jsonl` where `<encoded-cwd>` is the absolute cwd with every non-alphanumeric char replaced by `-`. Pi: under `~/.pi/agent/sessions/<cwd-slug>/` (honor `PI_CODING_AGENT_SESSION_DIR` if set).
- `evaluate_resume_eligibility(...) -> ResumeDecision` — returns `resume` or `refeed` plus a machine-readable reason, given: previous-run agent kind vs current agent kind, cwd existence/stability, session-file presence (filesystem probe), and `agent_session_sha` vs current git HEAD. ALL conditions must hold for `resume`: same agent kind ∧ cwd exists+unchanged ∧ session file present ∧ HEAD unchanged. Any failure → `refeed` with the specific reason.

This module never decides to use `--continue` — only explicit derived ids exist in its vocabulary (silent-fresh hazard banned by construction).

## Acceptance criteria

- [x] `derive_session_id` is deterministic and returns a valid UUID string; identical for repeated calls on the same issue id, distinct across issue ids.
- [x] `session_file_path` produces the documented Claude `<encoded-cwd>` encoding and the Pi path (with env override honored).
- [x] `evaluate_resume_eligibility` returns `resume` only when all four conditions hold; each single-condition failure returns `refeed` with a distinct reason (agent-mismatch, cwd-missing, session-absent, sha-drift).
- [x] No subprocess, no network, no scheduler imports in the module (pure + filesystem probe only).
- [x] Reasons are stable string constants suitable for log markers.

## Verification

`uv run pytest tests/test_session_continuity.py -q`

## Blocked by

None — can start immediately.

## Implementation Notes

Added `session_continuity.py` with deterministic UUIDv5 session ids, Claude and Pi session-file path resolution, and pure resume eligibility decisions with stable `resume`/`refeed` actions plus machine-readable reasons. Added `tests/test_session_continuity.py` covering id derivation, path resolution, env override behavior, timestamped Pi session discovery, all eligibility branches, and the no-subprocess/no-network/no-scheduler purity guard.
