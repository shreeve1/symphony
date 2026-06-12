---
id: 034
title: Podium — sixth `archived` issue state: migration, API, board column, Archive button
status: done
blocked_by: [033]
parent: null
priority: 0
created: 2026-06-12
updated: 2026-06-12
actor: ralph
---

## What to build

The `archived` issue state end-to-end, per
`wiki/analyses/podium-issue-archive-design.md` (decision record; design
accepted 2026-06-12). Archive is Podium's junk-disposal path so Done stays
reserved for real completions (Done is load-bearing: it triggers FF-merge for
infra issues with active worktrees).

**Schema.** New Alembic revision `0004_archived_state` rebuilding the `issue`
table CHECK constraint to `state IN ('todo','in_review','running','blocked',
'done','archived')` (SQLite cannot alter a CHECK — use batch/table-rebuild
mode, following `web/api/migrations/versions/0003_infra_role_columns.py`
conventions). Update `SCHEMA_SQL` in `web/api/schema.py` to match and bump
`INITIAL_REVISION` to `0004_archived_state`. `tests/test_alembic_baseline.py`
enforces migration/runtime parity automatically.

**API.** Add `archived` to the issue-state vocabulary: the list-filter
`Literal` (`web/api/main.py:247`) and the `IssuePatch` state field. No
transition guards — PATCH already allows any state→state change, and archive
must be reachable from every state including `running` (mid-run semantics land
in #035). Leave `ALLOWED_REPLY_STATES` unchanged: replying to an archived
issue 409s, which is correct (a reply re-dispatches; archived issues must stay
unreachable by the engine).

**Frontend.** Append `{ key: "archived", label: "Archived", dot: "bg-zinc-500" }`
as the last entry of `STATES` in `web/frontend/lib/issues.ts` — the board
column (rightmost), dashboard counts, and the flyout state chip all derive
from this array. When a binding has no stored collapse set in localStorage
(#033), default to `["archived"]` so the archived column starts collapsed; an
existing stored value is respected as-is. Add an "Archive" button in
`IssueFlyout` near the metadata chips (`data-testid="archive-issue"`), no
confirmation dialog — it PATCHes `state: "archived"`. Restore path is the
existing state chip (flip archived → any state); no dedicated button. Hide the
Archive button when the issue is already archived.

**Out of scope.** Engine guard, worktree teardown (#035), retention purge
(#036), card-hover affordance (deferred). Applying the migration to the live
`podium.db` is an operator step (services stopped, restart ritual) — this
slice only ships code, migration, and tests against fresh/test DBs; do not
restart services or touch the live DB.

## Acceptance criteria

- [x] Alembic revision `0004_archived_state` exists with working `upgrade()` and `downgrade()` (downgrade restores the five-value CHECK; document that downgrade requires no archived rows present and fails loudly otherwise).
- [x] `SCHEMA_SQL` CHECK includes `archived`; `INITIAL_REVISION` is `0004_archived_state`; `python3 -m pytest tests/test_alembic_baseline.py` passes.
- [x] `PATCH /api/issues/{id}` accepts `state: "archived"` from every other state and returns the updated row; `GET /api/bindings/{name}/issues?state=archived` filters correctly; invalid states still 422.
- [x] `POST /api/issues/{id}/reply` on an archived issue returns 409 (existing guard, regression-tested).
- [x] Board renders an Archived column rightmost; it is collapsed by default for a binding with no stored collapse set, expandable via #033 controls.
- [x] Flyout Archive button archives without confirmation; the card moves to the archived column; the state chip restores it; the button is hidden on already-archived issues.
- [x] New e2e spec covers archive-via-button, default-collapsed archived column, and restore-via-chip.

## Verification

```
cd /home/james/symphony && python3 -m pytest
cd /home/james/symphony/web/frontend && pnpm test:e2e
```

## Implementation Notes

Added the `archived` issue state across Alembic/runtime schema, API validation and filtering, board state vocabulary, flyout Archive action, and e2e coverage. Archived is the rightmost board column and defaults collapsed when a binding has no stored collapse set. Reply-to-archived returns 409 via the reply-state guard.

Verification passed: `PATH="$PWD/.venv/bin:$HOME/.local/bin:$PATH" python3 -m pytest -q`, `pnpm exec tsc --noEmit`, and `PATH="$HOME/.local/bin:$PATH" pnpm test:e2e`. Fresh Ralph review returned `PASS_WITH_NOTES` for minor stale-test-title/doc coverage notes; follow-up commits added explicit archived reply guard coverage and refreshed the stale board test title.

## Blocked by

- Blocked by #033 (archived column default-collapse requires the minimize feature).
