---
title: "ADR-0032 — Projects define agent reaction; decompose the binding_type bundle"
type: analysis
status: promoted
created: 2026-07-02
updated: 2026-07-02
sources:
  - docs/adr/0032-project-defined-agent-reaction-not-binding-type-bundle.md
  - config.py
  - prompt_renderer.py
  - main.py
  - scheduler/__init__.py
  - scheduler/dispatch_state.py
  - bindings.yml
  - tests/test_config.py
  - tests/test_prompt_renderer.py
  - tests/test_prompt_renderer_podium.py
confidence: high
tags: [adr, binding_type, preamble, capability-flags, scheduling, blocked-reconciler, worktree, infra-preamble, prompt-renderer, homelab, patrol]
---

# ADR-0032 — Projects define agent reaction; decompose the `binding_type` bundle

**Status: `proposed` in the ADR file (2026-07-01); engine decomposition #178–#181 + #188 landed to `main`; homelab binding flip (5a) deployed live 2026-07-02 (`symphony-host.service` PID 904584, `code_sha=84304c3`).**

`binding_type` (`infra`|`coding`) was a **bundle**: one `is_coding` flag gated six unrelated behaviors. ADR-0032 decomposes it so the **engine owns capabilities** and the **project owns how its agents react** (a project-supplied preamble file). Goal: an environment-agnostic engine — homelab and a work-prod environment run the same engine with different preambles + capability flags, no engine code change. It supersedes the engine-owned `INFRA_PREAMBLE` constant from ADR-0016 and completes ADR-0016's own portability goal, which the constant broke by hardcoding infra prose into the renderer [source: docs/adr/0032-project-defined-agent-reaction-not-binding-type-bundle.md].

## The bundle and its decomposition

Six behaviors were welded to `binding_type`. Two (`approval.enabled`, `auto_close_on_verified`) were already per-binding — proof the pattern works. The other four were split out [source: docs/adr/0032-project-defined-agent-reaction-not-binding-type-bundle.md]:

| Behavior | New owner |
|---|---|
| `INFRA_PREAMBLE` prose (identity + 17 rules) | project — a repo-relative `preamble:` file |
| verify-the-cure / block-vs-schedule policy | project — preamble content |
| maintenance-window hold + re-dispatch | engine — `scheduling` flag |
| blocked-reconciler auto-cure | engine — `blocked_reconciler` flag |
| worktree defaulting | engine — `worktree_default` flag (was `binding_type == "coding"`) |

Flipping homelab to `type: coding` would NOT have delivered portability: it correctly moves policy/prompt into the project (`body = ""`, "issue is the prompt") but silently drops the two useful engine capabilities (window scheduling, reconciler cure) that a prompt cannot re-express — a prompt cannot hold itself for six hours until the maintenance window. That is why the split is per-capability, not a type swap [source: docs/adr/0032-project-defined-agent-reaction-not-binding-type-bundle.md].

## What landed in the engine (#178–#181, verified this session)

- **Per-binding capability flags** on `ProjectBinding` (`config.py`): `scheduling: bool`, `blocked_reconciler: bool`, `preamble: str | None`, and `worktree_default` as a property (explicit value wins, else `binding_type == "coding"`). Defaults derive from `binding_type` (`infra`→scheduling/reconciler True, worktree False; `coding`→inverse), so no live binding changed behavior on deploy [source: config.py].
- **bindings.yml keys accepted** (all optional; omitted → type-derived default): `preamble`, `scheduling`, `blocked_reconciler`, `worktree_default` [source: config.py].
- **Preamble resolution** (`main.py`): `repo_path / preamble`. Absent or missing file → NO preamble, pure "issue is the prompt". `OUTPUT_CONTRACT` is ALWAYS appended — it is the harness (git ownership + `SYMPHONY_RESULT`/`SYMPHONY_SCHEDULE`/`SYMPHONY_QUESTION` grammar the scheduler parses), a separate constant from `INFRA_PREAMBLE`; "strip the preamble" never means dropping the output contract [source: main.py; source: prompt_renderer.py; source: docs/adr/0032-project-defined-agent-reaction-not-binding-type-bundle.md].
- **Scheduler** reads capability flags, not `is_coding`: `_select_scheduled_candidate`, blocked reconciler, and `SYMPHONY_SCHEDULE` marker detection all gate on `scheduling`/`blocked_reconciler` [source: scheduler/__init__.py].
- **`binding_type` degraded to a thin preset**: it expands to capability-flag defaults at config load; removal of the enum is a later cleanup (inert-vestige posture, mirroring ADR-0031). The remaining `binding_type` params in the renderer are non-gating [source: config.py; source: prompt_renderer.py].

## #188 — schedule-context gating (landed `3c4138b`)

The known engine gap: `prompt_renderer.py` still gated **schedule-context injection** on `binding_type != "coding"` at two sites (normal + resume) instead of the `scheduling` capability. Fixed by `3c4138b`: `render_prompt` accepts `scheduling: bool` and gates both sites on it; `main.py` threads `binding.scheduling`. Schedule-context-asserting tests pass `scheduling=True`; the former coding-omit test gates on `scheduling=False`. Impact on homelab was NONE (homelab stays `type: infra` AND `scheduling: true`, so old and new gates agree); it matters only for a future binding where `binding_type` and `scheduling` diverge. Verified: 32 renderer tests pass [source: prompt_renderer.py; source: main.py; source: tests/test_prompt_renderer.py; source: tests/test_prompt_renderer_podium.py].

## The homelab flip (5a, live 2026-07-02)

`bindings.yml` `homelab` entry made its capabilities explicit (all three flag values equal the `type: infra` defaults, so the flip is behavior-neutral on deploy; only `preamble` is a real change) [source: bindings.yml]:

```yaml
  preamble: SYMPHONY.md      # re-homed INFRA_PREAMBLE, resolved at /home/james/homelab/SYMPHONY.md
  scheduling: true           # keep ADR-0018 maintenance-window machinery
  blocked_reconciler: true   # keep patrol auto-cure
  worktree_default: false    # D1: commit-to-base infra remediation, no Landing
```

The homelab side (repo `/home/james/homelab`, ADR-0032 D1–D4) authored `SYMPHONY.md` (the operational contract, pointing at `CLAUDE.md` for host safety policy), and re-homed patrol self-healing as project content: `.claude/skills/patrol-response` + `.claude/skills/patrol-tune`, plus four additive patrol-status marker fields (`consecutive_fails` worker-owned; `consecutive_blocks`/`last_blocked_at`/`suppressed_until` agent-owned). That worker/skill work lives in the homelab wiki, not here. Deploy = `symphony-host.service` restart; verified `symphony_started code_sha=84304c3 bindings=6`, homelab binding reconciled clean, `pi_rpc_probe_ok`, zero errors [source: bindings.yml; source: config.py].

**Do-not-break invariants:** keep `scheduling: true` on homelab or ADR-0018 medium-risk window self-scheduling is lost (medium-risk findings block with no exit again); keep `worktree_default: false` (infra remediation commits to base — enabling worktrees silently adds Landing, the ADR-0032 trap); never move `OUTPUT_CONTRACT` into a project preamble [source: docs/adr/0032-project-defined-agent-reaction-not-binding-type-bundle.md; source: scheduler/dispatch_state.py].

## Relationship to prior ADRs

- **Supersedes** the ADR-0016 `INFRA_PREAMBLE` engine constant (ADR-0016 *relocated* the infra prose from a per-repo `WORKFLOW.md` into the engine — the opposite of project-owned; ADR-0032 moves it back into the project as a preamble file). See C-0276/C-0277/C-0278.
- **Retains** ADR-0018 maintenance-window scheduling as the `scheduling` capability (no longer implied by `infra` type). See C-0298–C-0301.
- **Builds on** ADR-0031's preamble-stripping precedent and inert-vestige cleanup posture.

## Open follow-ups

- `binding_type` enum removal is a flagged later cleanup, not done — no engine branch reads it directly now, but the preset still expands to defaults.
- Consolidated repoint of the `binding_type`/`INFRA_PREAMBLE` routing keywords toward the capability model is partially done here; the `workflow-homelab.md` entity page carries an ADR-0032 update note.
