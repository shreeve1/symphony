---
id: 129
title: Gate verified-close on origin == patrol
status: done
blocked_by: [128]
parent: null
priority: 0
created: 2026-07-02
updated: 2026-07-02
actor: ralph
---

## What to build

Scope the ADR-0020 verified-close branch so only patrol-origin issues auto-close
on a `done` verdict. Operator-created issues (`origin='operator'`) fall through
to the normal In Review terminal path, so an operator lookup like "can you lookup
the netbird deployment" parks in `in_review` until the operator sets it done —
instead of silently closing.

- `scheduler/__init__.py`, the verified-close branch (currently guarded by
  `scheduling and verdict == "done" and binding is not None and
  binding.auto_close_on_verified`): add `and candidate.origin == "patrol"`.
- Fail-safe polarity: anything not explicitly `'patrol'` (including unexpected
  values) does NOT auto-close — it falls through to the existing
  In Review terminal handling below the branch.
- Patrol behavior is unchanged: a patrol `done` still closes directly.

Add a scheduler test covering both paths:
- operator-origin `done` verdict on an `auto_close_on_verified` binding →
  transitions to `in_review` (not `done`);
- patrol-origin `done` verdict on the same binding → transitions to `done`
  (verified-close preserved).

## Acceptance criteria

- [x] Verified-close branch requires `candidate.origin == "patrol"`.
- [x] Operator-origin `done` on an auto-close binding lands `in_review`.
- [x] Patrol-origin `done` on an auto-close binding lands `done` (unchanged).
- [x] New/updated test in `tests/test_scheduler.py` asserts both transitions.

## Verification

`PATH="$HOME/.local/bin:$PATH" uv run pytest tests/test_scheduler.py -q`

## Blocked by

- Blocked by #128

## Implementation Notes

Added `and candidate.origin == "patrol"` to the ADR-0020 verified-close guard in
`scheduler/__init__.py`. Fail-safe polarity: only an explicit `'patrol'` origin
auto-closes; `'operator'`, `None`, and any unexpected value fall through to the
existing In Review terminal handling. Patrol behavior unchanged.
`tests/test_scheduler.py`: the existing verified-close test now sets
`origin="patrol"` explicitly (it previously relied on the `_candidate` default of
`'operator'`, which no longer closes); added
`test_operator_origin_done_parks_in_review_on_auto_close_binding` asserting an
operator-origin `done` on the same `auto_close_on_verified` binding lands
`in_review` (reason `agent-marker-review`). Verification
`uv run pytest tests/test_scheduler.py -q` passes (214 passed, exit 0).
