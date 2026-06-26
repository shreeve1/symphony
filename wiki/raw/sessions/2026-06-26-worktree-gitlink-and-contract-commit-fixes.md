# Session Capture: Worktree Gitlink and Contract Commit Fixes

- Date: 2026-06-26
- Purpose: Diagnose and resolve two major systemic auto-land issues (tracked worktree gitlinks blocking merge, and coding agents failing to commit before done, causing wasteful re-dispatches).
- Scope: Captured root cause of `base_repo_dirty` false-positives and the missing commit instruction in `prompt_renderer.py`'s `OUTPUT_CONTRACT`.

## Durable Facts

- **Tracked Worktree Gitlinks Block Land:** Per-issue worktrees were being tracked in the git index as `160000` gitlinks because `worktrees/` was not in `.gitignore`. Committed changes in a worktree register as modified in the base repo index (` M worktrees/symphony/141`), causing `base_repo_dirty` to return True and block auto-land. — Evidence: `git status --porcelain`, `web/api/worktree.py`
- **Missing Prompt Commit Instruction:** Coding agents (ADR-0011) do not have a preamble and are rendered strictly as `issue_block + OUTPUT_CONTRACT`. Because `OUTPUT_CONTRACT` had no instruction to commit files, coding agents consistently finished without committing, forcing a dirty worktree and a wasteful second auto-commit re-dispatch run (e.g. Run 478) just to commit. — Evidence: `prompt_renderer.py`

## Decisions

- **Tracked Gitlinks Mitigation:** Globally ignore `worktrees/` in `.gitignore` and untrack existing gitlink entries from the base checkout (`git rm --cached -r worktrees/`). Mirror path-anchoring checks (`line[3:].startswith("worktrees/")`) in `web/api/worktree.py` and `remote_worktree.py` to prevent any future false-positives. — Evidence: commit `b81cbf4`
- **Output Contract Hardening:** Update `OUTPUT_CONTRACT` in `prompt_renderer.py` to explicitly require agents to test, stage, and commit their own relevant changes before emitting `SYMPHONY_RESULT: done`. — Evidence: commit `279f7d6`

## Evidence

- `web/api/worktree.py` — local `base_repo_dirty` implementation
- `remote_worktree.py` — remote `base_repo_dirty` implementation
- `prompt_renderer.py` — unified `OUTPUT_CONTRACT` definition
- `tests/test_prompt_renderer.py` — regression tests for contract wording
- `web/api/tests/test_worktree.py` — regression tests for path-anchoring and modified worktrees
- `tests/test_external_id_endpoint.py` / `skill_migration.py` — repaired test-suite issue-creation schema regressions (Issue 138 description field requirements)

## Exclusions

- No secrets, credentials, or private personal data was captured or modified. No environment files were read.

## Open Questions And Follow-Ups

- Ensure that any future test database setups mock the `generate_issue_title` helper to prevent slow/flaky external LLM API calls during pytest runs.
