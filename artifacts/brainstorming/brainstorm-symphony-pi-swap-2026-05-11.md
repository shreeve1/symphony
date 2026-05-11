# Brainstorm: Replace OpenCode with pi as Symphony's executor

## Context

Symphony today dispatches agents via `opencode run --agent build --dir <repo>
[--model <m>] --title symphony-<id> <prompt>` from `agent_runner.py`. We want
to replace OpenCode entirely with the `pi` coding tool
(`@mariozechner/pi-coding-agent`, installed locally at version `0.74.0` at
`/home/james/.npm-global/bin/pi`). The Plane state-transition contract
(`plane_cli.py` PATH shim, `SYMPHONY_RESULT:` stdout marker) and prompt
rendering (`WORKFLOW.md` + `prompt_renderer.py`) stay intact.

This was a normal brainstorm (not a `dev-validate` handoff). Project review
was performed: we audited `agent_runner.py`, `config.py`, `plane_cli.py`,
`prompt_renderer.py`, `scheduler.py`, the systemd unit env, and pi's CLI
surface. Targeted web research was attempted but the research subagent
errored on provider config; pi's local `--help` and `--list-models` output
gave a complete picture without external sources, so no additional
research was performed.

## Key Themes

- **opencode `--agent build` was redundant with WORKFLOW.md.** WORKFLOW.md
  line 9 (`"You are a homelab infrastructure agent..."`) plus the MODE:
  directive and domain overlays form a complete role-establishing prompt.
  Pi doesn't need an equivalent.
- **pi has no `--dir` flag.** Working directory is controlled by the
  invoking process — Symphony must pass `Popen(cwd=str(homelab_repo_path))`.
- **The plane CLI shim has two latent bugs** that opencode masks via the
  `SYMPHONY_RESULT:` marker fallback: no shebang on `plane_cli.py`, and
  `from schedule import ...` collides with the site-packages `schedule`
  library because `PYTHONPATH` is filtered out of the subprocess env.
- **pi exits 0 silently on auth/model misconfiguration.** Confirmed by
  probing with empty `ZAI_API_KEY`: `pi -p` returned exit 0 with zero
  stdout and zero stderr. The scheduler would interpret this as "agent
  succeeded, no marker, no repo changes → mark Done." Swap-blocking
  without mitigation.
- **CLIPROXY_API_KEY does not transfer.** pi uses per-provider env
  (`ZAI_API_KEY`). A new key must be provisioned in `symphony-host.env`
  (live mutation, James approval required).

## Candidate Directions Considered

### Direction A — Drop-in argv swap (chosen)
Replace argv shape and env allow-list. Keep prompt rendering, plane shim,
scheduler logic unchanged.

- Benefits: smallest correct diff, scheduler untouched, tests stay
  structurally identical.
- Risks: still need to address auth-failure silent-exit and shim bugs.

### Direction B — Swap + adopt `--mode json`
Add structured terminal events from pi consumed by scheduler instead of
relying on stdout-marker parsing.

- Benefits: kills brittle string matching, cleaner audit trail.
- Risks: scheduler.py changes, larger blast radius.
- Decision: **defer to follow-up**. Not a swap requirement.

### Direction C — Pi skill or `--append-system-prompt` artifact (rejected)
Ship a Symphony-side system prompt file (C1) or skill directory (C2).

- Decision: **rejected (S3 chosen)**. WORKFLOW.md already covers the role
  unambiguously. Adding a parallel system prompt creates drift risk.

## Locked Decisions

| Decision | Value | Rationale |
|---|---|---|
| Swap scope | Full swap, no opencode fallback | User-confirmed at Phase 3 |
| Plane transitions | `plane_cli.py` PATH shim + `SYMPHONY_RESULT:` marker (both, marker authoritative) | User-confirmed; marker already exists as fallback |
| Shim hardening | Add `#!/usr/bin/env python3` to `plane_cli.py`; inject `PYTHONPATH=<symphony dir>` in `agent_runner.py` | Fixes latent bugs masked by marker fallback today |
| Provider | `zai` direct | Closest mirror of current opencode `zai-coding-plan/glm-5.1`; opencode `CLIPROXY_API_KEY` not reusable by pi |
| Model | `glm-5.1:high` | User-selected; native ZAI serving, thinking level high; 30-min run timeout accommodates the cost |
| Context discovery | `--no-context-files` | WORKFLOW.md is the sole context contract; prevents surprise inheritance of `/home/james/AGENTS.md`, `/home/james/CLAUDE.md`, `.worktrees/**/AGENTS.md`, and `agent-instructions/**/AGENTS.md` |
| Session | `--no-session` + `PI_CODING_AGENT_SESSION_DIR=/run/symphony/pi-sessions` | Ephemeral by design; prevents state leakage that motivated `--model` workaround in opencode |
| Output mode | text | Defer `--mode json` to a follow-up |
| Agent-role shape | S3 — WORKFLOW.md is contract; no `--append-system-prompt`, no `--skill` | opencode `--agent build` was redundant with WORKFLOW.md line 9 |
| Working directory | `Popen(cwd=str(config.homelab_repo_path))` | pi has no `--dir` flag |
| Title / labelling | Structured log line `LOGGER.info("pi_dispatch issue_id=%s …", issue.id)` replaces `--title symphony-<id>` | pi has no `--title`; structured log carries same audit value |
| Auth-failure safety net | **M3** — both startup probe (`verify_pi_support` runs a one-token call against the real model) **and** per-run guardrail (rc=0 + empty stdout + empty stderr → coerce to rc=137 in `AgentResult`) | pi exits 0 silently on missing key, bogus model, etc. Confirmed by local probe |

## Final Swap Shape

```text
Files changed (symphony repo):

  plane_cli.py
    + #!/usr/bin/env python3  (line 1)

  config.py
    - opencode_bin, opencode_agent, opencode_model
    + pi_bin (env: PI_BIN)
    + pi_provider (env: SYMPHONY_PI_PROVIDER, default "zai")
    + pi_model (env: SYMPHONY_PI_MODEL, default "glm-5.1:high")

  agent_runner.py
    - verify_opencode_support
    + verify_pi_support(pi_bin, provider, model)
        Step 1: --help advertises --print + --no-session
        Step 2: one-token auth probe against the configured provider/model;
                fail fast if rc != 0 or stdout is empty

    Argv:
      - opencode run --agent <a> --dir <d> --title symphony-<id>
                    [--model <m>] <prompt>
      + pi --print --no-session --no-context-files
           --provider <p> --model <m> <prompt>

    Popen:
      + cwd=str(config.homelab_repo_path)
      + structured log: LOGGER.info("pi_dispatch issue_id=%s …", issue.id)

    Env allow-list:
      - CLIPROXY_API_KEY
      + ZAI_API_KEY
      + PI_OFFLINE, PI_CODING_AGENT_DIR, PI_CODING_AGENT_SESSION_DIR

    Env injection:
      + env["PYTHONPATH"] = str(Path(__file__).parent)
        (so the plane shim's `from schedule import …` resolves the sibling
         module, not the site-packages library)

    Post-run guardrail (after process.communicate):
      + if exit_code == 0 and not stdout.strip() and not stderr.strip():
            coerce AgentResult to exit_code=137 with explanatory stderr.

  main.py
    + call verify_pi_support(...) at startup, before scheduler loop

  tests/*
    - opencode argv assertions
    + pi argv assertions
    + verify_pi_support tests (help check + probe success/failure)
    + agent_runner silent-exit guardrail test

Live host config (mutations require James approval):

  /home/james/plane/symphony-host.env
    + ZAI_API_KEY=<new key — provisioned by James>
    - CLIPROXY_API_KEY can stay or be removed if confirmed unused elsewhere

  systemd unit env (EnvironmentFile or unit Environment=):
    - OPENCODE_BIN, SYMPHONY_OPENCODE_AGENT, SYMPHONY_OPENCODE_MODEL
    + PI_BIN=/home/james/.npm-global/bin/pi
    + SYMPHONY_PI_PROVIDER=zai
    + SYMPHONY_PI_MODEL=glm-5.1:high
    + PI_OFFLINE=1                   (optional)
    + PI_CODING_AGENT_SESSION_DIR=/run/symphony/pi-sessions
```

## Failure-Mode Walkthrough Summary

| # | Signature | Survives swap? |
|---|---|---|
| 1 | Missing env var | ✅ unchanged |
| 2 | Plane 301 / redirect | ✅ unchanged |
| 3 | Plane 401 | ✅ unchanged |
| 4 | Plane 404 / project UUID | ✅ unchanged |
| 5 | Plane 429 | ✅ unchanged |
| 6 | `git` not found | ✅ unchanged |
| 7 | Worktree dirty / stale lock | ✅ unchanged |
| 8 | systemd 217/USER, 203/EXEC | ✅ unchanged |
| 9 | Rapid restart loop | ✅ unchanged |
| 10 | Plane adapter NotImplementedError | ✅ unchanged |
| 11 | Smoke ticket stuck Running | ✅ unchanged |
| 12 | Missing Plane comments | ✅ unchanged |
| 13 | Invalid label UUID | ✅ unchanged |
| 14 | Executor dispatch failure (`verify_*_support`) | 🔧 swap to `verify_pi_support` |
| 15 | Dirty homelab after agent | ✅ unchanged |
| 16 | plane_cli.py has no shebang (latent) | 🔧 F1 — add shebang |
| 17 | `from schedule import` collision (latent) | 🔧 F2 — inject PYTHONPATH |
| 18 | pi -p silent rc=0 on auth/model error | 🔧 M3 — probe + guardrail |

## Recommended Next Steps

1. Hand this artifact to `/Plan` (or a future planning session) as the
   feasibility-confirmed scope. The plan should:
   - phase the swap as one commit-able unit per file (or one PR per
     repo: symphony only; no homelab changes needed for the swap itself);
   - separate live-host mutations (`symphony-host.env`, systemd env) into
     a follow-up approval gate;
   - include a Plane smoke ticket dry-run as the verification step before
     declaring the swap complete.
2. Provision `ZAI_API_KEY` for Symphony before the live cutover. This is
   the only new secret the swap requires; James must add it to
   `/home/james/plane/symphony-host.env`.
3. After the swap is stable, consider follow-ups:
   - Direction B (adopt `--mode json` for structured terminal events).
   - Label-driven AGENTS.md overlays in `prompt_renderer.py` (Direction
     C3b) if real benefit emerges from selectively pulling in
     `agent-instructions/<domain>/AGENTS.md` content.
   - Cleanup: confirm `CLIPROXY_API_KEY` is no longer needed and remove
     it from `symphony-host.env`.
