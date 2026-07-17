# Session Capture: Issue 464 remote Pi Duo runtime gap

- Date: 2026-07-17
- Purpose: Explain why Podium issue 464 failed twice on the `mac-dotfiles` remote binding.
- Scope: Read-only correlation of the Podium issue/run rows, bounded run logs, scheduler journal, and non-secret remote Pi model metadata.

## Durable Facts

- Issue 464 (`mac-dotfiles`) selected the outer catalog model `pi-duo/Duo`; Runs 2687 and 2692 both exited 1 in about 7.5 seconds and the issue moved to `blocked`. — Evidence: read-only queries against `podium.db`; `runs/2687.log`; `runs/2692.log`; `journalctl -u symphony-host.service` for 2026-07-17 14:16 UTC.
- The immediate failure was inside Duo's configured actor, not Symphony's dispatch gate: the remote Pi process could not resolve the MiniMax provider credential. The remote Duo actor also named `minimax/MiniMax-M3`, while the remote safe model inventory contained only MiniMax 2.x ids, so supplying the credential alone would not make that actor tuple resolvable. — Evidence: `runs/2692.log`; read-only SSH metadata probe that printed provider/model ids and credential presence only.
- `Warning: No models match pattern "zai/glm-5.2"` was secondary startup configuration drift: the remote settings enabled that pattern, but the noninteractive SSH process had no ZAI credential and `pi --list-models` omitted the ZAI entry. Duo's configured verifier was CLIProxy, not ZAI. — Evidence: `runs/2692.log`; read-only SSH `pi --list-models`; safe settings/model-id metadata probe.
- Pi Duo intentionally registers its outer virtual model even when actor lookup is unavailable for picker metadata: `providerConfig()` catches actor lookup failure and still emits `pi-duo/Duo`; request handling later calls fail-loud `lookupModel(config.actor)`. Symphony validates only the outer `models.yml` entry, so nested actor readiness is a host-runtime concern. — Evidence: `/home/james/dotfiles/.pi/agent/extensions/pi-duo/extensions/pi-duo.ts` (`lookupModel`, `streamPiDuo`, `providerConfig`).

## Decisions

- None. The session diagnosed only; it did not change the remote host, issue state, service, model catalog, or repository files outside this wiki capture.

## Evidence

- `runs/2687.log` and `runs/2692.log` — exact empty-stdout/nonzero stderr symptom.
- `podium.db` read-only issue/run queries — issue state, run ids, provider/model, timing, and verdict.
- `journalctl -u symphony-host.service` around 2026-07-17 14:16 UTC — remote dispatch, exit 1, and blocked transition.
- `/home/james/dotfiles/.pi/agent/extensions/pi-duo/extensions/pi-duo.ts` — outer virtual-model registration and request-time nested-model lookup behavior.

## Exclusions

- No credentials, credential values, private environment-file contents, request headers, or full remote model configuration were captured.
- Unrelated dirty working-tree changes and unrelated issues were excluded.

## Open Questions And Follow-Ups

- Choose either a remote Duo repair (configure a resolvable actor provider/model and its credential for noninteractive SSH) or temporarily requeue the issue with a directly available CLIProxy model.
- Add a remote preflight that resolves Duo's nested actor/verifier tuples, because an outer `pi-duo/Duo` catalog smoke cannot prove the nested models are usable.
