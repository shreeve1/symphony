# Session Capture: ADR-0014 worktree done-commit re-dispatch — implementation build

- Date: 2026-06-18
- Purpose: Build ADR-0014 (was `proposed`/unbuilt) from `plans/feature-worktree-done-commit-redispatch.md` via `/dev-build`. Closes the silent-discard gap (C-0247).
- Scope: Captures the implemented predicate refinement, the shipped code surface, the test coverage, and the wave-end pi audit finding. Excludes routine build chatter.

## Durable Facts

- ADR-0014 is **implemented and `accepted`** as of 2026-06-18. Status flipped `proposed → accepted` with an acceptance line citing `web/api/main.py:_maybe_merge_worktree` and `web/api/worktree.py:worktree_is_dirty`. — Evidence: `docs/adr/0014-worktree-done-commit-redispatch.md`
- **Implemented predicate is dirty-only, not the ADR's original "no commits ahead OR dirty."** Re-dispatch fires iff `worktree_is_dirty(...)` (`git status --porcelain` non-empty inside the worktree). A clean worktree with no commits ahead is genuinely empty → falls through to today's harmless no-op FF merge + teardown (re-dispatching it would loop pointlessly). A worktree that is dirty AND has commits ahead (partial commit) still re-dispatches, so partial work is never landed. ADR decision item 2 was refined in prose to match. — Evidence: `web/api/main.py` (`_maybe_merge_worktree` classification branch), `docs/adr/0014-worktree-done-commit-redispatch.md` (decision item 2 refinement note)
- New helper `worktree_is_dirty(repo_path, binding_name, issue_id) -> bool` runs `git status --porcelain` inside the worktree via `_run_git`; absent worktree dir → `False`. Unlike `base_repo_dirty`, untracked files are NOT excused (a leaf worktree has no nested Podium worktrees; untracked = real agent output). Exported through `worktree_facade.py`. — Evidence: `web/api/worktree.py`, `worktree_facade.py`
- `main.py` constants: `MAX_COMMIT_REDISPATCH = 2`, `COMMIT_REDISPATCH_REPLY_PREFIX = "### Operator Reply (Symphony auto-commit"`. `_count_commit_redispatches(comments_md)` counts the prefix substring (NULL → 0). `_redispatch_to_commit(...)` re-reads fresh `comments_md, updated_at` (the pre-PATCH `current` is stale because `patch_issue` already committed `state='done'` and bumped `updated_at`), appends a synthetic `### Operator Reply (Symphony auto-commit · {ts})` note naming the worktree path + branch and instructing test→`git add -A && git commit`, atomically flips `state='todo'`, publishes over WebSocket, calls `touch_wake_sentinel()`. — Evidence: `web/api/main.py`
- The classification sits in `_maybe_merge_worktree` after the `worktree_exists` early-return and BEFORE the `base_repo_dirty` precheck. Dirty + `prior >= MAX_COMMIT_REDISPATCH` → `_append_blocked_and_publish`; dirty + under cap → `_redispatch_to_commit`; clean → unchanged merge/teardown path. — Evidence: `web/api/main.py`
- Synthetic note header matches `prompt_renderer._OPERATOR_REPLY_RE` (`### Operator Reply\s*\([^)]*\)\s*\n`), so it surfaces as the current request on resume; a test asserts both the regex match and that `_count_commit_redispatches` counts it as 1. — Evidence: `web/api/tests/test_worktree_api.py`, `prompt_renderer.py:125`
- Tests: 4 unit (`test_worktree.py`: clean/tracked-mod/untracked/absent, plus committed-clean) + 5 API (`test_worktree_api.py`: dirty→todo, dirty-at-cap→blocked, clean-no-commits→teardown-no-redispatch, partial-commit→todo, note-regex). Targeted suites 40 passed (was 30). — Evidence: `web/api/tests/test_worktree.py`, `web/api/tests/test_worktree_api.py`

## Decisions

- Confirmed the dirty-only predicate over the ADR's looser "no commits ahead or dirty" wording, and recorded the refinement in the ADR rather than silently diverging. — Evidence: `docs/adr/0014-worktree-done-commit-redispatch.md`
- Left the unguarded `WHERE id = ?` UPDATE in `_redispatch_to_commit` (no state/run guard, unlike `reply_to_issue`). Rationale: the sibling `_append_blocked_and_publish` on the same done-merge path already UPDATEs by bare `WHERE id = ?`; the `done` transition is operator-gated and runs synchronously within one PATCH request handler. Matches existing pattern; not a regression. — Evidence: `web/api/main.py` (`_append_blocked_and_publish`, `_redispatch_to_commit`)

## Evidence

- `web/api/worktree.py`, `worktree_facade.py`, `web/api/main.py`, `docs/adr/0014-worktree-done-commit-redispatch.md`, `web/api/tests/test_worktree.py`, `web/api/tests/test_worktree_api.py` — the implementation diff (wave 1).
- `plans/.feature-worktree-done-commit-redispatch.state.yml` — `build_audits` wave-1 entry (pi reviewer, outcome `passed`, one Warning logged).
- Full suite: 926 passed, 2 skipped; 1 failure (`test_remote_agent.py::test_run_remote_agent_silent_exit_is_failure`) isolated to a pre-existing uncommitted `agent_runner.py` change unrelated to ADR-0014 (confirmed: test passes with committed `agent_runner.py`).

## Exclusions

- No secrets. Pre-existing uncommitted working-tree changes (`agent_runner.py`, frontend, other wiki edits) were not part of this build and are not captured here.

## Open Questions And Follow-Ups

- Optional hardening (audit Warning, deferred): add an atomic state guard + `rowcount==0` handling to `_redispatch_to_commit` (and to `_append_blocked_and_publish`) to match `reply_to_issue`'s concurrency posture. Not required for correctness on the operator-gated done path.
- The worktree feature remains dormant (no `worktree_active=1` row); enabling it on the `symphony` self-binding is now unblocked (C-0249).
