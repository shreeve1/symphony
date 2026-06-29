---
title: Land-on-done hardening (done means landed)
type: analysis
status: promoted
created: 2026-06-27
updated: 2026-06-27
sources:
  - plans/land-on-done-harden.md
  - redispatch_core.py
  - web/api/main.py
  - scheduler/__init__.py
  - web/api/worktree.py
  - web/frontend/components/IssueFlyout.tsx
  - web/frontend/lib/api.ts
  - web/frontend/tests/edit-state.spec.ts
  - web/api/tests/test_worktree_api.py
  - tests/test_scheduler.py
  - tests/test_redispatch_core.py
  - tests/test_tracker_podium.py
  - wiki/raw/sessions/2026-06-27-land-on-done-harden.md
  - wiki/analyses/analysis-session-worktree-done-commit-redispatch.md
confidence: high
tags: [podium, worktree, landing, done-means-landed, operator-reland, redispatch, active-run-guard, dispatch-race, adr-0014, self-binding]
---

# Land-on-done hardening (done means landed)

A `/dev-build` of `plans/land-on-done-harden.md` (converged at independent Pi-review round 3) hardened the **operator move-to-done → commit → merge → done** flow for worktree-backed issues. It folds five review findings into one coherent pass. This page extends [analysis-session-worktree-done-commit-redispatch.md](analysis-session-worktree-done-commit-redispatch.md) (ADR-0014) — it does not replace it. Build commit `67d5921`; live clean-path validation on Issue #126 (`67d5921..129f109`).

## The contract: "done means landed"

`done` is a terminal state reserved for work that is provably on `main`. Before this, `patch_issue` persisted `state='done'` upfront and then called `_maybe_merge_worktree`; a crash in that window left a durable `done` row whose work was not on `main`. Now, on the **worktree-done case** (`state→done && worktree_active`), `patch_issue` defers persisting `state` — and a combined `worktree_active` flip — and makes `_maybe_merge_worktree` the terminal-state authority [source: web/api/main.py:patch_issue; web/api/main.py:_maybe_merge_worktree].

Outcomes from `_maybe_merge_worktree`:
- `todo` — dirty worktree, re-dispatch the agent to commit (ADR-0014).
- `blocked` — conflict / base-dirty / re-dispatch cap / **missing worktree** (NEW: was a silent no-op).
- `done` — clean land proven on `main`, then `worktree_active=false` (NEW: persisted here, not before).

## The operator-reland marker (distinct from review RELAND)

A new marker pair lives in `redispatch_core.py`: `OPERATOR_RELAND_PENDING_PREFIX` / `OPERATOR_RELAND_DONE_PREFIX`, with `count_operator_reland_pending`, `operator_reland_unconsumed`, and `operator_reland_done_body`. It is **distinct** from the review `RELAND_PENDING`/`RELAND_DONE` pair [source: redispatch_core.py].

This distinct prefix is load-bearing. `tracker_podium.list_candidates` computes `review_dispatch` from `RELAND_PENDING_RE` specifically — reusing `RELAND_PENDING` for the operator path would trigger review-run reselection loops. The distinct prefix keeps an operator-done issue redispatching as a normal `todo` implement run [source: tracker_podium.py:171; tests/test_tracker_podium.py::test_operator_reland_marker_does_not_reselect_as_review_run].

## Closing the dirty-loop dead-end (scheduler)

Before this, a dirty move-to-done re-dispatched the agent to commit and set `todo`; the subsequent commit run had `review_dispatch=False`, so `_handle_review_terminal_done` returned `False` at its provenance gate and the issue parked `in_review` **forever** — the operator had to click `done` a second time. This was the #126 root cause and the "hard time getting work to auto-commit and land" pain [source: wiki/raw/sessions/2026-06-27-land-on-done-harden.md].

New `_handle_operator_reland` in `scheduler/__init__.py` is wired into the terminal-success path **before** `_handle_review_terminal_done` and independently of its provenance gate. It is gated **solely** on `operator_reland_unconsumed(comments_md)` (not on `verdict=='done'`). On every handled branch it finishes the Run row (`_finish_run_record` + `_append_terminal_output_context`) so no Run is left `running`. Its land tail mirrors the review terminal: dirty-under-`MAX_COMMIT_REDISPATCH` → re-dispatch to commit + a fresh `OPERATOR_RELAND_PENDING` marker (keeps the marker outstanding so the loop re-enters next run, no second click); dirty-at-cap → block; base repo dirty (`_review_base_repo_dirty`) → block; conflict → block; clean → `_land_review_worktree` (FF + rebase-retry) → append `operator_reland_done_body`, clear `worktree_active`, transition `done` [source: scheduler/__init__.py:_handle_operator_reland, _review_base_repo_dirty].

## Active-run guard + dispatch-race mitigation

Move-to-done is refused while a run is queued/running: `patch_issue` raises `HTTPException(409, "land not allowed during active run …")` when `latest_run_state in ACTIVE_RUN_STATES`, mirroring the schedule guard [source: web/api/main.py:patch_issue].

Because the merge runs synchronously over seconds and `done` is now deferred, the scheduler could start a run during that window. The clean path is a **split land**: call `merge_worktree()` (merge only — NOT `land_worktree()`, which calls `cleanup_worktree()` before returning and would defeat an abort); re-fetch the row; if `latest_run_state in ACTIVE_RUN_STATES`, abort via `_abort_worktree_land` (transition `in_review`, **keep** the worktree, skip cleanup, append "move to done again to retry"); otherwise `cleanup_worktree()` + `_finalize_worktree_done` (`done` + `worktree_active=false`). The remote path mirrors with `remote_worktree.merge_worktree` then `remove_worktree` [source: web/api/main.py:_maybe_merge_worktree, _abort_worktree_land, _finalize_worktree_done; web/api/worktree.py:merge_worktree, land_worktree].

**Accepted residual risk:** the synchronous-merge dispatch race is mitigated (split land + re-check), not fully closed — a run could still start between the re-check and cleanup. A cross-process landing lease would close it and is a documented deferred follow-up.

## Frontend

`IssueFlyout.tsx` `onPatch` closes only when the **returned** row's `state` is `done`/`archived` (not the requested patch state), so dirty-redispatch (`todo`) and block (`blocked`) outcomes keep the flyout open. A new inline `patch-error` surface shows the active-run 409 detail, carried through `lib/api.ts:patchIssue` (it now parses the FastAPI `detail` body rather than discarding it). New `web/frontend/tests/edit-state.spec.ts` covers both [source: web/frontend/components/IssueFlyout.tsx; web/frontend/lib/api.ts; web/frontend/tests/edit-state.spec.ts].

## Verification

- Full Python suite: **1214 passed, 2 skipped**. Affected files: 265 passed.
- Frontend e2e `edit-state.spec.ts`: 2 passed.
- Wave-end pi audit (`/dev-build`, model openai-codex/gpt-5.5): **0 critical / 1 warning / 0 note**, outcome `passed`. The warning (remote mid-merge abort path untested) was closed inline with `test_remote_land_aborts_if_run_starts_during_merge`.
- Live validation #126: drove the real `patch_issue` via the auth-free `TestClient(main.app)` pattern → rebase+FF → branch/worktree removed, `done` persisted, `worktree_active` cleared, 3 commits landed on top of `67d5921`.

## Deploy

`symphony-host.service` restarted onto `67d5921` (then `129f109` after #126 landed): running sha matched disk head, 5 bindings reconciled, `rpc_orphan_reap_done count=0`, `pi_rpc_probe_ok`, zero errors. `podium-api.service` + `podium-web.service` unchanged (the frontend `IssueFlyout.tsx`/`api.ts` changes deploy via the normal `podium-web deploy.sh` + `podium-api restart`, not symphony-host — see podium-frontend-deploy-cosmetics).

## Claims

C-0344 (`done means landed` deferred persistence), C-0345 (operator-reland marker distinct from review RELAND), C-0346 (`_handle_operator_reland` closes the dirty-loop dead-end) — see [CLAIMS.md](../CLAIMS.md). Extends ADR-0014 lineage (C-0246–C-0319).

## Open follow-ups

- ADR: the plan flagged a possible new ADR for the "done means landed" trade-off (rejected "done means committed" and "force a review run"). Deferred to James.
- Cross-process landing lease to fully close the synchronous-merge dispatch race (mitigated here, not closed).
