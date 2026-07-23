# Session Capture: Herdr frontier gate headless pnpm hardening

- Date: 2026-07-22
- Purpose: Preserve why the Symphony frontier merge gate sets `CI=true` for the frontend TypeScript check.
- Scope: Issue #33 recovery, the verified headless gate failure mode, the one-line fix, and post-fix verification.

## Durable Facts

- The project frontier merge gate runs the full Python suite before the frontend TypeScript check: `uv run pytest -q && (cd web/frontend && CI=true pnpm exec tsc --noEmit)`. — Evidence: `.herdr-frontier-gate`; commit `839699cb3154b96207702aacef1e1ce31a6f38e2`.
- With pnpm v11, the pre-fix `pnpm exec tsc --noEmit` path attempted an interactive modules-directory purge when dependency state required recreation. In the headless non-TTY frontier runner, that prompt could not be answered and pnpm aborted instead of running TypeScript. — Evidence: observed frontier gate output during the issue #33 recovery session; pre-fix command in parent of commit `839699c`.
- Setting `CI=true` only around the pnpm command selects pnpm's noninteractive CI behavior while preserving both existing checks. After the change, TypeScript passed and the complete gate passed with `1693 passed, 2 skipped`. — Evidence: `.herdr-frontier-gate`; post-fix commands `cd web/frontend && CI=true pnpm exec tsc --noEmit` and `.herdr-frontier-gate`.
- The fix was committed as `839699c` (`fix: make frontier typecheck noninteractive`) and pushed to `origin/main`. — Evidence: `git show 839699c`; `git rev-parse main origin/main`.

## Decisions

- Keep the frontier gate strict and make only pnpm noninteractive; do not remove or bypass the frontend typecheck. — Evidence: operator-approved follow-up and commit `839699c`.
- Keep Playwright outside the per-merge frontier gate because it is heavier and requires a dev server; its existing separate configuration remains authoritative. — Evidence: comments in `.herdr-frontier-gate`.

## Evidence

- `.herdr-frontier-gate` — current command and deliberate scope.
- Commit `839699cb3154b96207702aacef1e1ce31a6f38e2` — exact one-line change from the interactive-risk command to the headless-safe command.
- GitHub issue `shreeve1/symphony#33` — recovered implementation that exposed the merge-gate failure mode; issue is closed after verification and landing.

## Exclusions

- No credentials, environment-file contents, private issue content, or raw transcript were captured.
- Temporary reviewer scaffolding and issue #34 artifacts are not part of this operational rule.
- The pnpm behavior is scoped to the observed v11 modules-recreation path; this capture does not claim every pnpm invocation prompts.

## Open Questions And Follow-Ups

- None. Keep `CI=true` on the pnpm command unless the frontier runner later supplies an equivalent noninteractive environment globally.
