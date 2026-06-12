---
title: Pi personal harness profile
type: analysis
status: promoted
created: 2026-06-12
updated: 2026-06-12
sources:
  - wiki/raw/sessions/2026-06-12-personal-harness-pi.md
  - .rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md
  - .pi/extensions/personal-harness.ts
confidence: high
tags: [pi, harness, validation, safety, tooling]
---

# Pi personal harness profile

Symphony now has a project-local Pi personal harness generated at `.pi/extensions/personal-harness.ts`, sourced from `.rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md` [source: wiki/raw/sessions/2026-06-12-personal-harness-pi.md#durable-facts]. The harness is repo-local; it does not edit global Pi settings or target package manifests [source: .rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md#profile-metadata].

## Selected posture

- Fast touched-file syntax checks are blocking after writes for Python (`python3 -m py_compile`), JSON (`jq .`), JavaScript/MJS/CJS (`node --check`), and shell (`bash -n`) [source: .rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md#syntax-check-commands].
- Automatic formatters are skipped because the repo has no declared formatter contract and automatic rewrites would be surprising [source: .rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md#formatter-commands].
- Python Ruff lint is advisory after writes; frontend lint is not selected as an afterWrite gate [source: .rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md#lint-commands].
- Project checks are advisory: `python3 -m pytest -q` and `git diff --check` run before git attempts; `pnpm exec tsc --noEmit` runs at agent end for frontend touches and cannot block by Pi event semantics [source: .rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md#project-check-commands].
- Playwright e2e is manual-only because it is expensive and the current frontend e2e setup can affect `.next` [source: .rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md#scenario-check-commands]; see the deploy hazard page for context [source: wiki/analyses/podium-frontend-deploy-cosmetics.md#second-trigger-playwright-e2e-clobbers-the-live-next].

## Safety blockers

The generated extension blocks or warns on deterministic local surfaces: `.env*` writes, env/secret reads, generated/vendor/runtime writes, live service `systemctl` mutations, unit-file touches, Plane API mutations, DB/log deletion, recursive root/current-directory deletion, Alembic downgrades, live Podium skill refresh without `--dry-run`, and frontend build/start commands outside the deploy flow [source: .rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md#safety-rules]. The source evidence is the existing live-infra safety policy in `CLAUDE.md` and the operational wiki [source: wiki/raw/sessions/2026-06-12-personal-harness-pi.md#evidence].

## Guidance mode

Guidance is reference-mode only. `guidanceFiles` is empty in the generated profile, and architecture references point at `CONTEXT.md`, wiki index/routing, Podium docs, ADR-0005, ADR-0006, the test index, and the frontend deploy hazard page [source: wiki/raw/sessions/2026-06-12-personal-harness-pi.md#decisions]. This avoids injecting large wiki or runbook contents into every prompt while keeping paths discoverable.

## Verification

Verification passed for generated marker/default export checks, offline Pi load smoke, isolated offline Pi load smoke, syntax dry checks, safety dry checks, project/scenario source dry checks, and reference-guidance checks [source: wiki/raw/sessions/2026-06-12-personal-harness-pi.md#durable-facts].

## Follow-up

Run `/reload` inside Pi from `/home/james/symphony` to activate the extension. If the harness is too aggressive, edit the Harness Profile artifact first and regenerate, or delete `.pi/extensions/personal-harness.ts` [source: wiki/raw/sessions/2026-06-12-personal-harness-pi.md#open-questions-and-follow-ups].

## Claims

C-0121 and C-0122 in [CLAIMS.md](../CLAIMS.md).
