# Session Capture: land-on-done hardening (done means landed)

- Date: 2026-06-27
- Purpose: Harden the operator move-to-done flow so one `done` click reliably lands a worktree-backed issue's branch to `main` (dirty → commit-redispatch → lands on the commit run, no second click), and `done` is never durable before the merge is provably on `main`. Resolve Issue #126 (parked `in_review`, unmerged clean branch) as the live validation.
- Scope: A `/dev-build` of `plans/land-on-done-harden.md` (converged at review round 3), commit + push, symphony-host restart onto the new code, live #126 clean-path land validation, and an unrelated live-DB Alembic catch-up (0011→0012). Five findings from an independent Pi review folded into one pass.

## Durable Facts

- **"done means landed" deferred-persistence contract.** `patch_issue` no longer persists `state='done'` upfront on the worktree-done path (`state→done && worktree_active`). It defers `state` (and a combined `worktree_active` flip) to `_maybe_merge_worktree`, which becomes the terminal-state authority: `todo` (dirty redispatch), `blocked` (conflict / base-dirty / cap / missing-worktree), or `done` (clean land proven on `main`). Removes the crash window where `done` was durable but the merge had not run. — Evidence: `web/api/main.py:patch_issue`, `web/api/main.py:_maybe_merge_worktree`; commit `67d5921`
- **Distinct operator-reland marker.** A new marker pair in `redispatch_core.py` — `OPERATOR_RELAND_PENDING_PREFIX` / `OPERATOR_RELAND_DONE_PREFIX` (+ `count_operator_reland_pending` / `operator_reland_unconsumed` / `operator_reland_done_body`) — is DISTINCT from the review `RELAND_PENDING`/`RELAND_DONE` pair. This is load-bearing: `tracker_podium.list_candidates` keys review-run reselection off `RELAND_PENDING_RE` specifically, so the distinct prefix does NOT trigger review reselection; an operator-done issue redispatches as a normal `todo` implement run. — Evidence: `redispatch_core.py`; `tracker_podium.py:171`; `tests/test_redispatch_core.py::test_operator_reland_marker_distinct_from_review_reland_prefix`
- **Dirty-loop dead-end closed by `_handle_operator_reland`.** Before this, a dirty move-to-done re-dispatched the agent to commit (`todo`); the subsequent commit run had `review_dispatch=False`, so `_handle_review_terminal_done` returned `False` at its provenance gate and the issue parked `in_review` forever (the operator's "hard time getting work to auto-commit and land" pain; the #126 root cause). New `scheduler/__init__py._handle_operator_reland` is wired into the terminal-success path BEFORE `_handle_review_terminal_done`, gated solely on `operator_reland_unconsumed(comments_md)` (not on `verdict=='done'`, not on the review provenance gate), and runs the same land tail (dirty-under-cap redispatch / dirty-at-cap block / base-dirty block / conflict block / clean land). — Evidence: `scheduler/__init__.py:_handle_operator_reland`; `scheduler/__init__.py` terminal path (~L2733); commit `67d5921`
- **Split-land dispatch-race mitigation + active-run 409 guard.** Never land a worktree-backed issue while a run is queued/running: `patch_issue` raises `HTTPException(409, "land not allowed during active run …")` when `latest_run_state in ACTIVE_RUN_STATES`. To handle a run starting during the synchronous merge: the clean path calls `merge_worktree()` (merge only — NOT `land_worktree()`, which cleans up before returning and would defeat an abort), re-fetches the row, and if a run appeared aborts via new `_abort_worktree_land` (transition `in_review`, keep worktree, skip cleanup, message "move to done again to retry"); else `cleanup_worktree()` + new `_finalize_worktree_done` (persists `done` + `worktree_active=false`). Residual accepted risk: the race is mitigated not closed (a run could still start between re-check and cleanup); a cross-process landing lease is a documented deferred follow-up. — Evidence: `web/api/main.py:_maybe_merge_worktree`, `_abort_worktree_land`, `_finalize_worktree_done`; `web/api/worktree.py:merge_worktree`/`land_worktree`
- **Missing-worktree now blocks, never a false done.** `_maybe_merge_worktree` previously no-op'd (returned the unchanged row) when `worktree_exists(...)` was false; in the deferred-done model that must act — it now blocks ("cannot prove landing — worktree absent"), `worktree_active` unchanged. — Evidence: `web/api/main.py:_maybe_merge_worktree`
- **Frontend closes on the returned row state.** `IssueFlyout.tsx` `onPatch` now closes only when the returned row's `state` is `done`/`archived` (not the requested patch state), so dirty-redispatch (`todo`) and block (`blocked`) outcomes keep the flyout open to show the message; a new inline `patch-error` surface shows the active-run 409 detail (carried through `lib/api.ts:patchIssue`). — Evidence: `web/frontend/components/IssueFlyout.tsx`; `web/frontend/lib/api.ts`; `web/frontend/tests/edit-state.spec.ts`
- **#126 validated clean-path live.** Drove the real `patch_issue` on #126 (`in_review`, clean worktree, unmerged `podium/symphony/126`) via the sanctioned auth-free `TestClient(main.app)` pattern (overrides `PODIUM_PASSWORD_HASH` to the test hash; no real password, no secret read): `{state:done}` → FF failed (main ahead) → rebase+FF → branch + worktree removed, `done` persisted, `worktree_active` cleared, 3 reply-draft commits landed on top of `67d5921`. — Evidence: commit `67d5921..129f109 main`; live `podium.db` #126 `state=done,worktree_active=0`
- **Live Alembic catch-up 0011→0012 (unrelated, same session).** The live `podium.db` was at `0011_issue_auto_land` while code head was `0012_retry_verdict` (the TestClient lifespan logged `podium_schema_revision_mismatch ... refusing to stamp`). Migration `0012_retry_verdict` rebuilds `issue`+`run` tables (not a plain ALTER) to widen the `verdict`/`latest_verdict` CHECK to allow `'retry'`. Applied safely: stop `podium-api`+`symphony-host` → WAL checkpoint → backup → `PODIUM_DB_PATH` pinned → `alembic upgrade head` → restart; verified rows preserved (130 issues/477 runs), `retry` write accepted, mismatch gone. — Evidence: `web/api/migrations/versions/0012_retry_verdict.py`; backups `podium.db.pre-0012.20260627T*`

## Decisions

- Operator move-to-done on a dirty worktree re-dispatches to commit AND emits an `OPERATOR_RELAND_PENDING` marker; the scheduler consumes that marker after the commit run to land — one operator click, loop closes without a second click. — Evidence: `web/api/main.py:_redispatch_to_commit`; `scheduler/__init__.py:_handle_operator_reland`
- A combined `{state:done, worktree_active:false}` PATCH defers `worktree_active` (with `state`) to the land outcome, so a blocked/dirty result leaves `worktree_active=true` (never marks a physically-intact worktree inactive). — Evidence: `web/api/main.py:patch_issue`

## Evidence

- `plans/land-on-done-harden.md` — the build plan (5 Pi-review findings folded; converged round 3)
- `redispatch_core.py` — operator-reland marker vocabulary
- `web/api/main.py` — `patch_issue`, `_maybe_merge_worktree`, `_redispatch_to_commit`, `_finalize_worktree_done`, `_abort_worktree_land`
- `scheduler/__init__.py` — `_handle_operator_reland`, `_review_base_repo_dirty`
- `web/frontend/components/IssueFlyout.tsx`, `web/frontend/lib/api.ts`, `web/frontend/tests/edit-state.spec.ts`
- `web/api/tests/test_worktree_api.py`, `tests/test_scheduler.py`, `tests/test_redispatch_core.py`, `tests/test_tracker_podium.py`
- commit `67d5921` (build) + `67d5921..129f109` (live #126 land)
- `plans/.land-on-done-harden.state.yml` — wave-end pi audit 0 critical / 1 warning (resolved: added `test_remote_land_aborts_if_run_starts_during_merge`)
- `web/api/migrations/versions/0012_retry_verdict.py` — Alembic catch-up

## Exclusions

- No secrets/credentials read. The live PATCH used the auth-free TestClient pattern (test password hash), never the real operator password or `/home/james/symphony-host.env`.
- No raw transcript archived.
- The new ADR the plan flagged ("done means landed" trade-off; rejected "done means committed" and "force a review run") is **deferred** — decision on authoring it left to James, not captured as a decision here.
- `/dev-build` advisor skip (claude-opus 429 cooling down) recorded in the build report; not durable project knowledge.

## Open Questions And Follow-Ups

- ADR: should "done means landed" be formally recorded as an ADR? Plan flagged it; deferred to James. Possible `docs/adr/0030-done-means-landed.md`.
- Deferred residual: synchronous-merge dispatch race is mitigated (split-land + re-check), NOT closed — a cross-process landing lease is the documented follow-up.
- Plan task 8.2 (#126) is now complete (clean-path validated live).
