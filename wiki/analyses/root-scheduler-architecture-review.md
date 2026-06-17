---
title: "Root scheduler module architecture review (+ Pi meta-review)"
type: analysis
status: promoted
created: 2026-06-17
updated: 2026-06-17
sources:
  - .rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md
  - wiki/raw/sessions/2026-06-17-root-scheduler-architecture-review.md
  - scheduler.py
  - main.py
  - agent_runner.py
  - plane_adapter.py
  - tracker_podium.py
  - tracker_adapter.py
  - tracker_types.py
  - web/api/main.py
  - web/api/tests/test_context_compaction.py
  - bindings.yml
  - .kanban/issues/065-extract-probe-binding.md
  - .kanban/issues/066-public-build-binding-runtime-web-api-reflection.md
  - .kanban/issues/067-plane-secret-deshipping-podium.md
  - .kanban/issues/068-dedup-resume-fallback.md
  - .kanban/issues/069-scope-cooldown-dispatchstate.md
  - .kanban/issues/070-decompose-run-tick.md
  - .kanban/issues/073-config-tracker-neutral-dual-read.md
  - tests/test_agent_runner.py
  - tests/test_remote_agent.py
  - tests/test_dispatch_compaction.py
  - tests/test_scheduler.py
  - tests/test_config.py
  - .kanban/issues/074-tracker-enum-neutral-names.md
  - tests/test_tracker_contract.py
confidence: high
tags: [architecture-review, scheduler, tracker-adapter, agent-runner, refactor-plan, plane-retirement]
---

# Root scheduler module architecture review (+ Pi meta-review)

Layer-by-layer architecture audit of Symphony's **root scheduler module** — the 24 top-level `*.py` files (~11.6k LOC) that `symphony-host.service` runs via `python3 -m main` — followed by an independent Pi (`openai-codex/gpt-5.5`) meta-review of the resulting artifact. At creation time, no source was modified; the product was a phased refactor plan. Authoritative artifact: `.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md` (git-ignored) [source: .rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md].

## Shape

8 top-down layers (entry → utilities), **41 findings** (29 accepted, 5 rejected, 7 deferred), 2 methodology principles, 8 cross-cutting themes, a 7-phase plan. The import graph is a clean DAG; entry `main.py`, hub `scheduler.py` (3039 LOC) [source: scheduler.py].

## Highest-leverage structural findings

- **T4 — scheduler decomposition.** `run_tick` is ~882 LOC (`scheduler.py:1168-2050`) with a duplicated resume-fallback block (`:1521-1605` ≈ `:1615-1697`); `scheduler.py` is 3039 LOC. Plan: dedup → scope cooldown → decompose `run_tick` (terminal handlers first) → split into a `scheduler/` package with an `__init__` re-export. Highest risk (live dispatch path) [source: scheduler.py:1168-2050].
- **T7 — tracker vocabulary home.** The tracker-agnostic engine types live *inside* the Plane adapter: `CandidateIssue` (`plane_adapter.py:53`, field-equivalently duplicated in `tracker_podium.py:42`) and the `TrackerAdapter` Protocol (`plane_adapter.py:136`, defined divergently again in `tracker_adapter.py:15`). Plan: a neutral `tracker_types.py` with layering `tracker_contract → tracker_types → tracker_adapter → {plane_adapter, tracker_podium}` [source: plane_adapter.py:53, tracker_podium.py:42, tracker_adapter.py:15].
- **T5 — per-binding isolation.** `_PLANE_COOLDOWN_UNTIL` (`scheduler.py:67`) is a module global that leaks rate-limit cooldown across all bindings, undermining the per-binding `_DispatchState`; scope it to `_DispatchState` [source: scheduler.py:63-182].
- **T3 — boundary leaks.** `web/api/main.py:_compact_issue_context` reaches engine internals through four `vars()` reflections (`:930/957/987/1000`) plus `import_module`; the binding-runtime factory is reached via `vars(engine_main)["_build_binding_runtime"]`. Plan: normal imports + a public `build_binding_runtime` [source: web/api/main.py:925-1000].

## Triage philosophy (wise-decision keeps)

Notable **rejected/kept** decisions: keep the engine→`web.api.db` coupling (Podium *is* the web DB); keep the hand-written `SymphonyConfig.__repr__` on a deny-by-omission security argument; keep `(value, error|None)` tuple returns; keep `schedule.py` as one cohesive file; keep `plane_cli`'s standalone Telegram sender. Two methodology principles emerged: **M1** keep tested zero-consumer primitives that pair with an existing flow; **M2** verify an unusual coupling's reason before "fixing" it (several `vars()`/lazy-import "smells" were deliberate) [source: .rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md].

## Plane is dormant, not gone

All 4 live bindings are `tracker: podium` (homelab, symphony, dotfiles, n8n); **zero** `tracker: plane` bindings, so the Plane dispatch path is **currently dormant** but kept as a rollback hedge [source: bindings.yml]. Consequence surfaced by the Pi meta-review: `agent_runner` shipped the Plane-only `plane` helper **and `SYMPHONY_PLANE_API_KEY`** to every agent subprocess for a tracker no live agent calls — a present secret-exposure surface. Issue #067 fixed the near-term L6-02 security cleanup: Podium local/RPC dispatch now omits `SYMPHONY_PLANE_*`, `PLANE_DASHBOARD_URL`, and the helper; remote Podium dispatch likewise omits callback env, helper shipping, and PATH prepending. Plane-tracker bindings still receive the callback env and helper for rollback/back-compat. Full `plane_cli`/Plane-path deletion stays deferred (theme T8), gated on a confirmed Plane sunset [source: agent_runner.py, tests/test_agent_runner.py, tests/test_remote_agent.py, .kanban/issues/067-plane-secret-deshipping-podium.md, bindings.yml].

## Pi meta-review corrections (2026-06-17)

An independent Pi review (read-only verified) produced 5 findings, all verified against source and applied: (1) **L0-01 was a misdiagnosis** — `scheduler._render_candidate_prompt` (`:593-607`) is a signature-adapter shim, not a duplicate of `main`'s `CandidateIssue→IssueData` mapper; reframed from "consolidate" to "rename". (2) **L0-06 added** — the `web/api` reflection cluster was under-scoped (4 `vars()` sites, not 1). (3) **L6-02 re-prioritized** — Plane-secret de-shipping moved into accepted Phase 5. (4) `CandidateIssue` "byte-identical"→"field-equivalent". (5) Phase 3 explicitly repoints `web/api/main.py:927` [source: .rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md, web/api/main.py:925-1000].

## Status & next action

Audit complete; implementation has started. Issue #45 landed the first small polish batch: L0-01 renamed the scheduler renderer shim to `_invoke_renderer` while leaving `main._render_candidate_prompt` intact; L5-03 routed config and `RoutingAgentAdapter` valid-agent checks through `model_catalog.KNOWN_AGENTS`; L4-01 extracted `schedule._decode_entity_at` while preserving branch-specific handling. Verification passed with the full Python suite (`uv run pytest`: 878 passed, 2 skipped) [source: scheduler.py, main.py, model_catalog.py, config.py, agent_runner.py, schedule.py]. Issue #64 then landed T7's tracker vocabulary home: `tracker_types.py` now owns `CandidateIssue`, `CommentPayload`, `IssuePayload`, label/state helpers, ISO parsing, candidate conversion, and Plane-style cursor/page helpers; `tracker_adapter.py` is the sole `TrackerAdapter` Protocol home; concrete Plane/Podium adapters import those shared definitions. Actionable review preserved two Plane-path behaviours after the move: default `IssuePayload` state remains Todo and malformed Plane issue rows still raise `PlanePollingSchemaError`. Verification passed with the full Python suite (`uv run pytest`: 883 passed, 2 skipped) [source: tracker_types.py, tracker_adapter.py, plane_adapter.py, tracker_podium.py, scheduler.py, blocked_reconciler.py, web/api/main.py]. Issue #65 then landed L0-03: `_probe_binding(config, binding)` now owns startup probe side effects (local pi probe, Podium model-catalog probe resolution, remote reachability logging), `run_bindings_loop` invokes it before `_build_binding_runtime`, and `_build_binding_runtime` is pure runtime wiring for tracker/transport/agent adapters. Verification passed with the full Python suite (`uv run pytest -q`: 884 passed, 2 skipped) and fresh Ralph review passed [source: main.py, tests/test_main.py, .kanban/issues/065-extract-probe-binding.md]. Issue #66 then landed L0-02/L0-06: the runtime factory is public as `main.build_binding_runtime(config, binding)`, `web/api/main.py` imports that factory plus `SymphonyConfig`, `maybe_compact`, and `estimate_tokens` normally, and `_compact_issue_context` no longer uses `vars(engine_main)` or `vars(compaction)` reflection. Actionable review then fixed the legacy `uvicorn main:app` from `web/api` invocation, where the API module is already `sys.modules["main"]`, by loading repo-root `main.py` under an alias only for that legacy path; the regression is covered in `web/api/tests/test_context_compaction.py`. Verification passed with the full Python suite (`uv run pytest`: 885 passed, 2 skipped) [source: main.py, web/api/main.py, tests/test_main.py, tests/test_trading_podium_dispatch.py, web/api/tests/test_context_compaction.py, .kanban/issues/066-public-build-binding-runtime-web-api-reflection.md]. Issue #067 then landed L6-02(a): `_agent_env` and `_remote_exports` gate Plane callback env on tracker kind, `run_agent`/`run_pi_rpc_agent` ship the `plane` helper only for Plane bindings, and `run_remote_agent` ships/prepends the helper only for remote Plane bindings. Verification passed with the full Python suite (`uv run pytest`: 887 passed, 2 skipped), touched-file LSP diagnostics clean, and `git diff --check` clean [source: agent_runner.py, tests/test_agent_runner.py, tests/test_remote_agent.py, .kanban/issues/067-plane-secret-deshipping-podium.md]. Issue #068 then landed the first T4 scheduler-decomposition step: `_dispatch_with_resume_fallback` centralizes the resumed-dispatch fallback sequence, and both the dispatch-exception and nonzero-exit paths call it; regression coverage now exercises the nonzero fallback path. Verification passed with `uv run pytest` (888 passed, 2 skipped), touched-file LSP diagnostics clean, and a live `symphony-host.service` restart on code SHA `ee967e3` with reconcile and dispatch-loop evidence [source: scheduler.py, tests/test_dispatch_compaction.py, .kanban/issues/068-dedup-resume-fallback.md]. Issue #069 then landed T5 per-binding cooldown isolation: `_PLANE_COOLDOWN_UNTIL` and legacy test-only scheduler globals were removed, cooldown state is stored only on `_DispatchState`, and tests assert one state receiving a Plane 429 does not cool down another state. Verification passed with `uv run pytest` (887 passed, 2 skipped), touched-file LSP diagnostics clean, fresh Ralph review passed, and live `symphony-host.service` restart on code SHA `877438f` confirmed `symphony_started`, `reconcile_startup_*`, `run_reconcile_*`, and `dispatch_completed` [source: scheduler.py, tests/test_scheduler.py, .kanban/issues/069-scope-cooldown-dispatchstate.md]. Issue #070 then landed the main T4 `run_tick` decomposition increment: `run_tick` now delegates to named selection, gate, prepare, dispatch, and terminal-classification helpers; `_classify_terminal` centralizes terminal run-record finalization, blocked/review transitions, Question Park, archived-terminal, and clean-review handling. Verification passed with `uv run pytest -q` (887 passed, 2 skipped), `uv run ruff check scheduler.py`, `uv run python -m py_compile scheduler.py`, clean touched-file LSP diagnostics, fresh Ralph review, and live `symphony-host.service` restart on code SHA `48fc0bb` with startup reconcile, run reconcile, and dispatch-loop evidence [source: scheduler.py, .kanban/issues/070-decompose-run-tick.md]. Issue #073 then landed the code side of the L5-02 vocabulary migration: `config.py` dual-reads tracker-neutral `SYMPHONY_TRACKER_*` env names and legacy `PLANE_*` names, documents neutral-over-legacy precedence, keeps existing Plane-named fields for back-compat, and adds tracker-neutral accessor properties plus legacy-only/neutral-only/precedence tests. No systemd unit or `/home/james/symphony-host.env` edit is part of this slice [source: config.py, tests/test_config.py, .kanban/issues/073-config-tracker-neutral-dual-read.md]. Issue #074 then landed L3-04/L5-02 vocabulary cleanup inside `tracker_contract.py`: `TrackerState`, `TrackerLabel`, and `TrackerUserMapping` are canonical, `PlaneState`/`PlaneLabel`/`PlaneUserMapping`/`PlaneContract` remain compatibility aliases, and `tracker_adapter.py`, `tracker_podium.py`, and `config.py` annotations now use canonical names while legacy importers keep working. Verification passed with `uv run pytest` (891 passed, 2 skipped), focused ruff/tests, clean touched-file LSP diagnostics, and fresh Ralph review [source: tracker_contract.py, tracker_adapter.py, tracker_podium.py, config.py, tests/test_tracker_contract.py, .kanban/issues/074-tracker-enum-neutral-names.md]. The remaining artifact is still blueprint-consumable per phase — `/blueprint` the artifact, "Implement Phase 1: Foundation", repeat. Phase 7 remains operator-gated on Plane sunset; the live unit/env rename after #073 remains an operator-coordinated follow-up outside the code-side dual-read slice [source: wiki/raw/sessions/2026-06-17-root-scheduler-architecture-review.md].
