# Plan: Replace OpenCode with pi as Symphony's executor

## Task Description

Replace OpenCode entirely as Symphony's coding-agent executor with the locally installed `pi` CLI (`@mariozechner/pi-coding-agent` v0.74.0 at `/home/james/.npm-global/bin/pi`). The swap covers executor dispatch, runtime config, startup verification, scheduler redaction / permission-gate text, the Plane helper PATH shim, and the affected tests. The Plane state-transition contract (`plane_cli.py` PATH shim + `SYMPHONY_RESULT:` stdout marker) and prompt rendering (`WORKFLOW.md` + `homelab_router.prompt_renderer`) stay intact.

Source artifact: `artifacts/brainstorming/brainstorm-symphony-pi-swap-2026-05-11.md`.

## Objective

Symphony dispatches Plane issues to `pi --print --no-session --provider zai --model glm-5.1:high <prompt>` from the configured homelab repo working directory, with the same Plane state-transition guarantees as before, no OpenCode runtime dependency, and explicit guardrails for pi auth/model silent failures.

## Problem Statement

Symphony currently launches `opencode run --agent build --dir <repo> [--model <m>] --title symphony-<id> <prompt>` via `agent_runner.run_agent`. That path adds an unnecessary OpenCode agent layer, hides two latent Plane shim issues, and uses `CLIPROXY_API_KEY`, which does not transfer to direct pi/ZAI usage. The replacement must avoid a dangerous pi behavior confirmed in the brainstorm: pi can exit 0 with empty stdout/stderr on auth or model misconfiguration, which the scheduler could otherwise treat as a successful no-op.

Round 1 Codex audit also found that the initial draft missed `scheduler.py`, `tests/test_scheduler.py`, missing/non-executable `PI_BIN` handling, executable shim regression coverage, and stale OpenCode user-facing strings. This revised plan incorporates those findings.

## Solution Approach

Implement the smallest viable swap:

- Replace OpenCode config fields and env names with pi equivalents.
- Replace OpenCode argv with `pi --print --no-session --provider <p> --model <m> <prompt>`.
- Drop `--no-context-files` per James' decision after Codex review, so pi can load `/home/james/homelab/AGENTS.md` / `CLAUDE.md` from the homelab repo the same way the current `opencode --dir` path benefits from repo context. This revises the brainstorm's earlier lock because `WORKFLOW.md` line 27 explicitly depends on AGENTS.md safety rules.
- Move live pi support checking to startup only. `run_agent` must not do a live verifier call per ticket.
- Add a run-level silent-exit guardrail: `(rc=0, empty stdout, empty stderr)` becomes `rc=137` with explanatory stderr.
- Add a shebang to `plane_cli.py` and inject `PYTHONPATH=<symphony dir>` into the child env so the copied `plane` shim resolves sibling `schedule.py` instead of site-packages `schedule`.
- Update `scheduler.py` redaction from `CLIPROXY_API_KEY` to `ZAI_API_KEY` and remove/reword OpenCode-specific permission-gate text.
- Update every test affected by the config dataclass shape, especially `tests/test_scheduler.py`.

Live-host mutations (`/home/james/plane/symphony-host.env`, systemd environment, service restart, Plane smoke ticket) are approval-gated operational steps and are documented here but not performed by the build.

## Relevant Files

Use these files to complete the task:

- `agent_runner.py` — pi dispatch, `verify_pi_support`, env allow-list, `PYTHONPATH`, `cwd`, silent-exit guardrail, stale OpenCode docstrings.
- `config.py` — remove OpenCode fields; add `pi_bin`, `pi_provider`, `pi_model`; require `PI_BIN`.
- `scheduler.py` — replace `CLIPROXY_API_KEY` redaction with `ZAI_API_KEY`; update permission-gate docstring/comment/message to be executor-neutral or pi-compatible.
- `plane_cli.py` — add executable shebang.
- `main.py` — call `verify_pi_support` once at startup before `run_loop`.
- `scripts/sync_plane_ids.py` — retarget stale helper comments from OpenCode to pi/Symphony so final stale-reference validation passes.
- `tests/test_agent_runner.py` — pi argv/env/cwd/log/probe/guardrail tests, including missing/non-executable `PI_BIN` via `OSError` wrapping.
- `tests/test_config.py` — pi env defaults/overrides/required vars/repr tests.
- `tests/test_main.py` — startup verifier success/failure tests.
- `tests/test_plane_cli.py` — shebang plus executable PATH-shim subprocess regression.
- `tests/test_scheduler.py` — update `SymphonyConfig(...)` helpers and env dicts from OpenCode to pi; add ZAI redaction and permission message coverage.

No new files are required.

## Implementation Phases

### Phase 1: Foundation

Add the shim shebang and reshape `SymphonyConfig`. Update config, plane CLI, and scheduler test fixtures early so the suite can compile with the new dataclass shape.

### Phase 2: Executor Swap

Replace the OpenCode runner path with pi. Keep startup verification in `main.async_main` only; remove the current per-run verifier call from `run_agent`. Add the pi silent-exit guardrail after the successful `communicate()` branch. Keep timeout handling unchanged.

### Phase 3: Scheduler and Redaction Polish

Update scheduler secret redaction from `CLIPROXY_API_KEY` to `ZAI_API_KEY`. Reword permission-gate comments and Plane comment text so they no longer say OpenCode. Keep the gate itself if the existing regex still matches pi's denial output; otherwise make the message executor-neutral and document that exact pi permission strings should be refined after the first real denial is observed.

### Phase 4: Validation and Operational Handoff

Run the Python test suite, compile modules, grep for stale OpenCode / CLIPROXY references, and document the live-host approval gate for `ZAI_API_KEY`, systemd env changes, restart, and smoke ticket.

## Step by Step Tasks

IMPORTANT: Execute every step in order when running manually. Build will parallelize independent groups automatically.

### 1. Harden the Plane shim
- [ ] [1.1] Prepend `#!/usr/bin/env python3` as line 1 of `plane_cli.py`.
- [ ] [1.2] Add `tests/test_plane_cli.py::test_file_has_python_shebang` asserting the file starts with `#!/usr/bin/env python3\n`.
- [ ] [1.3] Add an executable PATH-shim regression: copy `plane_cli.py` to a temp file named `plane`, chmod `0o700`, run it as a subprocess with filtered env plus `PYTHONPATH=<symphony dir>`, and assert it reaches the expected CLI/env error rather than `Exec format error` or `ImportError`.

### 2. Reshape SymphonyConfig
- [ ] [2.1] In `config.py`, remove `opencode_bin`, `opencode_agent`, and `opencode_model` from `SymphonyConfig` and `__repr__`.
- [ ] [2.2] Add `pi_bin: str`, `pi_provider: str = "zai"`, and `pi_model: str = "glm-5.1:high"` to `SymphonyConfig` and `__repr__`.
- [ ] [2.3] Replace required env `OPENCODE_BIN` with `PI_BIN`.
- [ ] [2.4] Read `PI_BIN`, `SYMPHONY_PI_PROVIDER`, and `SYMPHONY_PI_MODEL` in `from_env`, preserving existing Plane, Telegram, timeout, poll, and lock handling.
- [ ] [2.5] Update `tests/test_config.py` for missing required vars, defaults, provider override, model override, and repr.
- [ ] [2.6] Update every `SymphonyConfig(...)` helper in `tests/test_scheduler.py` to pass `pi_bin`, `pi_provider`, and `pi_model` instead of `opencode_bin`.
- [ ] [2.7] Update every `OPENCODE_BIN` env fixture in `tests/test_scheduler.py` to `PI_BIN`.

### 3. Add startup-only pi support verification [sequential]
- [ ] [3.1] In `agent_runner.py`, replace `verify_opencode_support` with `verify_pi_support(pi_bin: str, provider: str, model: str, cwd: Path | str, run_func=...)`.
- [ ] [3.2] In `verify_pi_support`, help-check `[pi_bin, "--help"]` and require `--print` plus `--no-session` in combined stdout/stderr.
- [ ] [3.3] In `verify_pi_support`, probe `[pi_bin, "--print", "--no-session", "--provider", provider, "--model", model, "ping"]` with `cwd=str(cwd)` and a short timeout such as 30 seconds. Do not include `--no-context-files`; the probe should load the same homelab context as real dispatch.
- [ ] [3.4] Raise `AgentRunnerError` if help/probe rc is nonzero, if probe stdout is empty after `.strip()`, or if `run_func` raises `OSError` (`FileNotFoundError`, `PermissionError`, non-executable binary). Retarget all verifier exception messages from OpenCode / `run --agent` wording to pi / `--print --no-session` wording.
- [ ] [3.5] Remove verifier invocation from `run_agent`; only `main.async_main` should call `verify_pi_support`.
- [ ] [3.6] Update `tests/test_agent_runner.py` to cover help success, missing `--print`, missing `--no-session`, probe rc failure, empty/whitespace probe stdout, and `OSError` wrapping.

### 4. Swap run_agent dispatch [sequential]
- [ ] [4.1] Replace the OpenCode command with `[config.pi_bin, "--print", "--no-session", "--provider", config.pi_provider, "--model", config.pi_model, rendered_prompt]`.
- [ ] [4.2] Remove `--agent`, `--dir`, `--title`, and per-run `--model` conditionals.
- [ ] [4.3] Pass `cwd=str(config.homelab_repo_path)` to `popen_factory(...)`.
- [ ] [4.4] Replace env allow-list item `CLIPROXY_API_KEY` with `ZAI_API_KEY`, `PI_OFFLINE`, `PI_CODING_AGENT_DIR`, and `PI_CODING_AGENT_SESSION_DIR`; keep existing PATH/HOME/USER/LANG/TERM/XDG/TMPDIR/PYTHONUNBUFFERED/Telegram values.
- [ ] [4.5] Set `env["PYTHONPATH"] = str(Path(__file__).parent)` after composing env.
- [ ] [4.6] Replace the OpenCode title log with `LOGGER.info("pi_dispatch issue_id=%s provider=%s model=%s", issue.id, config.pi_provider, config.pi_model)`; keep `agent_exited` unchanged.
- [ ] [4.7] Update module/class/function docstrings in `agent_runner.py` so no user-facing OpenCode references remain.
- [ ] [4.8] Add the silent-exit guardrail in the successful `communicate()` path: if `exit_code == 0` and both streams are blank after `.strip()`, log a warning and return `AgentResult(137, duration_ms, False, stdout, explanatory_stderr)`.
- [ ] [4.9] Ensure timeout behavior is unchanged and guardrail does not run on the timeout branch.
- [ ] [4.10] Update `tests/test_agent_runner.py` for exact pi argv, cwd, env allow-list, `PYTHONPATH`, configured provider/model, dispatch log, silent-zero coercion, non-silent-zero preservation, and timeout preservation.

### 5. Wire startup probe into main
- [ ] [5.1] Import `verify_pi_support` in `main.py`.
- [ ] [5.2] In `main.async_main`, call `verify_pi_support(config.pi_bin, config.pi_provider, config.pi_model, config.homelab_repo_path)` immediately after `SymphonyConfig.from_env()` and before `HttpxPlaneTransport(...)` construction. This avoids opening a Plane transport if the verifier fails.
- [ ] [5.3] Update `tests/test_main.py` to assert verifier invocation before transport construction and `run_loop`, and that `AgentRunnerError` aborts startup without constructing `HttpxPlaneTransport`.

### 6. Update scheduler redaction and executor-neutral text
- [ ] [6.1] In `scheduler.py`, replace `_SECRET_ENV_KEYS` entry `CLIPROXY_API_KEY` with `ZAI_API_KEY`.
- [ ] [6.2] Add/update scheduler tests proving `ZAI_API_KEY` is redacted from stdout/stderr comments and `CLIPROXY_API_KEY` is no longer required by the scheduler redaction list.
- [ ] [6.3] Reword `_hit_permission_gate` docstring from OpenCode-specific to executor-neutral.
- [ ] [6.4] Reword the Plane comment text `Agent could not complete because OpenCode denied required tool access.` to an executor-neutral phrase such as `Agent could not complete because required tool access was denied.`
- [ ] [6.5] Add/update a scheduler test for the permission-gate comment text so it no longer names OpenCode.

### 7. Update scheduler test fixtures
- [ ] [7.1] Update `tests/test_scheduler.py` `_config()` helper to use pi fields.
- [ ] [7.2] Replace all env dict `OPENCODE_BIN` entries with `PI_BIN`.
- [ ] [7.3] Search `tests/test_scheduler.py` for `opencode`, `OPENCODE`, and `OpenCode`; update or remove all stale references unless they are in historical fixture text explicitly asserted out of scope.

### 8. Remove stale OpenCode references outside runtime code
- [ ] [8.1] Update `scripts/sync_plane_ids.py` comments/docstrings that mention OpenCode to refer to the Symphony-launched agent or pi PATH shim.
- [ ] [8.2] Search `agent_runner.py`, `scheduler.py`, `main.py`, `config.py`, `tests/`, and `scripts/sync_plane_ids.py` for `opencode`, `OPENCODE`, `OpenCode`, and `CLIPROXY`; retarget every match or explicitly exclude non-runtime historical artifacts from validation.

### 9. Validate
- [ ] [9.1] Run `cd /home/james/plane/symphony && uv run pytest -q` and confirm zero failures.
- [ ] [9.2] Run `cd /home/james/plane/symphony && uv run python -m py_compile *.py` and confirm module compilation succeeds.
- [ ] [9.3] Run `cd /home/james/plane/symphony && rg -n "opencode|OPENCODE|OpenCode|CLIPROXY" --glob '!plans/**' --glob '!artifacts/**'` and confirm zero stale runtime/test/script references.
- [ ] [9.4] Run `cd /home/james/plane/symphony && head -1 plane_cli.py` and confirm `#!/usr/bin/env python3`.
- [ ] [9.5] Document live-host changes in the PR/commit body, but do not mutate `/home/james/plane/symphony-host.env` or systemd without James approval. Record that verifier failure halts startup intentionally because a missing/bad pi provider cannot safely execute tickets.

## Testing Strategy

- **Unit tests:** update and expand `tests/test_agent_runner.py`, `tests/test_config.py`, `tests/test_main.py`, `tests/test_plane_cli.py`, and `tests/test_scheduler.py`.
- **Executable shim regression:** verify copied `plane_cli.py` works as a PATH executable under filtered env plus `PYTHONPATH`.
- **Scheduler safety:** verify ZAI key redaction and executor-neutral permission text.
- **Manual smoke after approved live cutover:** one Plane smoke ticket, journal inspection for `pi_dispatch`, and expected terminal Plane state.

## Tests

### T.1. Plane shim hardening
- [ ] [T.1.1] `tests/test_plane_cli.py::test_file_has_python_shebang` passes.
- [ ] [T.1.2] `tests/test_plane_cli.py::test_plane_cli_copy_runs_as_path_executable_with_pythonpath` passes.

### T.2. SymphonyConfig pi fields
- [ ] [T.2.1] Missing required vars mention `PI_BIN` and not `OPENCODE_BIN`.
- [ ] [T.2.2] Defaults load `pi_provider == "zai"` and `pi_model == "glm-5.1:high"`.
- [ ] [T.2.3] `SYMPHONY_PI_PROVIDER` override flows through.
- [ ] [T.2.4] `SYMPHONY_PI_MODEL` override flows through.
- [ ] [T.2.5] `__repr__` includes pi fields and redacts Plane API key.

### T.3. verify_pi_support
- [ ] [T.3.1] Help and probe success passes, with the probe receiving `cwd=config.homelab_repo_path`.
- [ ] [T.3.2] Missing `--print` fails.
- [ ] [T.3.3] Missing `--no-session` fails.
- [ ] [T.3.4] Probe nonzero rc fails.
- [ ] [T.3.5] Probe empty stdout fails.
- [ ] [T.3.6] Probe whitespace stdout fails.
- [ ] [T.3.7] `OSError` from help/probe raises `AgentRunnerError`.

### T.4. run_agent argv / env / cwd
- [ ] [T.4.1] Exact pi argv excludes `--no-context-files`, `--agent`, `--dir`, and `--title`.
- [ ] [T.4.2] `cwd == str(config.homelab_repo_path)`.
- [ ] [T.4.3] Env includes `ZAI_API_KEY` and excludes `CLIPROXY_API_KEY`.
- [ ] [T.4.4] Env injects `PYTHONPATH` to the Symphony source directory.
- [ ] [T.4.5] Dispatch log carries issue id, provider, and model.
- [ ] [T.4.6] Configured provider/model appear in argv.
- [ ] [T.4.7] `run_agent` does not call `verify_pi_support` per run.

### T.5. Silent-exit guardrail
- [ ] [T.5.1] Silent rc=0 becomes rc=137 with explanatory stderr.
- [ ] [T.5.2] Non-silent rc=0 remains rc=0.
- [ ] [T.5.3] Timeout path remains rc=-1 and does not trigger guardrail.

### T.6. main startup probe
- [ ] [T.6.1] `main.async_main` invokes `verify_pi_support` before transport construction and `run_loop`.
- [ ] [T.6.2] `AgentRunnerError` from verifier aborts startup without constructing `HttpxPlaneTransport`.

### T.7. scheduler updates
- [ ] [T.7.1] `tests/test_scheduler.py` config/env fixtures use pi fields.
- [ ] [T.7.2] `ZAI_API_KEY` is redacted from scheduler reports/comments.
- [ ] [T.7.3] Permission-gate comment text is executor-neutral.

### T.8. stale reference cleanup
- [ ] [T.8.1] `scripts/sync_plane_ids.py` no longer contains `OpenCode` / `opencode` wording.
- [ ] [T.8.2] Final stale-reference grep returns zero matches outside `plans/**` and `artifacts/**`.

## Progress

**Phase Status:**
- Build: `complete`
- Test: `complete`

**Task Counts:**
- Implementation: `38/38` tasks complete
- Tests: `29/29` tests passing

**Last Updated:** `2026-05-11T19:05:00Z`

## Acceptance Criteria

- `plane_cli.py` begins with `#!/usr/bin/env python3` and copied executable shim test passes.
- Runtime config has no OpenCode fields; `PI_BIN` is required; pi provider/model defaults and overrides work.
- `agent_runner.py` dispatches pi with `--print --no-session --provider <p> --model <m> <prompt>`, no `--no-context-files`, `cwd=config.homelab_repo_path`, and `PYTHONPATH=<symphony dir>`.
- `run_agent` does not perform per-ticket live support probes.
- `verify_pi_support` runs at startup and wraps rc failures, empty probe stdout, missing help flags, and `OSError` as `AgentRunnerError`.
- Silent pi zero-output exits become rc=137 and cannot be treated as successful no-ops.
- `scheduler.py` redacts `ZAI_API_KEY`, not `CLIPROXY_API_KEY`, and no longer posts OpenCode-specific permission text.
- `tests/test_scheduler.py` is updated for the new config/env shape.
- `verify_pi_support` probes with `cwd=config.homelab_repo_path`, and `main.async_main` calls it before constructing `HttpxPlaneTransport`.
- `uv run pytest -q` and `uv run python -m py_compile *.py` pass from `/home/james/plane/symphony`.
- `rg -n "opencode|OPENCODE|OpenCode|CLIPROXY" --glob '!plans/**' --glob '!artifacts/**'` returns zero stale runtime/test/script references.
- No live host config or systemd mutation is performed without James approval.

## Testing Promise

All unit tests under `tests/` pass with zero failures, and the suite proves the pi argv shape, startup probe, missing-binary failure handling, env allow-list, cwd, PYTHONPATH injection, executable Plane shim behavior, scheduler ZAI redaction, executor-neutral permission text, and silent-exit guardrail.

## Validation Commands

Execute these commands to validate the task is complete:

- `cd /home/james/plane/symphony && uv run pytest -q` — full test suite must pass.
- `cd /home/james/plane/symphony && uv run python -m py_compile *.py` — all modules compile.
- `cd /home/james/plane/symphony && rg -n "opencode|OPENCODE|OpenCode|CLIPROXY" --glob '!plans/**' --glob '!artifacts/**'` — no stale runtime/test/script references.
- `cd /home/james/plane/symphony && head -1 plane_cli.py` — prints `#!/usr/bin/env python3`.
- **Post-deploy after James approval:** provision `ZAI_API_KEY`, update systemd env, restart Symphony, create one Plane smoke ticket, and verify `journalctl -u symphony -n 200` contains `pi_dispatch issue_id=...` and the ticket reaches expected terminal state via marker/heuristic.

## Notes

**Live-host mutations (approval-gated, not part of this build):**

1. Add `ZAI_API_KEY=<new key>` to `/home/james/plane/symphony-host.env`.
2. Replace systemd env `OPENCODE_BIN`, `SYMPHONY_OPENCODE_AGENT`, `SYMPHONY_OPENCODE_MODEL` with `PI_BIN=/home/james/.npm-global/bin/pi`, `SYMPHONY_PI_PROVIDER=zai`, and `SYMPHONY_PI_MODEL=glm-5.1:high`.
3. Optional env: `PI_OFFLINE=1`, `PI_CODING_AGENT_DIR=<approved pi config dir>`, `PI_CODING_AGENT_SESSION_DIR=/run/symphony/pi-sessions`.
4. Reload/restart only after James approves the live mutation.

**Decision revision from brainstorm:**

The brainstorm locked `--no-context-files`, but Codex correctly identified that `WORKFLOW.md` depends on homelab `AGENTS.md` safety rules. James selected `Drop --no-context-files`; this revised plan follows that decision and keeps pi context discovery enabled from `cwd=config.homelab_repo_path`.

**Out of scope:**

- Adopting `pi --mode json` for structured terminal events.
- Label-driven AGENTS.md overlays in `prompt_renderer.py`.
- Removing `CLIPROXY_API_KEY` from live env until confirmed unused elsewhere.
