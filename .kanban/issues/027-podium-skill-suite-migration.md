---
id: 027
title: Plane-coupled symphony-* skill suite migration
status: in-progress
blocked_by: [019]
parent: null
priority: 0
created: 2026-06-10
updated: 2026-06-11
actor: ralph
---

## What to build

Per ADR-0005 ¶11: the six existing `symphony-*` skills that mutate or
inspect Plane today must either retire, migrate to Podium, or become
tracker-agnostic via the Tracker Adapter seam. Without this work, the
homelab cutover (#023c) leaves the operator with a broken skill suite.

Per-skill plan:

1. **`symphony-project-scaffold`** — currently creates a Plane project +
   appends to `bindings.yml`. Migrate: split into
   - `symphony-binding-scaffold` (Podium path): create the binding row
     directly in Podium DB + append to `bindings.yml` with
     `tracker: podium`. No tracker mutation.
   - The Plane-only path stays in source as a deprecated alias for the
     v2 hedge; documented "Plane is dormant" in the skill's SKILL.md.

2. **`symphony-binding-smoke`** — currently files a Plane issue and
   watches the Run. Migrate: file via Podium API (`POST /api/bindings/{name}/issues`
   from #014), poll the Run row, report verdict. Same observable
   behaviour, different write path.

3. **`symphony-bindings-status`** — currently reads Plane + journalctl.
   Migrate: read Podium DB (`GET /api/bindings`, then per-binding
   `/api/issues`) + journalctl. Same table output.

4. **`symphony-plane-recover`** — Plane-only by name and purpose. Keep
   as-is (used in #023d for archive). Mark as "Plane retirement tool
   only" in its SKILL.md.

5. **`symphony-onboard-project`** — umbrella over scaffold + workflow-author
   + restart + binding-smoke. Update to call the migrated sub-skills.

6. **`symphony-workflow-author`** — edits `WORKFLOW.md` on disk, not
   Plane. Already tracker-agnostic; only needs a docstring update
   acknowledging it works against both Podium and Plane bindings.

Tests for each migrated skill exercise the Podium API path. The Plane
path is left in source but is not exercised by any test in this slice.

## Acceptance criteria

- [ ] `symphony-binding-scaffold` skill exists and creates a binding via the Podium DB + `bindings.yml` edit (no Plane API call).
- [ ] `symphony-binding-smoke` posts via Podium `POST /api/bindings/{name}/issues` and polls the resulting Run row.
- [ ] `symphony-bindings-status` reads `GET /api/bindings` + per-binding issues; table format unchanged.
- [ ] `symphony-plane-recover` SKILL.md updated to document its Plane-only purpose.
- [ ] `symphony-onboard-project` calls the migrated sub-skills.
- [ ] `symphony-workflow-author` SKILL.md notes tracker-agnostic behaviour.
- [ ] Each migrated skill has its own integration test under `tests/skills/test_<skill>.py` against a temp Podium DB fixture.
- [ ] No migrated skill imports `plane_adapter` or makes HTTP calls to the Plane API.

## Verification

```
cd /home/james/symphony && uv run pytest
```

## Blocked by

- #019 (Podium Tracker Adapter must exist before skill migrations can read from it)
