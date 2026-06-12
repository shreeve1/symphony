# Session Capture: Issue archive ("delete button") design grilling

- Date: 2026-06-12
- Purpose: grill-me design session resolving how Podium disposes of junk issues — archive vs hard delete — plus board minimize UI and retention. Decisions accepted by James; not yet implemented.
- Scope: design decisions and the codebase facts that shaped them. No implementation occurred this session beyond two CONTEXT.md glossary edits.

## Durable Facts

- `issue` table has no archived/deleted column; `binding` has `archived` — Evidence: `web/api/schema.py:11,26-52`
- `PRAGMA foreign_keys = ON` plus `run.issue_id` (no ON DELETE) and `issue.latest_run_id` FKs mean hard-deleting an issue with Runs fails outright; purge must null `latest_run_id`, delete runs, then the issue — Evidence: `web/api/db.py:51`, `web/api/schema.py`
- Issue PATCH applies any state→state change with no transition guards — Evidence: `web/api/main.py:732-741`
- `PodiumTrackerAdapter.transition_state` is an unconditional UPDATE — a run finishing after operator archive would resurrect the issue unless guarded — Evidence: `tracker_podium.py:315-324`
- Done is load-bearing for infra issues with `worktree_active`: PATCH to done triggers FF-merge + teardown (`_maybe_merge_worktree`), so disposing junk via Done can fire a merge attempt — Evidence: `web/api/main.py:750-758`
- Board columns, counts, and the flyout state chip all derive from the `STATES` array, so a sixth state propagates through the UI automatically — Evidence: `web/frontend/lib/issues.ts:5`, `web/frontend/components/KanbanBoard.tsx:39`, `web/frontend/app/page.tsx:24`, `web/frontend/components/IssueFlyout.tsx:237-259`
- `remove_worktree` (dir + branch teardown) already exists and is reusable for archive cleanup — Evidence: `web/api/worktree.py:83`
- Code already uses "archive" for worktrees (`_maybe_archive_worktree`, "Worktree archived") — terminology collision with issue-archived noted — Evidence: `web/api/main.py:949`
- SQLite cannot alter a CHECK constraint; adding `archived` to the state CHECK is a table-rebuild migration, heavier than ADD COLUMN — Evidence: `web/api/schema.py:31`

## Decisions

All accepted by James in this session — Evidence: this capture; `CONTEXT.md` (Tracker Contract entry, edited twice this session).

1. Disposal is **archive, not hard delete** (history, run accounting, Issue Context preserved until purge).
2. Representation is a **sixth `state` value `archived`** — James explicitly rejected a new column; minimize-column UI made sixth-state the cheaper total design.
3. **Engine contract**: archived is never an engine Role. Engine never selects archived work; post-run it honors archived as terminal — no verdict state transition, worktree torn down, output discarded.
4. **Mid-run archive allowed** (reversal of an earlier forbid-with-409 decision): session runs to completion; teardown deferred to run completion. James: output not wanted, worktree deleted.
5. Coding bindings (run in bound checkout): archive mid-run lets the agent keep committing to the real repo until session end; commits stay. Accepted on record.
6. **Board UI**: general per-column minimize (−/+ collapse to narrow strip) on all columns; archived column rightmost; collapse state persisted in localStorage keyed per binding; archived collapsed by default.
7. **Button**: "Archive" button inside IssueFlyout near metadata chips, no confirmation (reversible via state chip). Card-hover affordance explicitly deferred as separate work.
8. **Retention purge from day one**: opportunistic sweep on archive PATCH + API startup; window hardcoded 14 days (James: "two weeks"); clock is `updated_at` (no archived_at column); delete order null `latest_run_id` → delete runs → delete issue in one transaction; best-effort unlink run `log_path` files.

## Evidence

- `CONTEXT.md` — Tracker Contract entry now carries the Archived state contract (two edits this session)
- `web/api/schema.py`, `web/api/main.py`, `tracker_podium.py`, `web/api/worktree.py`, `web/frontend/lib/issues.ts`, `web/frontend/components/KanbanBoard.tsx`, `web/frontend/components/IssueFlyout.tsx` — codebase facts above

## Exclusions

- No secrets, env contents, or transcript.
- ADR offered for archived-as-state; James did not take it up — recorded as declined, not written.
- Implementation details beyond accepted decisions (exact SQL, component code) intentionally not captured; they belong to the future implementation pass.

## Open Questions And Follow-Ups

- Implementation not started: CHECK-constraint table-rebuild Alembic migration must run with `symphony-host.service` (and Podium API) stopped — restart ritual applies.
- Card-hover archive affordance deferred as separate future work.
- Terminology collision: worktree "archive" wording vs issue archived state — consider renaming worktree comment wording during implementation.
- Purge of run `log_path` files interacts with existing 90-day/100-log retention (#022) — implementation should reuse or coexist cleanly.
