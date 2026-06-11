---
title: Podium #021 — worktree opt-in and FF-only auto-merge
type: analysis
status: promoted
created: 2026-06-11
updated: 2026-06-11
sources:
  - web/api/worktree.py
  - agent_runner.py
  - plane_adapter.py
  - tracker_podium.py
  - web/api/main.py
  - tests/test_agent_runner.py
  - web/api/tests/test_worktree.py
  - web/api/tests/test_worktree_api.py
  - web/frontend/tests/worktree.spec.ts
  - .kanban/issues/021-podium-worktree-auto-merge.md
confidence: high
tags: [podium, worktree, auto-merge, git, ralph, issue-021]
---

# Podium #021 — Worktree Opt-in and FF-only Auto-merge

Issue #021 implements ADR-0005's opt-in per-Issue worktree behavior. When `worktree_active=true`, dispatch creates/reuses a persistent worktree at `worktrees/<binding>/<issue_id>` with branch `podium/<binding>/<issue_id>` and runs `pi` from that worktree cwd [source: web/api/worktree.py; agent_runner.py; tests/test_agent_runner.py].

## Worktree helper contract

`web/api/worktree.py` owns deterministic path and branch naming, worktree creation/reuse, dirty-base checks, FF-only merge, and teardown. Existing branch refs are reused when a worktree was previously removed or partially cleaned up [source: web/api/worktree.py; web/api/tests/test_worktree.py].

The dirty-base precheck treats Podium-owned nested `worktrees/` directories as ignorable because git reports them as untracked from the base checkout. Other untracked files and all tracked modifications still block auto-merge [source: web/api/worktree.py; web/api/tests/test_worktree.py].

## Dispatch path

`CandidateIssue` now carries `worktree_active`, `base_branch`, and `binding_name` through Plane and Podium candidate surfaces. `PodiumTrackerAdapter.list_candidates()` populates those fields from the `issue` row. `run_agent()` creates the worktree before launch and uses the worktree path as subprocess `cwd`; false keeps thin-engine v2 behavior and runs from the repo checkout [source: plane_adapter.py; tracker_podium.py; agent_runner.py; tests/test_agent_runner.py].

## Done transition and abort paths

`PATCH /api/issues/{id}` handles `state -> done` while `worktree_active=true`: resolve binding repo, ensure the base checkout is clean, check out `base_branch`, run `git merge --ff-only podium/<binding>/<issue_id>`, and on success remove the worktree plus branch ref. Blocking git work runs through `asyncio.to_thread` so the FastAPI event loop is not held by checkout/merge/cleanup calls [source: web/api/main.py; web/api/worktree.py; web/api/tests/test_worktree_api.py].

Abort paths set the issue back to `blocked`, append an operator-facing comment to `comments_md`, publish the final blocked row over WebSocket, and leave the worktree intact for inspection. Covered aborts: dirty base checkout, conflict/diverged base, force-pushed base, and unknown repo path [source: web/api/main.py; web/api/tests/test_worktree_api.py].

Toggling `worktree_active` from true to false while a worktree exists appends a "Worktree archived" comment and does not delete the worktree. If a combined PATCH attempts both `state="done"` and `worktree_active=false`, the merge/block outcome wins and the archive note is skipped to avoid double messaging [source: web/api/main.py; web/api/tests/test_worktree_api.py].

## UI and verification

The Issue API projects server-derived `worktree_path` and `worktree_branch` fields; the Issue flyout renders those fields when `worktree_active=true` and the issue is not Done, then clears the chip after the issue transitions to Done [source: web/api/main.py; web/frontend/lib/api.ts; web/frontend/components/IssueFlyout.tsx; web/frontend/tests/worktree.spec.ts]. Run records now store `worktree_path`, `branch_name`, and `base_branch` for active worktree dispatch, so Run detail can render the worktree row for real runs [source: scheduler.py; tests/test_trading_podium_dispatch.py; web/frontend/components/RunDetailPanel.tsx].

Verification for #021 passed initially: `uv run pytest` (545 passed, 1 skipped) and `cd web/frontend && pnpm test:e2e` (15 passed). After dev-review-claude fixes, verification passed again with `uv run pytest` (547 passed, 1 skipped), `cd web/frontend && pnpm exec tsc --noEmit`, and `cd web/frontend && pnpm test:e2e` (15 passed) [source: .kanban/issues/021-podium-worktree-auto-merge.md; .kanban/progress.md].

## Test-harness note

The auth startup missing-secret test now monkeypatches dotenv loading because a local repo `.env` can otherwise satisfy `PODIUM_SESSION_SECRET` after `monkeypatch.delenv(...)`, masking the missing-env case [source: web/api/tests/test_auth.py; web/api/tests/conftest.py].

## Claims

C-0084 .. C-0088 in [CLAIMS.md](../CLAIMS.md).
