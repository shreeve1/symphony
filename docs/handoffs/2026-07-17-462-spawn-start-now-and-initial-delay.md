# Handoff — Add "Start now" + "Initial delay" to SPAWN automations

## Goal for the next session

Add two new operator controls to the **spawn** automation form (loop mode is out
of scope), so an operator can control *when the first issue fires* independently
of the recurring interval:

1. **"Start now" checkbox** (label like *Start immediately*) — fire the first
   issue on the next scheduler tick.
2. **"Initial delay" field** — inline alongside *Interval* and *Max runs* — delay
   the *first* fire by N minutes, then recur every interval.

Operator's motivating example: "run every 15 minutes, but delay the initial
start for 60 minutes." Today the interval technically delays the first fire too,
so there's no way to say "wait 60 min once, then every 15 min."

Suggested skills: start with **`grill-with-docs`** to lock the design decisions
below (they're genuine forks), then implement. This is a full-stack change
(UI + API + DB migration + fire path), so plan it as slices.

## Critical current behavior — READ THIS FIRST (verified this session)

The first-fire timing is governed entirely by `automation.next_fire_at`:

- **Create today sets `next_fire_at = NULL`** (`web/api/automations.py` INSERT ~line
  268-277 — literal `NULL` in the VALUES).
- The spawn fire query is `WHERE ... AND (next_fire_at IS NULL OR next_fire_at <=
  ?)` (`tracker_podium.py::fire_due_spawn_automations` ~line 645). So **NULL means
  "fire on the very next tick"** — i.e. *every spawn automation already "starts
  now" today*. Interval only governs the gap between *subsequent* fires
  (`compute_next_fire` in `automation.py` advances from `now` on first fire, then
  from the prior `next_fire_at`).

This is the key insight that shapes both features:

- **"Start now" is essentially the current default** (NULL next_fire_at). The new
  work is really: make the *default* an initial delay when the operator wants
  one, and let "start now" override back to immediate.
- **"Initial delay"** = set `next_fire_at = now + delay` at **create time**
  instead of NULL. No fire-path change needed — the existing `next_fire_at <= ?`
  gate already handles it. The delay is a create-time convenience, not a stored
  column that the fire loop reads every tick.

## Recommended design (confirm with operator via grill before building)

- **Don't add a persistent `initial_delay` DB column.** It's only meaningful once,
  at creation. Instead: the API accepts an optional `start_delay_seconds` (or
  `start_delay_minutes`) on **create**, and computes `next_fire_at = now +
  delay` for the INSERT. "Start now" (or omitting delay) → `next_fire_at = NULL`.
  This keeps the schema and fire path untouched. **This is the simplest correct
  approach — push back if the next session reaches for a new column.**
  - *Alternative if operator wants to edit the delay later:* store an absolute
    `next_fire_at` and expose it as an editable "Next run at" field. Heavier;
    only do this if the operator explicitly wants post-create editing.
- **UI (minutes, matching the interval change from commit `00fd658`):** the
  Interval field is now in **minutes** (converted ×60 to `spawn_interval_seconds`
  at the UI boundary). Keep the delay in **minutes** too for consistency. A
  "Start immediately" checkbox that, when checked, disables/zeroes the delay
  field is the cleanest UX (mutually exclusive: immediate vs delayed).
- **Interaction to decide:** if "Start now" is checked AND a delay is entered,
  which wins? Recommend: checkbox wins (immediate), delay field disabled while
  checked.

## Files to touch (with anchors)

- **DB/migration:** `web/api/schema.py` (`automation` table ~line 135) — likely
  NO new column under the recommended design. If operator picks the alternative,
  add a migration under `web/api/migrations/versions/` (next rev after
  `0023_automation_pin_fields`; follow that file's idempotent ALTER pattern and
  the alembic-baseline parity test `web/api/tests/test_alembic_baseline.py`).
- **API:** `web/api/automations.py` — `AutomationCreate` model (~line 76) add
  optional `start_delay_*`; `create_automation` INSERT (~line 260-300) compute
  `next_fire_at` from the delay instead of hard NULL. `_validate_create_for_mode`
  (~line 120) — delay/start-now only valid for spawn.
- **Fire path:** `tracker_podium.py::fire_due_spawn_automations` (~632) — likely
  **unchanged** (the `next_fire_at <= now` gate already does it). Verify.
- **Timing helper:** `automation.py::compute_next_fire` (~line 36) — already
  advances correctly from an existing `next_fire_at`; confirm no change needed.
- **UI:** `web/frontend/app/[binding]/automations/page.tsx` — spawn block has
  Interval + Max runs in a `flex gap-3` row (~line 339); add the delay input
  there and the "Start immediately" checkbox. State + `submit` payload + `openEdit`
  reset, mirroring how `intervalMin` was added in commit `00fd658`. API types in
  `web/frontend/lib/api.ts` (`AutomationCreate`).
- **Tests:** backend `web/api/tests/test_automations.py` and
  `tests/test_tracker_podium.py` / `tests/test_automation.py` (assert create with
  delay sets `next_fire_at ≈ now + delay`, and start-now sets NULL / fires next
  tick). Frontend `web/frontend/tests/automations.spec.ts` (the
  "creates a new spawn automation" test already asserts the posted payload — extend
  it for delay + start-now, mirroring the `postedInterval` assertion).

## Deploy / runtime notes

- This touches **both** frontend and backend. Frontend: `web/frontend/deploy.sh`
  (build → atomic swap → restart `podium-web.service`). Backend (Python API +
  scheduler): needs a **`symphony` scheduler restart** and, if a migration is
  added, `podium-migrations.service` runs it on boot (or run alembic manually).
  Don't forget the API restart — a purely-frontend deploy won't pick up
  `automations.py` changes.
- Precedent for the earlier UI-boundary minutes conversion: commit `00fd658`.
- Automation pin-field precedent (full-stack, migration + API + UI + tests):
  ADR-0040 `docs/adr/0040-automation-pin-fields.md` and its slices — good template
  for how this feature should be structured.
- ADR-0038 `docs/adr/0038-binding-scoped-automations-spawn-and-loop.md` documents
  spawn vs loop and the one-shot scheduling relationship — read for framing;
  consider whether this feature warrants an ADR amendment (probably a small note,
  not a new ADR, since it's within the established spawn model).

## State of the tree

`main` @ `3e5fe38` has all #462 work landed. Unrelated uncommitted files in the
working tree (`bindings.yml`, `.gitignore`, `plans/.patrol-*.state.yml`, `wiki/*`,
a stray whitespace-only diff in `automations/page.tsx`) are **not ours** — leave
them alone; do not stage them (a prior commit accidentally swept staged wiki files
and had to be reverted — `git add` only your specific files). Git remote is
`origin` using the `github-personal` SSH host alias.
