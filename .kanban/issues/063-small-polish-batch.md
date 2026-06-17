---
id: 063
title: Small polish batch — renderer-shim rename, KNOWN_AGENTS, entity-decode
status: in-progress
blocked_by: []
parent: null
priority: 0
created: 2026-06-17
---

## What to build

Three independent Phase-2 polish edits from `.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`. Lands before the scheduler split (serializes the first `scheduler.py` edit of the chain).

- **L0-01** — rename `scheduler.py:593`'s `_render_candidate_prompt` (the signature-adapter shim that forwards `resume=` only when the renderer accepts it) to `_invoke_renderer`; update its call site at `scheduler.py:722`. Do **not** touch `main.py:53`'s `_render_candidate_prompt` (the `CandidateIssue → IssueData` mapper) — they share a name but do different jobs; this only de-collides the name.
- **L5-03** — collapse the valid-agent set (`{"pi","claude"}`) to one source. `model_catalog.py:18` already has `KNOWN_AGENTS`; make `config.py:565` `_validate_agent` and the `agent_runner.py:1033-1036` `RoutingAgentAdapter` literals reference a single shared constant.
- **L4-01** — extract `_decode_entity_at(s, i) -> tuple[str, int] | None` in `schedule.py` (the `s.find(";")` + `html.unescape` mechanics duplicated at `:225-249`, `:256-282`, `:325-350`). The three branches keep their distinct decoded-char handling (quote-toggle vs verbatim) but call the shared helper. Control flow stays intact under the existing round-4-audit tests.

## Acceptance criteria

- [ ] `scheduler.py` has no `_render_candidate_prompt`; the shim is named `_invoke_renderer` and its call site is updated. `main.py`'s mapper is unchanged.
- [ ] The `{"pi","claude"}` agent set is defined once; `config._validate_agent` and `agent_runner` `RoutingAgentAdapter` reference the shared constant.
- [ ] `schedule.py` defines `_decode_entity_at`; the three entity-decode branches call it; the normalizer's control flow is unchanged.
- [ ] `uv run pytest` passes (round-4-audit schedule tests included).

## Verification

`uv run pytest`

## Blocked by

None — can start immediately.
