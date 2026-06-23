---
id: 105
title: Remote Claude edit+commit landing smoke on disposable checkout
status: pending
blocked_by: []
parent: 96
priority: 1
created: 2026-06-23
---

## What to build

Run one follow-up smoke for the path #104 intentionally did **not** exercise: remote Claude making an edit and committing it in a disposable remote checkout.

Keep it narrow:

1. Create a fresh disposable checkout on n8n (not `/home/itadmin/itastack`).
2. Add a temporary remote `default_agent: claude` binding, or reuse a direct harness only if it still exercises `ClaudeAgentAdapter`/`SshClaudeHost`.
3. Dispatch a tiny task that edits one throwaway file and commits it.
4. Verify the remote repo has the commit, no dirty worktree remains, and issue-specific tmux/temp/socket artifacts are gone.
5. Tear down the binding and checkout.

## Acceptance criteria

- [ ] Remote Claude creates and commits one trivial file change in the disposable checkout.
- [ ] Remote `git status --short` is clean after the run.
- [ ] Remote issue-specific tmux socket/temp dir are gone after the run.
- [ ] Temporary binding/checkout are removed after verification.

## Verification

Manual/prod-smoke evidence: run log, remote `git log -1 --oneline`, remote `git status --short`, and post-run residue check.

## Notes

#104 accepted ADR-0012 v2 based on read-only production scheduler Runs #324/#325. This follow-up exists so edit+commit landing is not hidden inside that scope note.
