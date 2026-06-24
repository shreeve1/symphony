---
status: accepted
relates-to: ADR-0012 (remote binding SSH exec), ADR-0021 (issue dependencies + parallel dispatch), ADR-0023 (native per-issue review phase + auto-land)
amends: ADR-0012 — remote coding bindings now use per-issue worktrees over SSH instead of a shared remote checkout
context: n8n review runs exposed local worktree assumptions against remote repo paths and kept re-dispatching after PermissionError
---

# Remote coding worktree parity

## Decision

Remote `type: coding` bindings use the same per-issue worktree contract as local
coding bindings, but all worktree operations run over SSH on the remote host.

- Worktree path: `<remote repo>/worktrees/<binding>/<issue_id>`.
- Branch name: `podium/<binding>/<issue_id>`.
- Dispatch cwd: the remote per-issue worktree.
- Review verification cwd: the same remote worktree.
- Review dirty check and auto-land: remote `git status`, merge/rebase/cleanup over SSH.
- Dependency/lock-gated parallelism applies once remote worktrees are available; remote non-coding bindings remain serialized.

## Why

The previous ADR-0012 simplification treated remote bindings as one shared remote
checkout. That made parallel dispatch unsafe and made ADR-0023 review terminal code
try local filesystem/git operations against remote-only paths such as
`/home/itadmin/itastack/worktrees/n8n/113`.

Matching the local worktree contract removes the special case: issue isolation,
review, dirty gates, and auto-land mean the same thing for local and remote coding
bindings.

## Consequences

- Remote coding bindings can use `run_cap` with ADR-0021 dependency and lock gates.
- Remote review runs no longer touch local remote-path lookalikes.
- Remote `auto_land=true` lands the remote worktree; operator-created `auto_land=false` remains in review for operator merge.
- SSH worktree helpers are now part of the remote binding runtime surface.
