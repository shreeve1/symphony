# Symphony

Symphony is a self-hosted AI-agent **dispatcher** — the engine that turns issues in a tracker into completed, human-reviewed work. It polls an issue tracker (Podium), renders a per-issue prompt, dispatches a pluggable coding agent (Pi or Claude) against a bound git repository in an isolated worktree, scrapes a structured verdict (`done` / `review` / `blocked`), and lands the result for human review.

It's the orchestration layer behind a self-healing homelab: recurring patrols detect infrastructure drift, file issues, and Symphony dispatches an agent to remediate them autonomously — with an approval-gated safety floor.

## What it does

- **Tracker-driven dispatch** — polls Podium for actionable issues and renders each into an agent prompt via a mandatory workflow template.
- **Pluggable agents** — a common adapter seam runs either the Pi coding agent or Claude, selected per binding.
- **Isolated worktrees** — every run executes in its own git worktree with lifecycle management, auto-merge, and reconciliation on restart.
- **Structured verdicts** — a unified output contract scrapes each run's terminal state (`done` / `review` / `blocked`) and drives the follow-up.
- **Durable & recoverable** — SQLite-backed state, Alembic migrations, startup reconcile/reaper for orphaned runs, log retention, and session continuity with delta-only resume prompts.
- **Multi-project** — `bindings.yml` maps tracked projects to repos, agents, and models; scaffold/onboard/offboard skills manage the fleet.
- **Concurrency-capped** — bounded concurrent dispatch with a defensive scheduler.

## Architecture

```
Patrol / human → Podium (issue tracker) → Symphony dispatcher
      → prompt renderer → agent adapter (Pi | Claude) in git worktree
      → structured verdict → auto-merge / human review
```

- `main.py`, `agent_runner.py` — dispatch loop and run lifecycle
- `tracker_podium.py`, `tracker_contract.py`, `tracker_adapter.py` — role-based tracker seam
- `claude_runner.py`, `claude_host.py` — Claude agent adapter (tmux-backed)
- `prompt_renderer.py` — per-issue prompt rendering from workflow templates
- `scheduler/`, `schedule.py` — recurring patrol scheduling
- `remote_worktree.py`, `worktree_facade.py` — isolated worktree lifecycle
- `web/` — Podium UI (kanban, run detail, live WebSocket updates)

## Status

Runs in production as `symphony-host.service` driving autonomous infrastructure remediation across a 4-node Proxmox homelab. Not packaged for general reuse — this repository documents the design and implementation.

## Safety

No destructive action, cluster operation without quorum, or dataset deletion executes without explicit human approval. Secrets stay out of the repo (`.env` and the state database are git-ignored).
