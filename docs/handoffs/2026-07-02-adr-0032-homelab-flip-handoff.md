# Handoff — ADR-0032 homelab flip: full context for the homelab agent

Audience: the agent working the **homelab** binding (repo `/home/james/homelab`)
to complete the ADR-0032 flip. This doc is the single source of truth for what
the Symphony engine now provides, what the homelab side already committed, and
what remains. Read it start-to-finish before acting.

## 1. What ADR-0032 is (the "why")

`binding_type` (`infra`|`coding`) was a **bundle**: one flag gated six unrelated
behaviors. ADR-0032 (`docs/adr/0032-project-defined-agent-reaction-not-binding-type-bundle.md`
in the symphony repo) decomposes it so the **engine owns capabilities** and the
**project owns how its agents react** (a project-supplied preamble). Goal:
environment-agnostic engine — homelab and a work-prod environment run the same
engine with different preambles + capability flags, no engine code change.

The operator's driving intent: strip the engine-owned infra preamble; let the
homelab repo define patrol handling; move toward a self-healing patrol loop
(findings worked like tickets, repeated-failure findings tuned-or-suppressed
instead of re-nagging every cycle).

## 2. What the engine now provides (LANDED — symphony #178–#181)

All merged to symphony `main`. Verified surfaces:

- **Per-binding capability flags** (`config.py`, `ProjectBinding`):
  - `scheduling: bool` — default derives from `binding_type` (infra→True, coding→False).
  - `blocked_reconciler: bool` — same default rule.
  - `worktree_default` — a property: explicit value wins, else `binding_type == "coding"`
    (infra→False = commit-to-base, coding→True = per-issue worktrees).
  - `preamble: str | None` — repo-relative path to the project preamble file.
  - `approval.enabled` / `auto_close_on_verified` — already per-binding (pre-ADR-0032).
- **bindings.yml keys accepted** (all optional; omitted → binding_type-derived default):
  `preamble`, `scheduling`, `blocked_reconciler`, `worktree_default`.
- **Preamble resolution** (`main.py:112-114`): `repo_path / preamble`. A file at the
  homelab repo root named e.g. `SYMPHONY.md` → `preamble: SYMPHONY.md`.
- **Renderer** (`prompt_renderer.py`): no preamble configured (or missing file) →
  NO preamble, pure "issue is the prompt". `OUTPUT_CONTRACT` is ALWAYS appended
  (verdict grammar is engine-owned; never put it in the project preamble).
- **Scheduler** (`scheduler/__init__.py`): scheduling/reconciler/marker paths now
  read the capability flags, not `is_coding`.

## 3. Known engine gap being fixed in parallel (symphony #188)

`prompt_renderer.py` still gates **schedule-context injection** on
`binding_type != "coding"` (two sites: normal ~L371, resume ~L419) instead of the
`scheduling` capability. #188 fixes it to gate on `scheduling`.

**Impact on homelab: NONE today.** Homelab stays `type: infra` AND opts into
`scheduling: true`, so the old and new gates agree — homelab keeps getting its
"you're in the approved window, apply now" schedule context either way. You do
NOT need to wait for #188. It only matters for a future binding where
`binding_type` and `scheduling` diverge.

## 4. What the homelab side already committed (homelab `252db37`)

From the #184 grill (`plans/adr-0032-homelab.md` in the homelab repo):

- **D1 Worktree: NO.** `worktree_default: false` — commit-to-base infra
  remediation. Avoids the ADR-0032 trap (coding preset silently enabling
  per-issue worktrees + Landing). Conservative default; operator can override.
- **D2 CLAUDE.md vs preamble: layered, no duplication.** CLAUDE.md owns host
  safety/autonomy policy; `SYMPHONY.md` owns the operational contract and points
  at CLAUDE.md. CLAUDE.md safety header updated to cite the ADR-0032 project
  preamble instead of the retired INFRA_PREAMBLE.
- **D3 Preamble content:** `SYMPHONY.md` (~12 rules). Dropped the engine-owned
  identity line + anything OUTPUT_CONTRACT already covers (verdict grammar,
  answer-naturally, end-with-contract). Kept orient / verify-live-state /
  doc-scope / git-ownership / access-subagents / trusted-issue-body /
  verify-the-cure.
- **D4 Patrol self-healing as project content:** `.claude/skills/patrol-response`
  and `.claude/skills/patrol-tune`. Marker gains `consecutive_fails`
  (worker-owned) + `consecutive_blocks` / `last_blocked_at` / `suppressed_until`
  (agent-owned). Thresholds: `consecutive_fails >= 3` → review;
  `consecutive_blocks >= 3` → patrol-tune (adjust threshold / bounded suppression
  / escalate — NEVER silently pause a schedule).

## 5. What REMAINS (the actionable checklist)

### 5a. bindings.yml edit — REQUIRED, this is the actual flip (symphony repo)
Lives in `/home/james/symphony/bindings.yml` (the `homelab` entry). It is a
**different binding** than homelab, so the homelab agent cannot commit it — the
operator applies it or dispatches it as a symphony issue. Exact edit, all
values equal to today's infra defaults (behavior-neutral on deploy):

```yaml
# homelab binding entry — add:
    preamble: SYMPHONY.md
    scheduling: true
    blocked_reconciler: true
    worktree_default: false
```

After editing: restart `symphony-host.service` and confirm the journal shows the
binding loaded. Then verify a homelab dispatch renders `SYMPHONY.md` as the
preamble (not INFRA_PREAMBLE) and still includes Schedule Context on a scheduled
release.

### 5b. patrol_plane.py marker fields — DEFERRED for operator schema sign-off
The four additive marker fields (`consecutive_fails`, `consecutive_blocks`,
`last_blocked_at`, `suppressed_until`) + tests are spec'd in
`plans/adr-0032-homelab.md`. Do NOT touch the live patrol write path until the
operator signs off the marker schema. The skills (agent-driven procedure) are
already committed; the worker-code half waits.

### 5c. Consolidated /wiki-update (symphony repo, interactive session)
After this batch lands: repoint ADR-0015/0016/0018 wiki pages + the
`binding_type` routing entries to ADR-0032; add the homelab binding model + the
two new patrol skills as entity/concept pages. Not doable during slice runs
(ADR-0028).

## 6. Sequencing

1. Apply 5a (bindings.yml) → restart → verify preamble + schedule context. This
   makes the flip live and behavior-neutral.
2. Operator signs off marker schema → implement 5b.
3. #188 lands independently (no homelab dependency).
4. Consolidated /wiki-update once everything lands.

## 7. Do-not-break invariants

- OUTPUT_CONTRACT is engine-owned — never move verdict grammar into `SYMPHONY.md`.
- Keep `scheduling: true` on homelab or you lose ADR-0018 maintenance-window
  self-scheduling (medium-risk findings would block with no exit again).
- `worktree_default: false` — infra remediation commits to base; do not enable
  worktrees without an explicit operator decision (the ADR-0032 trap).
- patrol-tune must never silently pause a schedule; escalate to the operator.
