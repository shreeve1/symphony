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
  - bindings.yml
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

All 4 live bindings are `tracker: podium` (homelab, symphony, dotfiles, n8n); **zero** `tracker: plane` bindings, so the Plane dispatch path is **currently dormant** but kept as a rollback hedge [source: bindings.yml]. Consequence surfaced by the Pi meta-review: `agent_runner` still ships the Plane-only `plane` helper **and `SYMPHONY_PLANE_API_KEY`** to every agent subprocess (`_agent_env:213-218`) for a tracker no live agent calls — a present secret-exposure surface. The review splits this (finding L6-02): de-shipping the secret/helper to Podium agents is a near-term **accepted Phase 5** security cleanup; full `plane_cli`/Plane-path deletion stays deferred (theme T8), gated on a confirmed Plane sunset [source: agent_runner.py:213-218, bindings.yml].

## Pi meta-review corrections (2026-06-17)

An independent Pi review (read-only verified) produced 5 findings, all verified against source and applied: (1) **L0-01 was a misdiagnosis** — `scheduler._render_candidate_prompt` (`:593-607`) is a signature-adapter shim, not a duplicate of `main`'s `CandidateIssue→IssueData` mapper; reframed from "consolidate" to "rename". (2) **L0-06 added** — the `web/api` reflection cluster was under-scoped (4 `vars()` sites, not 1). (3) **L6-02 re-prioritized** — Plane-secret de-shipping moved into accepted Phase 5. (4) `CandidateIssue` "byte-identical"→"field-equivalent". (5) Phase 3 explicitly repoints `web/api/main.py:927` [source: .rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md, web/api/main.py:925-1000].

## Status & next action

Audit complete; implementation has started. Issue #45 landed the first small polish batch: L0-01 renamed the scheduler renderer shim to `_invoke_renderer` while leaving `main._render_candidate_prompt` intact; L5-03 routed config and `RoutingAgentAdapter` valid-agent checks through `model_catalog.KNOWN_AGENTS`; L4-01 extracted `schedule._decode_entity_at` while preserving branch-specific handling. Verification passed with the full Python suite (`uv run pytest`: 878 passed, 2 skipped) [source: scheduler.py, main.py, model_catalog.py, config.py, agent_runner.py, schedule.py]. Issue #64 then landed T7's tracker vocabulary home: `tracker_types.py` now owns `CandidateIssue`, `CommentPayload`, `IssuePayload`, label/state helpers, ISO parsing, candidate conversion, and Plane-style cursor/page helpers; `tracker_adapter.py` is the sole `TrackerAdapter` Protocol home; concrete Plane/Podium adapters import those shared definitions. Verification passed with the full Python suite (`uv run pytest -q`: 881 passed, 2 skipped) [source: tracker_types.py, tracker_adapter.py, plane_adapter.py, tracker_podium.py, scheduler.py, blocked_reconciler.py, web/api/main.py]. The remaining artifact is still blueprint-consumable per phase — `/blueprint` the artifact, "Implement Phase 1: Foundation", repeat. Phases 6–7 are operator-gated (P6 touches the live `symphony-host.service` env contract; P7 needs Plane sunset) [source: wiki/raw/sessions/2026-06-17-root-scheduler-architecture-review.md].
