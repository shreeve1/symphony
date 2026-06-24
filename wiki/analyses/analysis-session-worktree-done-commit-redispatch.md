---
title: Worktree done-time commit-redispatch (ADR-0014, accepted/implemented)
type: analysis
status: promoted
created: 2026-06-18
updated: 2026-06-24
sources:
  - docs/adr/0014-worktree-done-commit-redispatch.md
  - web/api/worktree.py
  - worktree_facade.py
  - web/api/main.py
  - scheduler/__init__.py
  - CONTEXT.md
  - web/api/tests/test_worktree.py
  - web/api/tests/test_worktree_api.py
  - wiki/raw/sessions/2026-06-18-worktree-done-commit-redispatch-design.md
  - wiki/raw/sessions/2026-06-18-worktree-done-commit-redispatch-build.md
  - .kanban/issues/108-worktree-per-run-default.md
confidence: high
tags: [podium, worktree, landing, ff-merge, redispatch, operator-reply, adr-0014, self-binding]
---

# Worktree done-time commit-redispatch (ADR-0014, accepted/implemented)

A grill-me walkthrough of the Podium per-Issue worktree feature (ADR-0003 / opt-in per ADR-0005 / Podium #021) verified the lifecycle against code and surfaced a silent-data-loss gap, producing a design (ADR-0014) and a CONTEXT.md glossary correction. **ADR-0014 was implemented and `accepted` 2026-06-18 (C-0250); the silent-discard gap (C-0247) is now closed — see "Implementation landed" below.**

## Verified lifecycle

- Dispatch with `worktree_active=true` creates/reuses `worktrees/<binding>/<issue_id>` on branch `podium/<binding>/<issue_id>` from `base_branch`; the agent runs with that worktree as `cwd` and the worktree persists after the run [source: web/api/worktree.py; agent_runner.py].
- A successful run lands the Issue in `in_review`, never `done` (`scheduler/__init__.py:1699,1772`). The `done` transition is a **manual operator PATCH** — so merge-on-done never fires autonomously [source: scheduler/__init__.py; web/api/main.py].
- `state -> done` with `worktree_active=true` → `base_repo_dirty` precheck (ignores `?? worktrees/`) → `git checkout base_branch` → `git merge --ff-only` → on success `cleanup_worktree` (= `git worktree remove --force` + `git branch -D`). Failure paths (dirty base, non-FF/conflict/diverged, unknown repo) revert to `blocked`, comment, worktree kept [source: web/api/worktree.py; web/api/main.py:1272-1350].
- Not binding-type-gated: applies to any non-remote binding with `worktree_active=true`. Remote bindings (ADR-0012) force it off [source: web/api/main.py:816-818,1307-1311].

## The gap

When the agent never commits, the worktree branch equals base. `merge --ff-only` is a no-op success and `cleanup_worktree`'s `--force` removal **silently discards the uncommitted work** behind a green `done` [source: web/api/worktree.py:116-174; web/api/main.py:1339-1347]. This is the only silent-data-loss path in the feature, and it matters most for the `symphony` self-binding whose worktree holds live scheduler changes.

## Proposed decision (ADR-0014)

At done-time, classify the worktree:

1. **Clean + commits ahead** → FF-merge + teardown (unchanged).
2. **No commits ahead, or dirty** → re-dispatch the agent to commit, reusing the operator-reply machinery: append a synthetic `### Operator Reply` instructing `git add -A && git commit` (plus the pre-commit test reminder) and flip `state='todo'`. The persistent, idempotent worktree means the agent resumes on its own dirty tree [source: web/api/main.py:1074-1113; prompt_renderer.py:278-290; web/api/worktree.py:31-48].
3. **Loop guard:** re-dispatch at most twice (counted via the synthetic marker in `comments_md`); after the cap, fall back to **`blocked`** — never auto-commit un-agent-committed work into `main`.
4. Non-FF block path unchanged.

Rejected: immediate block (friction), `git add -A` auto-commit (bypasses tests, risks landing broken code), status-quo silent force-remove (data loss) [source: docs/adr/0014-worktree-done-commit-redispatch.md].

## Glossary correction

`CONTEXT.md` previously framed worktrees/landing as infra-only; the code and #021 claims (C-0084..C-0088) were already binding-agnostic. The `Run`, `Run Worktree`, `Landing`, and lifecycle-bullet terms were generalized to "any binding (coding or infra) with `worktree_active=true`" this session [source: CONTEXT.md].

## Self-binding safety

`symphony` (coding, `repo_path: /home/james/symphony`) is safe to enable: base on `main`, clean, `podium.db*`/build dirs gitignored (so `base_repo_dirty` does not false-trip); merge equals the manual landing step and triggers no restart (code inert until `symphony-restart`).

## Implementation landed (2026-06-18, C-0250)

Built from `plans/feature-worktree-done-commit-redispatch.md` via `/dev-build`. ADR-0014 flipped `proposed → accepted`.

- **Predicate refined to dirty-only.** The shipped classification re-dispatches **iff `worktree_is_dirty(...)`** — not the proposed "no commits ahead **or** dirty." A clean worktree with no commits ahead is genuinely empty and falls through to today's harmless no-op FF merge + teardown (re-dispatching it would loop pointlessly). A dirty worktree that *also* has commits ahead (partial commit) still re-dispatches, so partial work is never landed. The ADR decision prose was updated to record the refinement [source: web/api/main.py; docs/adr/0014-worktree-done-commit-redispatch.md].
- **`worktree_is_dirty(repo_path, binding, issue_id)`** runs `git status --porcelain` inside the worktree via `_run_git`; absent dir → `False`; untracked files count as dirty (unlike `base_repo_dirty`, no `?? worktrees/` excuse — a leaf worktree has no nested worktrees). Exported via `worktree_facade.py` [source: web/api/worktree.py; worktree_facade.py].
- **`_maybe_merge_worktree`** gains the classification after `worktree_exists` / before `base_repo_dirty`: dirty + `prior >= MAX_COMMIT_REDISPATCH` (2) → `_append_blocked_and_publish`; dirty + under cap → `_redispatch_to_commit`; clean → unchanged merge/teardown [source: web/api/main.py].
- **`_redispatch_to_commit`** re-reads fresh `comments_md, updated_at` (pre-PATCH `current` is stale because `patch_issue` already committed `state='done'`), appends a synthetic `### Operator Reply (Symphony auto-commit · {ts})` note (matches `prompt_renderer._OPERATOR_REPLY_RE`) naming the worktree path + branch, flips `state='todo'`, publishes, `touch_wake_sentinel()`. `_count_commit_redispatches` counts the `COMMIT_REDISPATCH_REPLY_PREFIX` substring (NULL → 0) [source: web/api/main.py; prompt_renderer.py:125].
- **Tests:** 4 unit + 5 API added; targeted suites 40 passed. Full suite 926 passed, 2 skipped, 1 pre-existing unrelated `agent_runner.py` failure (confirmed not caused by this change) [source: web/api/tests/test_worktree.py; web/api/tests/test_worktree_api.py].
- **Wave-end pi audit (`/dev-build`):** 0 critical / 1 warning / 0 note, outcome `passed`. The Warning (unguarded `WHERE id = ?` UPDATE in `_redispatch_to_commit`, no state guard) was logged not gated: it matches the pre-existing `_append_blocked_and_publish` pattern on the same operator-gated done path [source: plans/.feature-worktree-done-commit-redispatch.state.yml].

## Status

Issue #108 (2026-06-24) flips local coding bindings to default worktree isolation: `SymphonyConfig.worktree_default` / `SYMPHONY_WORKTREE_DEFAULT` defaults true, `_worktree_enabled` excludes remote bindings, local coding candidates are marked `worktree_active=True` during resume/dispatch, and Podium rows are updated so the existing done-time merge/cleanup path still owns terminal removal. The old explicit `worktree_active=true` opt-in still works; `SYMPHONY_WORKTREE_DEFAULT=false` is the kill switch [source: .kanban/issues/108-worktree-per-run-default.md; source: config.py; source: scheduler/__init__.py; source: tests/test_scheduler.py].

Feature is no longer designed as dormant/opt-in for local coding dispatch. **ADR-0014 `accepted` and implemented 2026-06-18 (C-0250); issue #108 makes the `symphony` self-binding isolation default-on for local coding runs (C-0316).**

## Claims

C-0246, C-0249 active but C-0249's "feature dormant" observation is superseded for local coding dispatch by C-0316; **C-0247 superseded (gap closed), C-0248 superseded (predicate refined), C-0250 (implemented), C-0316 (default-on local coding isolation)** — see [CLAIMS.md](../CLAIMS.md).
