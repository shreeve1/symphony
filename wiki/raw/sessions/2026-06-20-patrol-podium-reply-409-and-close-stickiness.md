# Session Capture: Patrol→Podium soak — reply-409 self-heal regression + auto-cure close stickiness

- Date: 2026-06-20
- Purpose: Watch the first live scheduled patrol→Podium cycles post-cutover (ADR-0015). Caught and fixed a workflow-fatal regression in the self-heal/reopen path and a sibling bug breaking auto-cure-to-done.
- Scope: Root causes, fixes (homelab commits `0e163be` + `219424e`), live verification, and a deferred design issue. Token-safe; no secrets captured.

## Durable Facts

- **Reply endpoint is the ONLY Podium comment mechanism and has reopen semantics.** `POST /api/issues/{id}/reply` (`web/api/main.py:1135-1158`) appends a comment AND atomically flips `state='todo'`, gated `WHERE state IN ('in_review','blocked','done') AND latest_run_state NOT IN ('queued','running')`; any other state/run → **409 Conflict**. — Evidence: `web/api/main.py:1100-1166`, `web/api/tests/test_reply.py`, `wiki/concepts/operator-reply.md`
- **Self-heal regression (root cause).** `record_failure` reopen-existing path called `update_issue(state=TODO)` BEFORE `add_comment` (→`/reply`). The TODO flip put the issue in a non-repliable state, so the failure comment 409'd deterministically; the unhandled `raise_for_status` failed `record_patrol_check_result` and the whole `PatrolWorkflow`, starving every check after the first reopened issue. — Evidence: `patrol_plane.py:375-383` (pre-fix), worker journal 15:00 cycle (`patrol-infra-scheduled-2026-06-20T15:00:00Z` Status FAILED), `temporal workflow describe`
- **Sibling bug — auto-cure close never stuck.** `record_pass` close path set `state=DONE` then posted the close comment via `/reply`; `/reply` accepts `done` and reopens it to `todo`, so a just-closed issue bounced back out of done (observed: issue 62 `closed`-outcome → `done` → reopened → dispatched → `in_review`). — Evidence: `patrol_plane.py:508-520` (pre-fix), `podium.db` issue 62 state transitions, workflow result JSON (`issue_id:62, outcome:closed`)
- **Hidden by mock/real divergence.** `InMemoryPodiumTransport`'s `/reply` fake appended unconditionally and never returned 409 (`podium_adapter.py:103-114` pre-fix), so unit tests + dry-run never saw the contract. Same class as the C-0270 bare-list and C-0271 int-id divergences.
- **The 409 race is real and expected in steady state.** `/reply` 409s when an issue has an active pi run (`latest_run_state=running`) — i.e. the patrol re-runs while a pi agent is mid-remediation. Two issues (70, 71) hit this in the second verification cycle and were tolerated (workflow COMPLETED).
- **Deferred design issue.** `/reply` reopens to `todo` on EVERY comment, so (a) pass-recorded (below-threshold) issues re-dispatch pi each cycle, and (b) a close can be clobbered back to `in_review` by a pi run dispatched during that churn. Durable fix = add a non-reopening comment endpoint to podium-api and route bot status comments through it. The reorder+tolerate-409 fix stops the workflow failures but does not stop the reopen churn.

## Decisions

- **Fix = reorder + tolerate-409 (operator-approved).** Post the comment BEFORE the caller's own state flip in `record_failure` and `record_pass` (close + pass paths); route all three reply-comment sites through a `_post_comment_tolerating_409` helper (409 = active run, non-fatal); make `InMemoryPodiumTransport` enforce the real state+run-state guard. — Evidence: homelab `0e163be` (failure path + mock + tests), `219424e` (close/pass paths + helper + tests)
- **Deferred:** the non-reopening comment endpoint (operator chose the reorder fix, deferred the durable endpoint fix). — Evidence: session decision
- **Deployment (operator-approved):** committed scoped to the 4 worker/test files (left in-flight `hosts/aidev.md`, `services/agent-zero-stack.md`, runbook docs untouched), restarted `homelab-temporal-patrol-worker.service` (now `code_sha=219424e`), and ran two manual `infra` cycles to self-heal.

## Evidence

- `automation/homelab-stack/src/homelab_worker/patrol_plane.py` — `_post_comment_tolerating_409` helper; comment-before-state-flip in `record_failure` + `record_pass`.
- `automation/homelab-stack/src/homelab_router/podium_adapter.py` — `InMemoryPodiumTransport` `/reply` now enforces the state+run-state guard and flips to todo.
- `automation/homelab-stack/tests/test_patrol_plane.py::TestPatrolPodiumReplyContract` — 4 regression tests (reopen appends comment; reopen tolerates 409 on active run; close sticks to done; close sticks when run active). Proven to fail against the old ordering.
- `automation/homelab-stack/tests/test_podium_adapter.py::TestComments` — seeded a repliable state to match the real contract.
- Full homelab-stack suite: 732 passed.
- Live: two manual `infra` cycles `COMPLETED`, dedup held (59 issues, no duplicate `external_id`), 409s on issues 70/71 tolerated, issue 63 closed→stayed `done`.

## Exclusions

- No secrets (`/home/james/symphony-host.env`, `/etc/homelab-stack/temporal-worker.env`); tokens never printed.
- In-flight operator working-tree files (`hosts/aidev.md`, `services/agent-zero-stack.md`, `runbooks/*`) intentionally not committed.

## Open Questions And Follow-Ups

- **Durable fix:** add a non-reopening comment endpoint to podium-api (`web/api/main.py`) and route patrol bot status comments through it, so pass/close comments don't reopen the issue. Until then, curing issues re-dispatch pi each cycle and a close can be transiently clobbered by an in-flight run.
- Scheduled 03:00 UTC infra cycle (and other domains' first self-heal cycles) should now COMPLETE on `code_sha=219424e` — worth a confirmation pass.
