---
status: accepted
---

# ADR-0030 — podium-issues validates model/agent against the catalog at load, sharing one contract with dispatch

## Context

`web/cli/podium_issues.py` turns an LLM-sliced plan into Podium issues. Until now it was a
"boring sink": it resolved the binding for cwd, inserted slices in dependency order, and hard-coded
`preferred_model = NULL` while only redundantly restating `binding.default_agent` into
`preferred_agent`. An operator could not pin a model from the `/podium-issues` skill, and there was
no authoring-time guard against a model the scheduler would reject.

Model selection is resolved at dispatch: `scheduler/__init__.py::_apply_dispatch_gate` calls
`model_catalog.resolve_model(issue.preferred_model, models, agent=resolved_agent)` and then asserts
the returned entry's agent equals the issue's resolved agent — a mismatch blocks dispatch loudly. The
`resolve_model` resolver alone is **not** the full verdict: its `if len(matches) == 1: return
matches[0]` branch can return a single catalog match whose agent differs from the one requested, so
the separate agent-match assertion is the part that catches a model/agent mismatch. A shared model id
like `claude-opus-4-8` lives under both the `claude` and `pi` agents, so model alone is not complete
control — `agent:` must be threadable too.

The risk of leaving the sink as a pure sink: a typo'd or agent-incompatible `model:` would write an
`auto_land=true` issue that silently sits in `todo` and only fails at dispatch, potentially stalling a
dependent batch (every downstream slice is `blocked_by` it) for an authoring mistake that could have
been caught before any row was inserted.

## Decision

**The sink becomes a catalog-validating authoring tool.** Each slice may optionally carry `model:` and
`agent:`. The sink threads them onto the issue row (`preferred_model`/`preferred_agent`) and, when at
least one slice sets a model, validates every model-bearing slice against `models.yml` at load time
using the **same contract dispatch uses**:

- `model_catalog.resolve_model(slice.model, models, agent=resolved_agent)` must succeed; and
- the returned entry's `agent` must equal the slice's resolved agent (`slice.agent or
  binding.default_agent`).

This is the model/agent portion of `_apply_dispatch_gate` — deliberately not the full gate, which
also probes the claude engine and validates `preferred_skill`/`reasoning_effort` at runtime. Those are
environmental and not authorable from a plan slice, so they stay dispatch-side.

Authoring and dispatch now share one resolver + one assertion, so they can never disagree on what is
acceptable. A bad model fails before any issue row is inserted, in both live and `--dry-run`.

The no-model / no-agent path is byte-identical to today: `preferred_agent` still falls back to
`binding.default_agent` (with a defensive `or "pi"` so the validator and the writer agree) and
`preferred_model` stays NULL; `load_models()` is never called when no slice sets a model, so existing
plans and the default-plan regression tests are unaffected.

## Considered alternatives

- **Pure sink; let dispatch catch bad models.** Rejected — an `auto_land=true` issue with a typo'd
  model would sit silently in `todo` and only block at dispatch, stalling its dependent batch for a
  fixable authoring mistake. Load-time validation fails fast, before any row exists.
- **Call `_apply_dispatch_gate` directly.** Rejected — it is scheduler-internal and depends on live
  `CandidateIssue`/`ProjectBinding` objects plus environmental probes (claude engine, skill files)
  that are not available at authoring time. Reusing `resolve_model` + the agent-match assertion
  reproduces the authorable portion of the verdict with no scheduler coupling. `resolve_model` alone
  is insufficient for the reason in Context (the single-match branch can return the wrong agent).

## Consequences

- `/podium-issues` can pin a model (and optionally an agent) per slice; the scheduler dispatches that
  exact pair.
- A typo'd, unknown, empty, or agent-incompatible `model`/`agent` fails `create-from-plan` with a
  clear `PodiumIssuesError` before any issue is inserted — in both live and dry-run.
- The sink stops being a pure sink; its docstring was updated in the same change to drop the
  "boring sink" framing.
- The validator does **not** guarantee dispatch of a `claude`-agent issue if the claude engine probe
  fails at runtime — that check is environmental, not authorable, and remains dispatch-side.
- Per-slice `reasoning_effort` stays hard-coded `'high'` (orthogonal to "which model"); it is a clean
  follow-up if a per-slice effort knob is ever requested.
