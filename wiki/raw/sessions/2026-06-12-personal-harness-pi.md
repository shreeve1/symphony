# Session Capture: Personalize Pi Harness

- Date: 2026-06-12
- Purpose: Capture the durable repo-local Pi harness generated for Symphony.
- Scope: Harness profile artifact, generated Pi extension, selected check posture, safety blockers, and verification results. Full transcript excluded.

## Durable Facts

- Generated Harness Profile artifact: `.rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md` — Evidence: file written during this session.
- Generated project-local Pi extension: `.pi/extensions/personal-harness.ts` — Evidence: file written during this session and load-smoked.
- Selected harness posture: blocking afterWrite syntax checks for Python/JSON/JavaScript/shell; advisory Python Ruff lint; advisory deferred project checks for pytest, frontend `tsc --noEmit`, and `git diff --check`; manual Playwright listing only; safety blockers for secret paths, live service/systemd actions, Plane mutations, destructive DB/log deletion, Alembic downgrade, generated/vendor writes, and symlink escapes — Evidence: `.rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md`, `.pi/extensions/personal-harness.ts`.
- Verification passed: generated marker/default export checks; offline Pi load smoke; isolated offline Pi load smoke; syntax dry checks for `.py`, `.json`, `.mjs`, `.sh`; safety regex/path dry checks; source inspections for project-check trigger, manual scenario listing, and reference-mode guidance — Evidence: session commands `PI_OFFLINE=1 pi --no-session -e ./.pi/extensions/personal-harness.ts --list-models haiku`, `PI_OFFLINE=1 pi --no-session --no-extensions -e ./.pi/extensions/personal-harness.ts --list-models haiku`, temp-file syntax dry checks, and profile extraction checks.

## Decisions

- Project checks are advisory only; no blocking project checks were selected because no clean baseline proof was established during this skill run — Evidence: `.rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md#project-check-commands`.
- Guidance injection uses reference-mode architecture guidance and no full touched-file guidance files, to avoid dumping large wiki/ADR/runbook content into prompts — Evidence: `.pi/extensions/personal-harness.ts` profile literal (`guidanceFiles: []`, `architectureGuidance[].mode: "reference"`).
- Playwright e2e is listed as manual only because the frontend e2e config can overwrite `.next` in the live repo and is expensive — Evidence: `wiki/analyses/podium-frontend-deploy-cosmetics.md`, `.rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md#scenario-check-commands`.

## Evidence

- `.rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md` — profile source of truth and gap analysis.
- `.pi/extensions/personal-harness.ts` — generated Pi extension.
- `web/frontend/playwright.config.ts` and `wiki/analyses/podium-frontend-deploy-cosmetics.md` — frontend e2e/deploy hazard context.
- `CLAUDE.md` and `wiki/concepts/symphony-operations.md` — live-service and secret safety gates.

## Exclusions

- No secrets, credentials, tokens, `.env` contents, or `/home/james/symphony-host.env` contents captured.
- Full transcript excluded.
- Web-research details beyond selected posture excluded; primary repo profile remains the generator source of truth.

## Open Questions And Follow-Ups

- Run `/reload` inside Pi from `/home/james/symphony` to load the generated extension.
- If harness behavior is too aggressive, edit `.rpiv/artifacts/research/2026-06-12_13-25-38_personalize-harness-pi.md` first and regenerate, or delete `.pi/extensions/personal-harness.ts`.
