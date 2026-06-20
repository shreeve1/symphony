# Session Capture: ADR-0017 `/comment` endpoint built, deployed, live-verified

- Date: 2026-06-20
- Purpose: Implement + deploy the non-reopening Comment primitive (ADR-0017), resolving the C-0281 patrol re-dispatch churn.
- Scope: symphony endpoint + tests + frontend splitter; homelab adapter repoint; ordered operator-gated deploy; live patrol smoke. Captured durable facts, deploy topology, and one infra gotcha.

## Durable Facts

- `POST /api/issues/{id}/comment` is the append-only Comment primitive: it mirrors `/reply`'s append + monotonic `updated_at` bump + `issue.updated` publish but drops the three reopen-coupled effects — no `state='todo'` flip, no run-state gate (works in any state incl `running`, never 409s on state grounds), no wake-sentinel touch. Body appended verbatim with a `\n\n` separator and NO injected header (attribution is caller-owned). Reuses `ReplyCreate` validation (422 empty / 400 unknown key), 404 unknown id. — Evidence: `web/api/main.py` (`comment_on_issue`), `web/api/tests/test_comment.py`
- Homelab `PodiumAdapter.add_comment` now posts to `/comment` (was `/reply`); `_reply_path` removed; the worker stamps its own `### Patrol (<iso-ts>)` header via local `datetime.now(timezone.utc).isoformat()`. `InMemoryPodiumTransport` gained a distinct `/comment` branch (verbatim append, no flip, no gate). `patrol_plane.py` logic unchanged — `_post_comment_tolerating_409` + comment-before-flip ordering are now dead insurance (`/comment` never 409s); reopen/close stay owned by the explicit `update_issue(state=…)` calls, so C-0281 churn falls out for free. — Evidence: `automation/homelab-stack/src/homelab_router/podium_adapter.py`, `automation/homelab-stack/src/homelab_worker/patrol_plane.py` (homelab `8a101eb`)
- Deploy topology (load-bearing order): symphony endpoint live first (`podium-api` restart, port 8090, `uvicorn main:app` — picks up the working tree on restart), then `podium-web` (port 8091), then the homelab patrol worker (`homelab-temporal-patrol-worker.service`, runs `python -m homelab_worker.worker` from the working tree). Worker restarted clean on `code_sha=8a101eb`, `tracker=podium binding=homelab base_url=http://127.0.0.1:8090`. — Evidence: systemd units, worker journal 2026-06-20 21:48
- Live docker patrol confirmed the contract: worker POSTed to `/api/issues/{74,75,76}/comment` → `200` (no `/reply`, no `409`); per-issue pattern was `POST …/comment` (comment lands, no flip) followed by a separate `PATCH …/issues/{id}` (record_failure's explicit `update_issue(state=TODO)` reopen). Comment + reopen are now decoupled. All three were still-failing checks (e.g. issue 74 "reclaimable=9.0GB (>5GB)") so they reopened correctly; symphony then dispatched remediation agents (74,75 → `running`). — Evidence: worker journal 2026-06-20 21:50; podium-api issue 74 comment body
- Pass-no-reopen and close-stays-done are covered by `TestPatrolPodiumReplyContract` (incl. new `test_pass_below_threshold_comments_without_reopen`) and `test_comment.py`; NOT live-observed this cycle because no docker check passed (all currently failing).

## Decisions

- Commit scoping: only the 4 symphony ADR-0017 files and 4 homelab ADR-0017 files were committed; pre-existing in-flight `CONTEXT.md`/`wiki/*` (symphony) and the Hermes/router/Plane-decommission WIP (homelab) were left untouched per the "leave in-flight files untouched" rule. — Evidence: symphony `09c852c`, homelab `8a101eb`
- James chose to batch the homelab worker restart, activating the unrelated uncommitted Hermes/router WIP alongside ADR-0017 (full homelab suite green, 723 passed). — Evidence: session decision 2026-06-20
- ADR-0017 status flipped `accepted` → `accepted; landed 2026-06-20`. — Evidence: `docs/adr/0017-comment-as-primitive-reopen-as-separate-effect.md`

## Evidence

- `web/api/main.py`, `web/api/tests/test_comment.py` — symphony endpoint + 17 contract tests (no-reopen in every state, never-409, monotonic updated_at, publish, wake-not-touched, verbatim/no-header).
- `web/frontend/components/IssueFlyout.tsx` — `### Patrol \(` added to `ENTRY_BOUNDARY` (own always-shown entry, not in `AGENT_SUMMARY_MARKERS`); `web/frontend/tests/comments-collapse.spec.ts` Playwright coverage.
- Two `/dev-build` wave diffs each passed an independent pi audit (Wave 1: 0 critical/2 warning, 1 applied; Wave 2: clean). State: `plans/.adr-0017-comment-endpoint.state.yml`.
- Symphony suite: 981 passed, 15 pre-existing failures (14 `tests/skills/*` missing-file drift, 1 flaky concurrent test — both reproduced without the change). Homelab suite: 723 passed.

## Exclusions

- No secrets/tokens (`PODIUM_API_TOKEN` sourced from `symphony-host.env`, never printed).
- Full transcript not archived.
- The host-only systemd drop-in for the pnpm gate is captured as agent memory, not wiki (host-ops, not project knowledge).

## Open Questions And Follow-Ups

- Live pass-comment-no-reopen and close-stays-done not yet observed in production (environment-dependent — needs a docker check to pass/close); confirm on the next healthy patrol cycle.
- `podium_schema_revision_mismatch` (db `0009_issue_external_id` vs code `0008_fix_issue_archived_check`) logged at podium-api startup — pre-existing alembic drift, unrelated to ADR-0017, worth a separate look.
- The retained `_post_comment_tolerating_409` + comment-before-flip ordering are now dead insurance; a later cleanup can drop them once the `/comment` contract has soaked (the `ponytail:` ceiling noted in the plan).
- `podium-web` restart requires a host-only systemd drop-in (`PNPM_CONFIG_VERIFY_DEPS_BEFORE_RUN=false`) to avoid a pnpm-11 crash-loop; not in the repo.
