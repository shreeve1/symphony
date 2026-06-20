# Session Capture: ADR-0017 live pass/close observation + INITIAL_REVISION 0009 fix

- Date: 2026-06-20
- Purpose: Close the two ADR-0017 open items from handoff `/tmp/handoff-XTILeb.md` — (1) live-observe the pass-no-reopen + close-stays-done contract paths that C-0285 had only test-covered, and (2) diagnose the pre-existing alembic 0009-vs-0008 schema-revision mismatch logged at podium-api's 21:34 restart.
- Scope: One live infra patrol cycle observed end-to-end; one isolated podium-api code fix committed (`web/api/schema.py`). No infra conditions were forced; no smoke comments injected.

## Durable Facts

- **ADR-0017 pass-no-reopen confirmed LIVE.** Triggering `schedule-patrol-infra` (worker code_sha=8a101eb) while aidev root fs sat at 76% (below the `pct > 80` fail threshold in `patrol_checks/infra.py:295`) produced on issue #64 (pve1, `in_review`): `POST /api/issues/64/comment 200` + `PATCH /api/issues/64 200`, comment body "Patrol pass for pve1: no OS package updates pending … Outcome: pass (consecutive_passes=1)", and **state stayed `in_review`** (no reopen). Same pattern on #65/#67/#68. — Evidence: `journalctl -u homelab-temporal-patrol-worker.service` @ 22:19; `GET /api/issues/64`.
- **ADR-0017 close-stays-done confirmed LIVE.** Issue #62 (aidev root fs) transitioned `in_review` → `done`: comment "Closing patrol ticket for aidev: root filesystem 76% used (code_sha=8a101eb) … Outcome: closed after 5 consecutive passes", posted via `/comment` BEFORE the DONE flip, and **the DONE state stuck** (no bounce back to in_review). This is the exact churn C-0281 described and ADR-0017 fixed. — Evidence: `GET /api/issues/62` (state=done, comments_md grew 6821→7023).
- **The whole infra cycle used `/comment` exclusively — zero `/reply`, zero 409.** Contrast the pre-restart 15:42 cycle (old worker pids 570812/606078) which used `/reply` and hit `409 Conflict` on #70/#71. — Evidence: journal diff between the 15:25/15:42 and 22:19 cycles.
- **A done issue legitimately reopening is NOT a contract violation.** Issue #63 (wazuh-ct122 root fs) went `done` → `running` this cycle because its disk genuinely crossed back over threshold: it closed at 79% (15:42, old code_sha=219424e) and the patrol now read **81% used** ("Patrol failure … Outcome: fail (severity=medium)"). The reopen went through `/comment` + a separate explicit `PATCH`, not the old reopen-gated `/reply`. — Evidence: `GET /api/issues/63` comments tail.
- **The alembic "0009 vs 0008" mismatch is a one-line code lag, not a DB problem.** The live DB (`/home/james/symphony/podium.db`; `/var/lib/symphony/` does not exist so `resolve_db_path` uses the repo-root fallback) is legitimately at head `0009_issue_external_id` with the `external_id` column present. `ensure_schema` warns because `INITIAL_REVISION` (the fresh-DB stamp baseline) was still `0008_fix_issue_archived_check` while the DB is at 0009. The DB is AHEAD of the baseline, not behind — `_schema_drift` finds no missing columns, so the app starts fine and the warning is a benign one-shot. **No `alembic upgrade head` and no stamp against live data is warranted.** — Evidence: `sqlite3 podium.db 'SELECT version_num FROM alembic_version'` → 0009; `web/api/main.py:429-475`; `web/api/db.py:13-21`.

## Decisions

- **Fix the lag by bumping the constant, not by touching the DB.** Set `INITIAL_REVISION = "0009_issue_external_id"` in `web/api/schema.py`. Rationale: the established pattern (commit `b26f31f` bumped 0007→0008 alongside migration 0008) is that `INITIAL_REVISION` tracks head, and `test_alembic_baseline_matches_runtime_schema` proves `SCHEMA_SQL` is the 0009 head shape. Commit `44d6b5f` (migration 0009 + external_id folded into SCHEMA_SQL) simply forgot to bump it. — Evidence: committed as symphony `188fadb`; `git log -p -S "INITIAL_REVISION =" -- web/api/schema.py`.
- **No podium-api restart forced for the fix.** Its only effects are silencing the benign startup warning on next boot and correctly stamping future fresh DBs; the running API (serving the patrol just observed) is left undisturbed. The fix applies on the next natural restart.

## Evidence

- `web/api/schema.py` (the one-line fix; symphony `188fadb`) — INITIAL_REVISION now 0009.
- `web/api/main.py:429-475` (`ensure_schema` warn-not-restamp logic), `web/api/db.py:13-21` (`resolve_db_path` fallback).
- `tests/test_alembic_baseline.py`, `web/api/tests/test_ensure_schema.py`, `web/api/tests/test_endpoints.py` — 11 passed after the bump.
- `automation/homelab-stack/src/homelab_worker/patrol_plane.py:413-555` (`record_pass`: pass-recorded / already-closed / closed paths), `:307-323` (`_post_comment_tolerating_409`, now dead insurance), `src/homelab_router/podium_adapter.py:184,276-292` (`add_comment` → `/comment`).
- `journalctl -u homelab-temporal-patrol-worker.service` 22:19 cycle (all `/comment`+`PATCH`, no `/reply`/409).

## Exclusions

- `PODIUM_API_TOKEN` (read from `/home/james/symphony-host.env`, never printed).
- Full comment bodies / transcript not archived; only the outcome lines quoted.
- The deferred dead-insurance cleanup (handoff item 3) was NOT done — see follow-ups.

## Open Questions And Follow-Ups

- **Handoff item 3 (dead-insurance cleanup) is now UNBLOCKED.** The pass-no-reopen + close-stays-done paths have now soaked live, so `_post_comment_tolerating_409` and the comment-before-state-flip ordering in `patrol_plane.py` can be dropped and `record_pass`/`record_failure` simplified, with the `### Patrol`-contract tests updated. Still low priority; let it soak a few more natural cycles first.
- **Handoff item 4 (uncommitted wiki) unchanged.** `wiki/` + `CONTEXT.md` edits remain operator-batched; this session's wiki edits add to that batch. Only `web/api/schema.py` was committed.
- podium-api will keep logging the benign mismatch warning until its next restart picks up `188fadb`.
