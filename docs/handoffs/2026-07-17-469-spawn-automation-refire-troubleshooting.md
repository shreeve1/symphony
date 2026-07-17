# Handoff — Troubleshoot spawn automations firing once but not re-firing

## Symptom (operator report)

A **spawn** automation fires its **first** issue, but the **next** issue never
fires at the interval it should. Concrete example to reproduce against:
**`pi-rmm` binding, automations creating GitHub issues** (operator saw the first
issue appear, subsequent ones did not).

This is a **troubleshooting** task, not a known bug — the fire-path code was
traced this session and is **algorithmically correct** (see "What was verified"
below). The failure is almost certainly **environmental / runtime state**, so
start by collecting evidence from the live DB and scheduler logs before touching
code.

## First: collect evidence (do this before reading code)

Run these against the live Podium DB and the `symphony-host.service` journal.
The DB path resolves via `resolve_db_path()` (usually `podium.db` at repo root /
data dir — confirm with the service's working dir).

1. **Automation row state** — the single most diagnostic query:
   ```sql
   SELECT id, binding_name, enabled, occurrences_fired, spawn_run_count,
          spawn_interval_seconds, next_fire_at, updated_at
   FROM automation
   WHERE mode = 'spawn' AND binding_name = 'pi-rmm';
   ```
   Interpret:
   - `enabled = 0` + `occurrences_fired >= spawn_run_count` → **not a bug**, the
     automation hit its Max-runs cap and correctly disabled (tracker_podium.py:705,
     `enabled = run_count is None or ordinal < int(run_count)`). Common if the
     operator set Max runs = 1.
   - `enabled = 1`, `occurrences_fired = 1`, `next_fire_at` in the **future** →
     it fired once and is waiting; check whether the tick is actually running and
     whether `next_fire_at` is further out than expected (interval-units bug — see
     hypothesis 3).
   - `enabled = 1`, `occurrences_fired = 1`, `next_fire_at` in the **past** →
     it's due but not being fired → scheduler isn't calling fire for this binding
     (hypothesis 1) OR the insert keeps failing and rolling back (hypothesis 2).
   - `occurrences_fired` stuck at 1 with `updated_at` advancing every ~30s →
     repeated failed insert + rollback (hypothesis 2 — check logs for the
     exception).

2. **Scheduler logs** — grep the journal:
   ```
   journalctl -u symphony-host.service --since "-2h" | \
     grep -E "spawn_automations_fired|automation_fire_failed|fire_due"
   ```
   - `automation_fire_failed binding=pi-rmm error=...` → **hypothesis 2**, the
     exception detail is the root cause. (Logged at scheduler/loop.py:188.)
   - `spawn_automations_fired binding=pi-rmm count=N` only once → fired once then
     stopped becoming due, or the binding loop stopped (hypothesis 1/3).
   - **No `fire_due`/`spawn_automations` lines mentioning pi-rmm at all** after
     the first fire → the pi-rmm `run_loop` may not be running (hypothesis 1).

3. **Is a run_loop actually running for pi-rmm?** Fire is **per-binding**
   (scheduler/loop.py:182 passes `binding=loop_binding`). Each scheduler process
   runs one binding's `run_loop`. Confirm the pi-rmm scheduler process/binding is
   in the running set (check the service, `bindings.yml`, and startup logs for
   the binding list). If pi-rmm has no live loop, fire is simply never called
   again.

4. **First spawned issue state** (rules out a downstream gate):
   ```sql
   SELECT id, external_id, state, hold, approval_required, created_at
   FROM issue WHERE origin = 'automation' AND binding_name = 'pi-rmm'
   ORDER BY id;
   ```
   Confirm only `automation:<id>:1` exists (never `:2`). If `:2` **does** exist
   but didn't dispatch, the problem is downstream dispatch, not the fire path.

## What was verified this session (fire path is correct)

Traced end-to-end; all correct — do **not** waste time re-deriving these:

- **`compute_next_fire`** (automation.py:36-51): first fire advances from `now`
  (`current_next_fire_at=None` → `now + interval`); subsequent fires advance from
  the **stored** `next_fire_at` (`stored + interval`). Correct, no drift.
- **Fire SELECT** (tracker_podium.py:647-652):
  `WHERE binding_name=? AND mode='spawn' AND enabled=1 AND (next_fire_at IS NULL
  OR next_fire_at <= ?)`. NULL-safe first fire; time-gated thereafter. Correct.
- **Enable logic** (tracker_podium.py:705): stays `1` for unlimited
  (`run_count is None`); disables only at count exhaustion. Correct.
- **`external_id`** (tracker_podium.py:684): `automation:<id>:<ordinal>` — unique
  per ordinal, so the UNIQUE index on `issue.external_id` (schema.py:69) does
  **not** dedupe the second fire. Correct.
- **Transaction boundary** (tracker_podium.py:640 `with self.connect()`): the
  loop inserts the issue + advances the automation row, then `commit()`s once.
  On an insert exception the SQLite context manager **rolls back** — so a failed
  insert does **not** advance `next_fire_at`; the automation retries next tick.
  (This means hypothesis 2 presents as `occurrences_fired` stuck at 1 with the
  error logged every tick, not as a silently-skipped fire.)

## Root-cause hypotheses (ranked)

1. **Max runs = 1 (or finite count already exhausted).** Most common false
   alarm. `spawn_run_count = 1` → after the first fire `ordinal(2) < 1` is false
   → `enabled = 0`. Working as designed. **Verify with query 1.** If this is it,
   the answer to the operator is "set Max runs empty (unlimited) or higher."

2. **Scheduler not firing for the pi-rmm binding.** Either the pi-rmm `run_loop`
   isn't running (no per-binding loop → fire never called again — scheduler/loop.py:182)
   or `fire_spawn_automations` keeps raising on the second insert and rolling back
   (scheduler/loop.py:184-188, `automation_fire_failed`). **Verify with queries
   2 + 3.**

3. **Interval units / next_fire_at too far out.** UI sends
   `spawn_interval_seconds = minutes × 60` (page.tsx). If a row has an interval in
   the wrong unit (e.g. an old row, or minutes stored as seconds), `next_fire_at`
   could be pushed far into the future so it never becomes due within the
   observation window. **Verify with query 1**: compare `spawn_interval_seconds`
   to what the operator entered, and check `next_fire_at − updated_at ≈ interval`.
   Also note the **poll interval defaults to 30s** (`config.py:190`,
   `SYMPHONY_POLL_INTERVAL_MS`); a spawn interval finer than the tick can't fire
   faster than ~30s.

4. **Downstream dispatch gate** (only if `automation:<id>:2` exists but no run).
   The first issue holds a lock / worktree / concurrency slot, or is
   `hold`/`approval_required`, blocking the second. **Verify with query 4** and
   the dispatch logs. This is a dispatch problem, not a fire problem.

## Suggested approach for next session

1. Run the four evidence queries/greps above; the automation-row query alone
   usually decides between hypotheses 1, 2, and 3.
2. If logs are silent, add temporary debug logging at the fire entry/SELECT to
   confirm the tick is running for pi-rmm and what the SELECT returns:
   - tracker_podium.py ~640 (entry): log `binding_name` + `now_iso`.
   - tracker_podium.py ~652 (after SELECT): log row count + each
     `(id, next_fire_at)`.
   Then watch a few ticks (poll interval ~30s) and re-check DB state.
3. Only after the hypothesis is confirmed by evidence, decide on a fix. Likely
   outcomes: operator config fix (Max runs), a genuine runtime bug in
   per-binding loop scheduling, or a units migration for old rows.

## Reference files (with anchors)

- **Timing helper:** `automation.py:36` (`compute_next_fire`).
- **Fire path:** `tracker_podium.py:632` (`fire_due_spawn_automations`) — SELECT
  647-652, insert 675-689, advance/commit 698-707.
- **Scheduler call site:** `scheduler/loop.py:182` (`_fire_spawn_automations`,
  per-binding), wrapper `scheduler/reconcile.py:152` (`fire_spawn_automations`).
- **Poll interval:** `config.py:190` (`poll_interval_ms`, default 30000).
- **Issue insert + external_id uniqueness:** `web/api/issue_create.py`
  (`insert_issue_row`), UNIQUE index `web/api/schema.py:69`.
- **Design:** ADR-0038 `docs/adr/0038-binding-scoped-automations-spawn-and-loop.md`
  (spawn vs loop, one-shot scheduling); ADR-0040 for pin fields.
- **Feature context:** the create/edit scheduling controls (Start immediately /
  Initial delay) landed under #462/#469 —
  `docs/handoffs/2026-07-17-462-spawn-start-now-and-initial-delay.md`. Note these
  only affect the **first** `next_fire_at`; they do not touch the recurring
  advance, so they are unlikely to be the cause but worth knowing when reading
  `next_fire_at`.

## State of the tree

Handoff-only change on `main`. All #462/#469 spawn-automation work is landed and
deployed (commits `e657954`, `4da51c6`, `99bb299`, `91abc59`, `fe51042`). Git
remote is `origin` via the `github-personal` SSH host alias. `git add` only this
handoff file — leave any unrelated working-tree files alone.
