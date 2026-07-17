# Session Capture: Issue 464 shell-environment correction

- Date: 2026-07-17
- Purpose: Reconcile why `pi-duo/Duo` works when invoked directly in a Mac terminal but fails when Symphony dispatches the same outer model remotely.
- Scope: Presence-only environment comparison, filtered model-list comparison, and inspection of Symphony's remote SSH command construction. No credential values or shell configuration contents were read.

## Durable Facts

- Both launch contexts use the same binary and version: `/opt/homebrew/bin/pi` version `0.80.6`. — Evidence: read-only SSH probes using the default noninteractive shell and `zsh -lic`.
- The Mac login-interactive shell reports the MiniMax credential variable present and lists `minimax/MiniMax-M3`; the default noninteractive SSH shell reports the variable missing and omits MiniMax models. — Evidence: presence-only `test -n` probes and filtered `pi --list-models` output under both shell modes.
- Symphony invokes remote Pi through SSH with one command argument (`cd ... && export <Symphony callback keys> ... && pi --mode rpc`). `run_remote_agent()` explicitly documents that the SSH command is noninteractive and does not source `.zshrc`/`.bashrc`; `_remote_exports()` forwards tracker callback variables plus `SYMPHONY_ISSUE_ID`, `TERM`, and `NO_COLOR`, not arbitrary provider credentials. — Evidence: `agent_runner.py` (`_remote_exports`, `_build_remote_command`, `run_remote_agent`); `ssh_support.py` (`ssh_base_args`).
- Therefore Issue 464's direct-terminal success and Symphony failure are consistent: the interactive terminal loads the credential-bearing shell initialization, while Symphony's noninteractive SSH launch does not. The earlier statement that the host registry itself lacked `MiniMax-M3` was incorrect; model visibility was conditional on credential availability in that shell context. — Evidence: paired shell probes; `runs/2687.log`; `runs/2692.log`.
- The `zai/glm-5.2` warning has the same environment-shape explanation: it is enabled in settings but its credential is absent in the noninteractive SSH environment. It remains secondary to Duo's MiniMax actor failure. — Evidence: paired shell probes and filtered model lists.

## Decisions

- None. Diagnosis and documentation correction only.

## Evidence

- `agent_runner.py:478-540,581-731` — bounded remote environment and noninteractive SSH launch.
- `ssh_support.py:12-31` — SSH argument construction.
- `runs/2687.log`; `runs/2692.log` — noninteractive runtime failure.
- Presence-only and filtered-model SSH probes under default shell vs `zsh -lic` — environment parity result.

## Exclusions

- No credential values, shell profile contents, model configuration values, environment-file contents, or private request data were captured.
- No paid model prompt was run; list-model and presence probes were sufficient.

## Open Questions And Follow-Ups

- Choose a secure way for noninteractive Symphony SSH dispatch to receive the provider credentials: host-level noninteractive shell initialization or an explicit restricted credential-loader seam in the remote launch path.
- Add an environment-parity smoke for remote composite providers so a direct interactive-terminal smoke is not mistaken for Symphony-path readiness.
