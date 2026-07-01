# Projects define how agents react; decompose the binding_type bundle into per-binding capabilities + a project-supplied preamble

## Status

proposed (2026-07-01). Outcome of a `/grill-me` pass over issue #174.

Supersedes the engine-owned `INFRA_PREAMBLE` constant introduced by
[ADR-0016](0016-workflow-md-retired-renderer-constant.md) and completes
ADR-0016's own stated portability goal ("install on a new host → author a
`CLAUDE.md`, touch nothing else"), which the constant broke by hardcoding infra
prose into the renderer. Builds on the preamble-stripping precedent of
[ADR-0031](0031-operator-driven-plan-build-not-engine-modes.md).

## Context

Issue #174 began as "turn the homelab infra binding into a coding binding so the
project can define how patrols are handled." The grill traced the real intent to
a larger goal: **Symphony should be an environment-agnostic engine; each project
defines how its agents react.** The operator's homelab is not their work
production environment, and they want to deploy the same engine to both without
editing engine code — tickets arrive via adapters, and the *project* decides the
agent's behavior.

`binding_type` (`infra` | `coding`) obstructs this because it is a **bundle**:
one flag (`is_coding`) gates six unrelated behaviors at once.

| Behavior | Kind | Belongs to |
|---|---|---|
| `INFRA_PREAMBLE` prose ("you are a Symphony infra agent…", 17 rules) | policy/prompt | the **project** |
| verify-the-cure / block-vs-schedule decision | policy/prompt | the **project** |
| maintenance-window hold + re-dispatch (`_select_scheduled_candidate`) | engine capability | the **engine** |
| blocked-reconciler auto-cure | engine capability | the **engine** |
| approval gate (`approval.enabled`) | engine capability — *already per-binding* | the **engine** |
| auto-close-on-verified (`auto_close_on_verified`) | engine capability — *already per-binding* | the **engine** |

Two of the six are **already** independent per-binding flags — proof the pattern
works. The obstacle is that the remaining four are welded to `binding_type`.

Flipping homelab to `coding` as the type exists today does **not** deliver
portability: it correctly moves the *policy/prompt* rows into the project
(`body = ""`, "issue is the prompt"), but it also silently drops the two genuinely
useful *engine capabilities* (window scheduling, reconciler cure) that a prompt
cannot re-express — a prompt cannot hold itself for six hours until the
maintenance window. The operator would trade portability for amnesia.

Separately, the grill surfaced that the `INFRA_PREAMBLE` prose is applied to
**every** homelab dispatch, including an operator's ad-hoc coding reply from the
issue flyout. This is why coding tasks on the homelab binding "act differently" —
the agent wears the infra-agent hat even when the operator just wants a normal
coding session. The operator was surprised the preamble still existed at all,
having understood ADR-0016 to have removed it (ADR-0016 *relocated* it from a
per-repo `WORKFLOW.md` into the engine constant, the opposite of project-owned).

## Decision

**Decompose the bundle. The engine owns capabilities; the project owns the
preamble.**

1. **Engine stops shipping `INFRA_PREAMBLE`.** The renderer no longer chooses
   preamble by `binding_type`. A binding may point at a **project-supplied
   preamble** (a repo-relative file path, e.g. `preamble: SYMPHONY.md`). Absent or
   empty → the engine renders **no preamble** (pure "issue is the prompt"). This
   is the strip-it-all default the operator asked for; the homelab-specific infra
   prose moves into the homelab repo.

2. **Scheduling and blocked-reconciliation become per-binding opt-in flags**,
   joining the existing `approval.enabled` and `auto_close_on_verified`. A binding
   that wants maintenance-window self-scheduling opts into it; one that does not
   renders nothing extra and the scheduler skips it. Homelab opts into
   `scheduling` to retain the ADR-0018 window machinery; it is no longer implied
   by an `infra` type.

3. **`binding_type` degrades to a thin preset**, not a behavior gate. It expands
   to a set of capability-flag defaults at config load (back-compat: existing
   `infra`/`coding` bindings resolve to today's behavior), but no engine branch
   reads `binding_type` directly anymore — every branch reads a specific
   capability flag. Removal of the enum is a later cleanup (flagged, not done),
   mirroring ADR-0031's inert-vestige posture.

## Rollout

Engine decomposition lands **first**, with every capability flag defaulting to
the value its old `binding_type` implied — so no live binding changes behavior on
deploy. Then, as a **separate homelab-repo follow-up**, homelab flips to the
stripped configuration: authors its own preamble + patrol-response skill, opts
into `scheduling`, and re-homes the patrol self-healing work (finding-state
marker, fail-side suppression, `patrol-tune` skill) as **project content** rather
than engine content.

## Consequences

- **Portability achieved:** the same engine serves homelab and a work production
  environment by supplying a different project preamble + capability-flag set. No
  engine code change per environment. This is the north-star the operator stated.
- **Ad-hoc coding on any binding feels neutral:** with no project preamble (or a
  coding-oriented one), an operator flyout reply is a plain coding session — the
  "acts differently" friction disappears.
- **Hard-to-reverse:** deleting the engine's infra prose and moving it into
  projects means every infra behavior now depends on project-authored text; a
  project that ships no preamble gets a bare agent. This is the intended trade —
  the engine stops having opinions about live-systems work — but it is a real
  ownership shift future sessions must honor.
- **ADR-0018 window scheduling survives** as an opt-in capability, not as an
  infra-type side effect. ADR-0015 patrol→Podium routing is unaffected (adapter
  seam, orthogonal to preamble/capabilities).
- **Inert vestige:** `binding_type` remains in `bindings.yml` and config as a
  preset label; no engine branch acts on it. Cleanup deferred.

## Rejected alternatives

- **Flip homelab→coding as-is** (the issue's literal title) — drops window
  scheduling and reconciler cure, which are not re-expressible as project prose.
- **Keep the bundle, add a third `binding_type`** — multiplies presets without
  addressing that the six behaviors are orthogonal; does not generalize to a new
  environment with a different mix.
- **Skill-selected preamble** (considered mid-grill) — solves the flyout-friction
  and patrol-tune-lane symptoms but leaves the engine owning the infra prose;
  a partial fix that does not deliver environment portability.

## Related

- [ADR-0016 — WORKFLOW.md retired → INFRA_PREAMBLE constant](0016-workflow-md-retired-renderer-constant.md) — the constant this supersedes; ADR-0032 completes its portability goal.
- [ADR-0031 — operator-driven plan/build, not engine modes](0031-operator-driven-plan-build-not-engine-modes.md) — the preamble-stripping + inert-vestige precedent.
- [ADR-0018 — patrol medium-risk window scheduling](0018-patrol-medium-risk-window-scheduling.md) — the window machinery preserved as an opt-in capability.
- [ADR-0015 — patrol→Podium tracker adapter](0015-patrol-podium-tracker-adapter.md) — adapter routing, orthogonal and unaffected.
