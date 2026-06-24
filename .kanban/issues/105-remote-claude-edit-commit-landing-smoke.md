---
id: 105
title: Remote Claude edit+commit landing smoke on disposable checkout
status: done
blocked_by: []
updated: 2026-06-24
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

- [x] Remote Claude creates and commits one trivial file change in the disposable checkout.
- [x] Remote `git status --short` is clean after the run.
- [x] Remote issue-specific tmux socket/temp dir are gone after the run.
- [x] Temporary binding/checkout are removed after verification.

## Verification

Manual/prod-smoke evidence: run log, remote `git log -1 --oneline`, remote `git status --short`, and post-run residue check.

Evidence log: `runs/105-remote-claude-edit-smoke.log` (ignored run artifact).

## Implementation Notes

- Used a direct Python harness instead of a temporary production binding to avoid `bindings.yml` mutation/restart while still exercising `ClaudeAgentAdapter(remote=RemotePolicy(...))` → `SshClaudeHost` → `run_claude_agent`.
- Created disposable checkout `/tmp/symphony-105-remote-claude-20260624005402-26879` on `itadmin@100.95.224.218` from `/home/itadmin/itastack`; configured repo-local git identity only in that checkout.
- Remote Claude wrote `symphony-remote-claude-smoke.txt` and committed `7f34e32 smoke: remote claude edit commit`.
- Verified remote `git status --short` was empty after the run.
- Verified no issue-specific remote `/tmp` or tmux artifacts matching `symphony-claude-105-remote-edit-smoke-*` remained.
- Removed the disposable checkout; no temporary binding was created.

## Notes

#104 accepted ADR-0012 v2 based on read-only production scheduler Runs #324/#325. This follow-up exists so edit+commit landing is not hidden inside that scope note.
