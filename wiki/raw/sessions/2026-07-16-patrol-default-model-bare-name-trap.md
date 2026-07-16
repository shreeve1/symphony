# Session Capture: Patrol default model bare-name trap (issue #413)

- Date: 2026-07-16
- Purpose: Capture the live-bug investigation, root cause, and fix for `PATROL_DEFAULT_MODEL = "pi-duo"` failing `resolve_model()`.
- Scope: Read-only investigation + code fix shipped as commit `1220493` (symphony `web/api/main.py` + alembic migration `0020` + tests).

## Durable Facts

- The `PATROL_DEFAULT_MODEL` constant in `web/api/main.py` was a **bare provider name** (`"pi-duo"`); `model_catalog.resolve_model()` accepts only an exact `entry["id"]` match OR a `provider/id` form (slash-split). `"pi-duo".partition("/")` yields `("pi-duo", "", "")` — empty `wanted_id` — so the provider/id branch was guarded out by `if wanted_id:` and the resolver fell through to raise `ModelResolutionError("model 'pi-duo' is not in models.yml for agent pi")`. Evidence: `model_catalog.py:96-129`, live error reproduced on every patrol issue created since 2026-07-14.
- Live evidence: 8+ homelab patrol issues created 2026-07-14 through 2026-07-15 had `preferred_model='pi-duo'` and were blocked at the dispatch gate with `Dispatch blocked: model resolution failed: model 'pi-duo' is not in models.yml for agent pi; add it to the catalog or clear preferred_model` — every `comments_md` line was the same message, re-dispatching on every tick. Issue #407 had 30+ identical blocking comments before the fix. SQLite query: `SELECT id, state, origin, preferred_model FROM issue WHERE binding_name='homelab' AND preferred_model='pi-duo' AND state='blocked'` returned issue 407 (Blackbox probe failure for https://10.20.20.72, repeatedly re-dispatching 2026-07-15 23:40 UTC through 2026-07-16 03:13 UTC).
- **Same class of bug had also broken `Fusion Fast` (C-0366, 2026-07-11):** issue #380 in `podium.db` (created 2026-07-14, between the C-0366 and C-0368 flips) shows `preferred_model='Fusion Fast'` — but this one resolved (Fusion Fast is an exact `entry["id"]` match, not a bare provider). Only the C-0368 bare-provider flip actually broke the dispatch gate. Three consecutive default-value flips in a row shipped broken or were at risk of breaking: C-0357 `deepseek-v4-flash` (worked — exact id match), C-0366 `Fusion Fast` (worked — exact id match), C-0368 `pi-duo` (broke — bare provider name).

## Decisions

- Fix the constant to provider/id form (`"pi-duo/Duo"`) rather than redesigning `resolve_model()` to also accept bare provider names. Reason: the slash-split contract was set when bare-id uniqueness was first broken (C-0310, 2026-06-23); extending it would be a deeper schema change for what is fundamentally a one-character authoring bug.
- Backfill in-flight broken rows via alembic migration `0020` rather than force-recreating the affected patrol issues. Reason: the patrol comments + external_id dedup are live state; force-recreating would lose history and could double-fire on the next patrol cycle.
- Migration targets `preferred_model='pi-duo'` only (not `NULL`, not `Fusion Fast`) — narrows blast radius and is irreversible-safe: the source value is recoverable from the patrol comment header, the target value is the same one the create endpoint would write today.

## Evidence

- Commit `1220493`: `web/api/main.py` (1-line constant + 3-line comment), `web/api/migrations/versions/0020_patrol_issues_force_pi_duo.py` (new), `web/api/tests/test_issue_create.py` (2 assertion updates), `web/api/tests/test_alembic_baseline.py` (new `test_0020_backfills_patrol_issues_to_pi_duo`).
- Test results: `web/api/tests/test_issue_create.py` 64 passed; `web/api/tests/test_alembic_baseline.py` 3 passed; `tests/test_dispatch_gate.py` 14 passed; `tests/test_model_catalog.py` 16 passed; `tests/test_scheduler.py` 228 passed.
- Claims: C-0373 (config-fact — fix + backfill), C-0374 (gotcha — resolver trap + suggested regression-guard pattern). C-0368's notes column extended with the bare-name bug context. C-0357 and C-0366 unchanged (their values worked via exact-id match).

## Exclusions

- Did not modify `resolve_model()` itself — adding bare-provider matching would be a schema/contract change, not a fix. The gotcha is captured in C-0374 for a follow-up slice.
- Did not backfill rows older than 2026-07-14 (the deepseek-v4-flash and Fusion Fast rows are pre-existing and resolving correctly today).
- Did not restart `podium-api` — the deploy is the operator's call (rollout order in the issue comment above).

## Open Questions And Follow-Ups

- Land the regression-guard test from C-0374 (assert `(agent, provider, id)` tuple identity against the catalog, not just the constant string) before the next `PATROL_DEFAULT_MODEL` flip.
- Consider adding two near-miss error messages in `resolve_model()` (C-0374): "missing the id half of provider/id" when `wanted_id` is empty after partition, and a more specific "provider/id X/Y not found" when both halves are non-empty.
- Verify the operator's prior assumption (issue #413 first turn) — that "pi-duo/duo was supposed to be default" — by tracing C-0368 to its origin: yes, the per-agent `pi` default flipped to `Duo` and the `PATROL_DEFAULT_MODEL` was supposed to be `pi-duo/Duo`, but the value was authored as the bare provider name `pi-duo` (likely a typo or an attempt to match the catalog `provider:` field). The wiki/mechanism was correct; the constant value was wrong.
