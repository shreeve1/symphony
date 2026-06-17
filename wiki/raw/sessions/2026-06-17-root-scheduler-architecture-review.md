# Session Capture: Root scheduler module architecture review + Pi meta-review

- Date: 2026-06-17
- Purpose: Layer-by-layer architecture review of Symphony's root scheduler module (24 top-level `*.py`, ~11.6k LOC), then an independent Pi (`openai-codex/gpt-5.5`) meta-review of the resulting artifact.
- Scope: Durable structural findings, triage decisions, methodology principles, the phased plan, and the Pi-review corrections. No source code was modified — the product is the review artifact only.

## Durable Facts

- The architecture review artifact lives at `.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md` (git-ignored). 8 layers, 41 findings (29 accepted, 5 rejected, 7 deferred), 2 methodology principles, 8 cross-cutting themes, 7-phase plan. — Evidence: `.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`
- The root module import graph is a clean DAG (no cycles); entry point `main.py`, central hub `scheduler.py` (3039 LOC). — Evidence: `scheduler.py`, `main.py`
- `scheduler.py:run_tick` is ~882 LOC (`scheduler.py:1168-2050`) and contains a duplicated resume-fallback retry block (`:1521-1605` ≈ `:1615-1697`). Highest-leverage refactor (review theme T4). — Evidence: `scheduler.py:1168-2050`
- The tracker-agnostic engine vocabulary lives *inside* the Plane adapter: `CandidateIssue` (`plane_adapter.py:53`), `CommentPayload`, `IssuePayload`, and the `TrackerAdapter` Protocol (`plane_adapter.py:136`). `CandidateIssue` is field-equivalently duplicated in `tracker_podium.py:42` (Podium copy has extra comments, not byte-identical). `TrackerAdapter` Protocol is also defined divergently in `tracker_adapter.py:15`. Review proposes a neutral `tracker_types.py` home (theme T7). — Evidence: `plane_adapter.py:53,136`, `tracker_podium.py:42`, `tracker_adapter.py:15`
- `_PLANE_COOLDOWN_UNTIL` (`scheduler.py:67`) is a module global that dual-tracks rate-limit cooldown across all bindings, undermining the per-binding `_DispatchState` isolation (review finding L1-04). — Evidence: `scheduler.py:63-67,131-182`
- All 4 live bindings are `tracker: podium` (homelab, symphony, dotfiles, n8n); there are zero `tracker: plane` bindings. The Plane dispatch path is therefore currently **dormant**, not active. — Evidence: `bindings.yml`
- Because all live bindings are Podium, `agent_runner` ships the Plane-only `plane` helper CLI (`plane_cli.py`) AND injects `SYMPHONY_PLANE_API_KEY` + Plane callback env into every agent subprocess (`agent_runner._agent_env:213-218`, also `run_agent:285`/`run_remote_agent:454`/`run_pi_rpc_agent:600`) for a tracker no live agent calls — a present secret-exposure surface and dead weight (review finding L6-02, sharpened by Pi). — Evidence: `agent_runner.py:213-218,285,454,600`, `bindings.yml`
- `web/api/main.py:_compact_issue_context` (`:925`) reaches engine internals through four `vars()` reflections: `vars(engine_main)["SymphonyConfig"]` (`:930`), `vars(engine_main)["_build_binding_runtime"]` (`:957`), `vars(compaction)["maybe_compact"]` (`:987`), `vars(compaction)["estimate_tokens"]` (`:1000`); plus `from tracker_podium import CandidateIssue` (`:927`). — Evidence: `web/api/main.py:925-1000`
- The two `_render_candidate_prompt` functions are NOT duplicates: `main.py:53-89` maps `CandidateIssue → IssueData` and calls `render_prompt`; `scheduler.py:593-607` is a signature-adapter shim that forwards `resume=` only when the injected renderer accepts it. They share a name, not logic — the defect is a naming collision, not DRY. — Evidence: `main.py:53-89`, `scheduler.py:593-607`

## Decisions

- Architecture-review triage (James-approved per finding): accept 29, reject 5, defer 7. Notable keeps (wise-decision lens): keep engine→`web.api.db` coupling (Podium *is* the web DB), keep hand-written `SymphonyConfig.__repr__` on a deny-by-omission security argument, keep `(value, error|None)` tuple returns, keep `schedule.py` as one file, keep `plane_cli`'s standalone Telegram sender. — Evidence: `.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md`
- Two methodology principles recorded: M1 — keep tested zero-consumer primitives that pair with an existing flow; M2 — verify an unusual coupling's reason before "fixing" it (several `vars()`/lazy-import/cross-layer "smells" were deliberate). — Evidence: artifact Methodology Principles section
- 7-phase plan: P1 Foundation → P2 shared-helper homes → P3 `tracker_types` → P4 scheduler decomposition (highest risk, live dispatch) → P5 entry/boundary + Plane-secret de-shipping → P6 post-Plane vocabulary migration (deferred, systemd env contract) → P7 legacy Plane-path removal (deferred, gated on Plane sunset). — Evidence: artifact Consolidated polish plan
- Pi meta-review corrections accepted (James: "all five"): L0-01 corrected from "consolidate duplicate mapper" to "rename the shim"; L0-06 added for the `web/api` reflection cluster; L6-02 split — the Plane-secret de-shipping moves into accepted Phase 5, full `plane_cli` deletion stays deferred Phase 7; L3-01 reworded "byte-identical"→"field-equivalent"; Phase 3 explicitly repoints `web/api/main.py:927`. — Evidence: artifact frontmatter `last_updated_note`, revised L0-01/L0-06/L6-02/L3-01

## Evidence

- `.rpiv/artifacts/architecture-reviews/2026-06-16_22-42-19_root-scheduler-module.md` — the full review artifact (findings, principles, themes, plan).
- `bindings.yml` — all live bindings are `tracker: podium`.
- `scheduler.py`, `main.py`, `agent_runner.py`, `plane_adapter.py`, `tracker_podium.py`, `tracker_adapter.py`, `web/api/main.py` — source verified for the cited findings.

## Exclusions

- No secrets captured (bindings.yml carries no secrets by design; `symphony-host.env` not read).
- Full per-finding detail is not duplicated here — the artifact is the authoritative source; this capture records the durable, citable conclusions only.
- No source code was modified this session; the pre-existing `web/frontend/*` working-tree changes are unrelated to this review.

## Open Questions And Follow-Ups

- Implementation has not started. Next action: `/blueprint` the artifact per phase (Phase 1 first).
- Near-term security cleanup (Phase 5 / L6-02a): stop shipping `SYMPHONY_PLANE_API_KEY` + the `plane` helper to Podium agents.
- Deferred and operator-gated: P6 vocabulary migration touches the live `symphony-host.service` env contract (ask James); P7 Plane-path removal needs a confirmed Plane sunset (no live `tracker:plane` binding — currently true, but the path is kept as a rollback hedge).
