---
title: Pi personal harness profile
type: analysis
status: promoted
created: 2026-06-12
updated: 2026-06-17
sources:
  - wiki/raw/sessions/2026-06-12-personal-harness-pi.md
  - wiki/raw/personal-harness-pi-profile.md
  - .rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md
  - .pi/extensions/personal-harness.ts
  - wiki/raw/sessions/2026-06-17-personal-harness-pi-removal.md
confidence: high
tags: [pi, harness, validation, safety, tooling, removed]
---

# Pi personal harness profile

Historical status: Symphony had a project-local Pi personal harness generated at `.pi/extensions/personal-harness.ts`, sourced from tracked `wiki/raw/personal-harness-pi-profile.md` (with the ignored `.rpiv` artifact kept as local skill output) [source: wiki/raw/sessions/2026-06-12-personal-harness-pi.md#durable-facts]. James removed the project-local extension file on 2026-06-17; future Pi reloads/sessions should no longer auto-discover this harness from the project [source: wiki/raw/sessions/2026-06-17-personal-harness-pi-removal.md#durable-facts]. The historical harness was repo-local; it did not edit global Pi settings or target package manifests [source: .rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md#profile-metadata].

## Selected posture

- Fast touched-file syntax checks are blocking after writes for Python (`python3 -m py_compile`), JSON (`jq .`), JavaScript/MJS/CJS (`node --check`), and shell (`bash -n`) [source: .rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md#syntax-check-commands].
- Automatic formatters are skipped because the repo has no declared formatter contract and automatic rewrites would be surprising [source: .rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md#formatter-commands].
- Python Ruff lint is advisory after writes; frontend lint is not selected as an afterWrite gate [source: .rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md#lint-commands].
- Project checks are advisory: `git diff --check` runs before git attempts; `pnpm exec tsc --noEmit` runs at agent end for frontend touches and cannot block by Pi event semantics; `uv run pytest -q` is manual-only to avoid slow git attempts [source: .rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md#project-check-commands].
- Playwright e2e is manual-only because it is expensive and the current frontend e2e setup can affect `.next` [source: .rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md#scenario-check-commands]; see the deploy hazard page for context [source: wiki/analyses/podium-frontend-deploy-cosmetics.md#second-trigger-playwright-e2e-clobbers-the-live-next].

## Safety blockers

The generated extension blocks or warns on deterministic local surfaces: `.env*` writes, read-tool env/secret reads, bash shell reader secret reads, generated/vendor/runtime writes, live service `systemctl` mutations, unit-file touches, Plane API mutations, DB/log deletion, recursive root/current-directory deletion, Alembic downgrades, live Podium skill refresh without `--dry-run`, and frontend build/start commands outside the deploy flow [source: .rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md#safety-rules]. The source evidence is the existing live-infra safety policy in `CLAUDE.md` and the operational wiki [source: wiki/raw/sessions/2026-06-12-personal-harness-pi.md#evidence].

## Guidance mode

Guidance is reference-mode only. `guidanceFiles` is empty in the generated profile, and architecture references point at `CONTEXT.md`, wiki index/routing, Podium docs, ADR-0005, ADR-0006, the test index, and the frontend deploy hazard page [source: wiki/raw/sessions/2026-06-12-personal-harness-pi.md#decisions]. This avoids injecting large wiki or runbook contents into every prompt while keeping paths discoverable.

## Verification

Verification passed for generated marker/default export checks, offline Pi load smoke, isolated offline Pi load smoke, syntax dry checks, mocked safety dry checks, mocked project/scenario trigger dry checks, targetRepo root-resolution dry checks, and reference-guidance checks [source: wiki/raw/sessions/2026-06-12-personal-harness-pi.md#durable-facts].

## Follow-up

The project-local extension has been deleted. Current already-running Pi sessions may still have it loaded until `/reload` or process restart; already-injected guidance messages do not disappear retroactively [source: wiki/raw/sessions/2026-06-17-personal-harness-pi-removal.md#durable-facts]. To restore the harness, regenerate `.pi/extensions/personal-harness.ts` from the retained profile source [source: wiki/raw/sessions/2026-06-17-personal-harness-pi-removal.md#scope].

## Claims

C-0121 and C-0122 in [CLAIMS.md](../CLAIMS.md) are superseded by C-0237.
