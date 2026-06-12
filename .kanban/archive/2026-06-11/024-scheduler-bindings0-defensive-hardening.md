---
id: 024
title: scheduler.py:488 defensive hardening — remove implicit single-binding assumption
status: done
blocked_by: []
parent: null
priority: 2
created: 2026-06-10
updated: 2026-06-11
actor: ralph
---

## What to build

**Not-a-bug-today, defensive hardening.** Reviewer correction (from the
#012-024 review): `scheduler.run_tick` is invoked through
`main.run_bindings_loop` which calls `config.for_binding(binding)` per
binding (`config.py:230`), so `config.bindings` is always `(binding,)`
when `run_tick` runs. `scheduler.py:488` `config.bindings[0]` therefore
resolves to the binding under dispatch in production — the originally
described bug ("schedule path fires for trading because homelab is
index 0") does not manifest.

The pattern is, however, brittle: future refactors that pass a wider
`SymphonyConfig` to `run_tick` (with multiple bindings) would silently
mis-resolve. Same brittle pattern at:
- `scheduler.py:419` `_binding_approval_enabled`
- `main.py:113` render closure (binds `runtime.config.bindings[0].binding_type`)

Refactor to read `binding_type` from the issue's resolved binding
directly, removing the implicit "config has one binding" assumption.

YAML naming note: `bindings.yml` uses key `type:` (lines 3, 64), parsed
into `ProjectBinding.binding_type` in `config.py:362`. The fix uses
`binding.binding_type` consistently; both spellings are real and refer
to the same value.

Defer-or-do: low priority, independent of the Podium track. Safe to land
before, during, or after Podium ships.

## Acceptance criteria

- [x] No remaining read of `config.bindings[0].binding_type` in `scheduler.py`.
- [x] No remaining read of `runtime.config.bindings[0].binding_type` in `main.py`.
- [x] All former `is_coding` consumers now resolve binding from the issue (or are passed `binding: ProjectBinding` directly).
- [x] `tests/test_scheduler.py` continues to pass; no new regressions.
- [x] Optional: new test exercising a `SymphonyConfig` with multiple bindings in `.bindings` asserts each issue resolves its own `is_coding` correctly — defensive against future refactor.
- [x] PR description notes "defensive refactor; no observable behaviour change."

## Verification

```
cd /home/james/symphony && uv run pytest
```

## Implementation Notes

Resolved binding type through explicit `ProjectBinding` plumbing instead of implicit first-binding reads. `main.BindingRuntime` now carries the binding into prompt rendering, startup reconciliation, and `run_loop`; scheduler helpers accept or derive binding from the candidate when issue context exists. Added a multi-binding regression test proving a coding binding remains gated as coding even when an infra binding is first in `config.bindings`.

Verification passed: `uv run pytest` (573 passed, 1 skipped). Fresh Ralph review passed.

## Blocked by

None — can start immediately. Independent of Podium track. Low priority.
