# Session Capture: Issue 464 Pi login fix verified

- Date: 2026-07-17
- Purpose: Verify the operator's fix for remote `pi-duo/Duo` authentication after Issue 464 failed through Symphony.
- Scope: Noninteractive SSH model visibility, the operator's exact print-mode command, and a direct RPC-mode transport probe. No credential values or auth-store contents were read.

## Durable Facts

- The operator opened Pi on the Mac, ran `/login`, and entered the MiniMax key through Pi's authentication flow. — Evidence: operator report in the interactive session.
- After `/login`, the same default noninteractive SSH context that previously omitted MiniMax now lists `minimax/MiniMax-M3` and `pi-duo/Duo`. — Evidence: filtered `pi --list-models` over batch-mode SSH.
- The operator's exact command shape succeeds noninteractively from the Symphony host: `pi --provider pi-duo --model Duo --print --no-session "ping"` returned `pong` with exit code 0 from `/Users/james/dotfiles`. — Evidence: bounded batch-mode SSH probe.
- Symphony's actual transport shape also succeeds: `pi --mode rpc --provider pi-duo --model Duo --session-id <fresh-uuid>` accepted a prompt over stdin and exited 0. The expected warning that the fresh session id did not yet exist was non-fatal. — Evidence: bounded batch-mode SSH RPC probe.
- Therefore a shell environment variable is not required when Pi's own login/auth store contains the provider credential. The Issue 464 failure was missing provider authentication in the noninteractive Pi context; `/login` repaired that context without changing Duo, Symphony, or shell initialization. — Evidence: before/after noninteractive probes and operator report.

## Decisions

- Prefer Pi's supported `/login` flow for provider authentication on the remote host over adding a separate shell credential loader for this incident.

## Evidence

- `runs/2687.log`; `runs/2692.log` — before-fix authentication failure.
- Batch-mode SSH filtered model list — post-fix `MiniMax-M3` visibility.
- Batch-mode SSH print smoke — `pong`, exit 0.
- Batch-mode SSH RPC smoke — exit 0.

## Exclusions

- No API key, auth-store path/content, shell profile, environment file, request headers, or private model response was captured.
- Issue 464 was not requeued; services, DB rows, remote configuration files, and repository code were not changed.

## Open Questions And Follow-Ups

- Requeue Issue 464 only if the operator wants a full scheduler/Issue lifecycle confirmation; the direct noninteractive print and RPC provider paths are already green.
