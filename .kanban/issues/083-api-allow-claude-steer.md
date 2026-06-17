---
id: 083
title: API — allow Claude steer for claude_persist bindings + expose flag
status: review
blocked_by: [76, 79]
parent: null
priority: 0
created: 2026-06-17
---

## What to build

Extend `POST /api/issues/{id}/steer` to accept Claude runs on `claude_persist` bindings (today it hard-rejects Claude), and expose `claude_persist` on `/api/bindings`. The steer queue + comments append are reused unchanged.

Source: `plans/warm-claude-session-and-send-keys-steer.md` tasks 7.1–7.4.

## What to build (detail)

- Add `_binding_claude_persist_for(name) -> bool` in `web/api/main.py` mirroring `_binding_pi_mode_for` (`:871`).
- Restructure the steer gating (`web/api/main.py:1262-1275`): allow when `(agent == "pi" and pi_mode == "rpc")` OR `(agent == "claude" and claude_persist)`. Remove the unconditional Claude reject (`:1263-1267`); keep a 409 for `agent == "claude"` when the binding lacks `claude_persist` (message: "enable claude_persist for live Claude steering").
- Leave the `comments_md` append and `write_steer_record` path unchanged (agent-agnostic queue; `### Operator Steer`/`### Operator Abort` headings already correct).
- Expose `claude_persist` per binding in `/api/bindings` (`web/api/main.py:644`) alongside `pi_mode`.

## Acceptance criteria

- [ ] A `steer`/`abort` on a live Claude Run whose binding has `claude_persist: true` is accepted (record written, comments appended).
- [ ] A Claude Run on a binding WITHOUT `claude_persist` is rejected 409 with the enable-flag message.
- [ ] pi RPC steer behaviour is unchanged.
- [ ] `/api/bindings` includes `claude_persist` for every binding.

## Verification

`uv run pytest tests/test_agent_runner.py tests/test_scheduler.py` and `uv run python -m py_compile web/api/main.py`

## Blocked by

- Blocked by #76 (the flag) and #79 (Claude-side steer delivery exists).
