---
status: accepted
relates-to: ADR-0033 (per-host/per-binding skill catalog), ADR-0038 (binding-scoped automations)
decided-with: James, 2026-07-17 (Podium issue #459 grill — continued from .handoff/handoff-20260717-090237-26938.md)
---

# Automation pin fields: extend the same per-Issue dispatch pins automations can specify at the table level

## Context

The New Issue modal already accepts per-Issue dispatch pins (preferred_skill,
preferred_agent, preferred_model, reasoning_effort, base_branch, worktree_active)
that the dispatch gate resolves against the per-binding skill catalog and the
model catalog. Operators authoring recurring automations have no equivalent
control: every fire inherits the binding-level default and the only way to pin a
specific model on a cadence is to also hand-author a throwaway Issue first — at
which point the automation's `template_title`/`template_body` no longer drive
anything. The gap-fix in this slice closes that and the two adjacent gaps that
issue #459's grill left as follow-up: making `origin='automation'` visible in
the UI and author-side validation that the loop worktree pin cannot be False.

## Decision

### 1. Pins live on the automation row

`automation` gains six nullable columns mirroring the per-Issue pin set on
`issue`:

```
preferred_skill       TEXT
preferred_agent       TEXT
preferred_model       TEXT
reasoning_effort      TEXT DEFAULT 'high'
base_branch           TEXT
worktree_active       BOOLEAN DEFAULT FALSE
```

`base_branch` is the only one with a non-null server-side default semantically
distinct from the column default — when unset on the automation, `fire_due_spawn_automations`
falls back to the binding default supplied by `tracker_podium.fire_due_spawn_automations`'s
caller; `reconcile_loop_automations` does the same. Both fire paths thread the
remaining five columns into `insert_issue_row` verbatim. This keeps the
`automation` row symmetric with `issue`'s pin columns and means an operator can
author a cadence against a brand-new model/skill without first minting a real
Issue. (Q1 of the #459 grill.)

### 2. `origin='automation'` is a third value alongside `operator` and `patrol`

Automation-spawned Issues carry `origin='automation'`. The `issue.origin` column
CHECK currently permits `'operator'` and `'patrol'`; SQLite cannot alter a
column-level CHECK in place, so migration `0023_automation_pin_fields` rebuilds
the `issue` table (mirroring `0012_retry_verdict`'s shape) with the extended
CHECK and copies every row. The rebuild's `INSERT INTO issue_new SELECT … FROM issue`
is exhaustive — `origin='patrol'` and `origin='operator'` rows survive the rebuild
unchanged, and automation-spawned Issues written from then on pass the extended
CHECK. (Q2 of the #459 grill.)

Three downstream constraints come with this:

- `web/api/main.py:IssueCreate.origin` is kept at
  `Literal["operator","patrol"] | None`. The public API contract for new
  Issues still excludes `automation` — only the spawn/loop fire paths write
  that value. This prevents operator tooling from minting `automation`-origin
  rows by hand and confusing the spawn-loop accounting.
- The frontend list endpoint's SELECT projection now includes `origin` so the
  UI can surface it (see design gap §4 below).
- The migration's rebuild pre-select list (`_ISSUE_COLUMNS`) must enumerate
  every current `issue` column in source order so `INSERT … SELECT` is a
  positional identity copy. The column ordering mirrors `SCHEMA_SQL` exactly;
  ad-hoc column drift on either side is a parity-test failure.

### 3. `base_branch` optional, falls back to binding default at fire-time

Mirrors the New Issue modal's UX, where `base_branch` already falls back to the
binding's `bindings.yml` value when the operator leaves it empty. The test
`test_spawn_automation_base_branch_override_wins_over_binding_default`
documents the contract: a non-NULL `base_branch` on the automation wins over
the caller's binding default; a NULL row takes the caller's default. (Q3 of
the #459 grill.)

### 4. Loop `worktree_active` is forced True at fire-time; reject explicit False at the API gate

Loops require a persistent worktree (operator-confirmed 2026-07-17: "loops use
worktrees"), and `reconcile_loop_automations` already hard-codes
`worktree_active=True` when calling `insert_issue_row`. With that hard-code
present, the `worktree_active` column value on a loop row is dead state — it
is stored but never read. (Q4 of the #459 grill.)

To remove the dead state without breaking existing rows or the spawn path, the
slice closes the gap **upstream** of the fire path:

- `_validate_create_for_mode` rejects `worktree_active=False` on loop CREATE
  with HTTP 422 unless the field is omitted (in which case the Pydantic
  default of `False` is filled in by the validation gate, which is why we
  also gate on `model_fields_set`).
- `_build_patch_set` (the PATCH path) rejects explicit `worktree_active=False`
  on loop rows with HTTP 422.
- The automations form sends `worktree_active: true` explicitly for loop
  CREATE so the API can distinguish a confirmed loop from a default-False
  that the validation gate would reject. The form's checkbox is hidden for
  loop mode (loops have no use for the toggle) and rendered as a small
  confirmation hint instead.

Spawn mode is unchanged: the form's `worktree_active` checkbox is forwarded
as the actual column override.

### 5. UI parity: combobox pin fields + origin chip

The New Issue modal exposes skill/agent/model as typed comboboxes sourced from
the per-binding skill catalog and the model catalog. The automations form
previously shipped with plain-text inputs in those three positions — operators
could typo into a value the dispatch gate would reject downstream. The slice
extracts `FieldCombobox` from `NewIssueModal.tsx` into
`components/FieldCombobox.tsx` and uses it on the automations form, so operator
typos fail at the form instead of at dispatch.

For `origin`, the slice adds `OriginChip` to `components/badges.tsx` and
renders it on the issue card and the flyout metadata strip. Operator-origin
rows render no chip (origin is the default and would be visual noise on every
row); `patrol` and `automation` rows render a coloured badge so spawn-loop
operators can tell at a glance which spawn path wrote an Issue.

The `AutomationPatch` model keeps `worktree_active: bool | None` and the API
no longer accepts `False` on loop rows (see §4). The `Issue` interface now
requires `origin: "operator" | "patrol" | "automation"` so a missing value is a
type error rather than a silent `undefined` at render time.

## Consequences

- Automation authors can pin model/skill/agent/effort/base_branch without
  first authoring a throwaway Issue. The pin set is symmetric with the New
  Issue modal so the dispatch gate's existing validation (`resolve_model`,
  skill catalog lookup) catches typos at fire-time regardless of source.
- `origin='automation'` is now a first-class value: automation-spawned Issues
  are visually distinct on the board and the flyout, and future code can
  branch on origin without parsing the migration-rebuild history.
- Loop `worktree_active` is no longer dead state; operators cannot
  accidentally downgrade a loop to non-worktree via the API. Existing rows
  stored before this slice are unaffected (the column accepts True the same
  way; only explicit False on edit is rejected).
- Migration `0023` adds a full row-preservation test
  (`test_0023_preserves_origin_patrol_operator_through_issue_rebuild`)
  that seeds `origin='patrol'` and `origin='operator'` rows at revision 0022,
  runs the migration to head, and asserts both origin values survive. Future
  migrations that touch `issue` should follow the same pattern.
- The pre-existing
  `tests/test_alembic_baseline.py::test_alembic_baseline_matches_runtime_schema`
  failure (column-ordinal mismatch) is **not** in this slice's scope. The
  canonical parity test in `web/api/tests/test_alembic_baseline.py` (this
  slice's file) uses a `(name, type)` fingerprint and continues to pass.

## Out of scope (deferred)

- Cross-checking pin fields against `mode` in `_validate_create_for_mode`
  beyond the worktree_active-on-loop rule. Operators can currently set
  `spawn_run_count` on a loop row or `loop_iteration_cap` on a spawn row;
  both are stored and silently ignored at fire-time. The pre-existing pattern
  for mode-aware validation already accommodates this; an explicit extension
  is left to the next session because no concrete bug drove it from issue #459.
- Authoring a per-pin-field dashboard summary (e.g., "how many spawn
  automations pin each model"). Useful once the cadence population grows; not
  blocking at current volume.
