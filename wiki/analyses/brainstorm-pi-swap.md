---
title: Brainstorm — pi-executor swap (2026-05-11)
type: analysis
status: promoted
created: 2026-06-09
updated: 2026-06-09
sources:
  - wiki/raw/brainstorm-pi-swap.md
  - artifacts/brainstorming/brainstorm-symphony-pi-swap-2026-05-11.md
confidence: high
tags: [brainstorm, pi, executor-swap, rejected-designs, silent-failure, opencode-retirement]
---

# Brainstorm — Replace OpenCode with pi as Symphony's executor

Origin artifact for the pi-executor-swap plan. Documents the rejected designs, the silent-failure rationale, and the locked decisions before the plan was written. Dated 2026-05-11.

## Why this matters in the wiki

The brainstorm captures decisions whose *reasons* are easy to lose once the plan lands. The plan ([symphony-plan-history](symphony-plan-history.md#symphony-pi-executor-swap)) records *what* shipped; this brainstorm records *what was rejected and why*.

## Key themes recorded

- **opencode `--agent build` was redundant with WORKFLOW.md** — WORKFLOW.md line 9 ("You are a homelab infrastructure agent...") plus MODE: directive and domain overlays form a complete role-establishing prompt. Pi doesn't need an equivalent [source: wiki/raw/brainstorm-pi-swap.md#23-26].
- **pi has no `--dir` flag** — working directory controlled by the invoking process; Symphony must pass `Popen(cwd=str(homelab_repo_path))` [source: wiki/raw/brainstorm-pi-swap.md#27-28].
- **plane CLI shim has two latent bugs** opencode masked via the `SYMPHONY_RESULT:` marker fallback: no shebang on `plane_cli.py`, and `from schedule import ...` collides with site-packages `schedule` library because `PYTHONPATH` is filtered out of the subprocess env [source: wiki/raw/brainstorm-pi-swap.md#29-32].
- **pi exits 0 silently on auth/model misconfiguration** — confirmed locally by probing with empty `ZAI_API_KEY`: `pi -p` returned exit 0 with zero stdout/stderr. The scheduler would interpret this as "agent succeeded, no marker, no repo changes → mark Done." **Swap-blocking without mitigation** [source: wiki/raw/brainstorm-pi-swap.md#33-37].
- **CLIPROXY_API_KEY does not transfer** — pi uses per-provider env (`ZAI_API_KEY`); new secret must be provisioned in `symphony-host.env` (live mutation, James approval required) [source: wiki/raw/brainstorm-pi-swap.md#38-40].

## Candidate directions

### Direction A — Drop-in argv swap (chosen)

Replace argv shape and env allow-list. Keep prompt rendering, plane shim, scheduler logic unchanged. Smallest correct diff, scheduler untouched, tests stay structurally identical. Risks: still need to address auth-failure silent-exit and shim bugs [source: wiki/raw/brainstorm-pi-swap.md#44-50].

### Direction B — Swap + adopt `--mode json` (deferred)

Structured terminal events from pi consumed by scheduler instead of stdout-marker parsing. Kills brittle string matching, cleaner audit trail. Scheduler changes, larger blast radius. **Deferred to follow-up**, not a swap requirement [source: wiki/raw/brainstorm-pi-swap.md#52-58].

### Direction C — Pi skill or `--append-system-prompt` artifact (rejected)

Ship a Symphony-side system prompt file (C1) or skill directory (C2). **Rejected** because WORKFLOW.md already covers the role unambiguously; adding a parallel system prompt creates drift risk [source: wiki/raw/brainstorm-pi-swap.md#60-64].

## Locked decisions table

| Decision | Value | Rationale |
|---|---|---|
| Swap scope | Full swap, no opencode fallback | User-confirmed at Phase 3 |
| Plane transitions | `plane_cli.py` PATH shim + `SYMPHONY_RESULT:` marker (both; marker authoritative) | Marker already exists as fallback |
| Shim hardening | `#!/usr/bin/env python3` shebang on `plane_cli.py`; inject `PYTHONPATH=<symphony dir>` in `agent_runner.py` | Fixes latent bugs masked by marker fallback |
| Provider | `zai` direct | Closest mirror of current opencode `zai-coding-plan/glm-5.1`; opencode `CLIPROXY_API_KEY` not reusable |
| Model | `glm-5.1:high` | Native ZAI serving, thinking level high; 30-min run timeout accommodates cost |
| Context discovery | **`--no-context-files`** (originally locked) | WORKFLOW.md is sole context contract; prevents inheritance of `/home/james/AGENTS.md`, `/home/james/CLAUDE.md`, `.worktrees/**/AGENTS.md` |
| Session | `--no-session` + `PI_CODING_AGENT_SESSION_DIR=/run/symphony/pi-sessions` | Ephemeral by design |
| Output mode | text | `--mode json` deferred |
| Agent-role shape | S3 — WORKFLOW.md is contract; no `--append-system-prompt`, no `--skill` | opencode `--agent build` was redundant |
| Working directory | `Popen(cwd=str(config.homelab_repo_path))` | pi has no `--dir` flag |
| Title / labelling | Structured log `LOGGER.info("pi_dispatch issue_id=%s …", issue.id)` replaces `--title symphony-<id>` | pi has no `--title` |
| Auth-failure safety net | **M3** — startup probe (`verify_pi_support` runs one-token call against the real model) **AND** per-run guardrail (rc=0 + empty stdout + empty stderr → coerce to rc=137 in `AgentResult`) | pi exits 0 silently |

[source: wiki/raw/brainstorm-pi-swap.md#68-82]

## ⚠️ Decision revision in the landed plan

The brainstorm locked `--no-context-files`, but Codex review caught that `WORKFLOW.md` line 27 depends on homelab `AGENTS.md` safety rules. James selected "Drop `--no-context-files`"; the landed plan ([symphony-plan-history](symphony-plan-history.md#symphony-pi-executor-swap)) keeps pi context discovery enabled from `cwd=config.homelab_repo_path`. The brainstorm's "Context discovery: `--no-context-files`" row is therefore historically superseded — do not use this row as guidance for the current code.

## Failure-mode walkthrough — what changed

Of 18 failure modes audited, 15 survived the swap unchanged. The three that needed swap-time work [source: wiki/raw/brainstorm-pi-swap.md#155-173]:

| # | Signature | Fix |
|---|---|---|
| 14 | Executor dispatch failure | swap `verify_opencode_support` → `verify_pi_support` |
| 16 | `plane_cli.py` has no shebang (latent) | F1 — add shebang |
| 17 | `from schedule import` collision (latent) | F2 — inject PYTHONPATH |
| 18 | pi -p silent rc=0 on auth/model error | M3 — probe + guardrail |

## Recommended next steps (recorded in the brainstorm)

1. Hand artifact to `/Plan` as feasibility-confirmed scope; phase swap per file or one PR per repo; separate live-host mutations into follow-up approval gate; include Plane smoke ticket dry-run as verification.
2. Provision `ZAI_API_KEY` in `/home/james/plane/symphony-host.env` (now `/home/james/symphony-host.env` post-move) — live mutation, James approval required.
3. Post-swap follow-ups: Direction B (`--mode json`), label-driven AGENTS.md overlays (Direction C3b), `CLIPROXY_API_KEY` cleanup.

## Related

- [Plan history — symphony-pi-executor-swap](symphony-plan-history.md#symphony-pi-executor-swap)
- [pi-swap review specs](pi-swap-review-specs.md)
- [Service unit source](../sources/symphony-host-service-unit.md)
