---
title: Podium #018 Shared-Password Auth
kind: analysis
status: promoted
created: 2026-06-11
updated: 2026-06-12
sources:
  - web/api/auth.py
  - web/api/main.py
  - web/api/tests/test_auth.py
  - web/cli/podium.py
  - scripts/podium-change-password.sh
  - web/README.md
  - web/cli/tests/test_skills_refresh.py
  - web/frontend/components/AppShell.tsx
  - web/frontend/app/login/page.tsx
  - web/frontend/tests/auth.spec.ts
confidence: high
tags: [podium, auth, frontend, api, cli]
---

# Podium #018 Shared-Password Auth

## Summary

Podium now has single-user shared-password authentication backed by bcrypt. The API loads `PODIUM_PASSWORD_HASH` and `PODIUM_SESSION_SECRET` from environment, with read-only `.env` fallback for dev, and fails startup when either is missing [source: web/api/auth.py] [source: web/api/main.py]. HTTP middleware protects `/api/*` except `/api/auth/*` and `/api/health`; the WebSocket endpoint also validates the signed `podium_session` cookie before accepting [source: web/api/main.py].

## Backend Contract

- `POST /api/auth/login` checks the submitted password against the bcrypt hash, sets an httpOnly `podium_session` cookie, `SameSite=Lax`, `Max-Age=86400`, and clears the IP failure bucket after success [source: web/api/main.py] [source: web/api/auth.py].
- Failed logins sleep 250ms before 401; five failures per IP per minute trigger 429 with `Retry-After: 60` [source: web/api/main.py] [source: web/api/auth.py].
- `POST /api/auth/logout` deletes the session cookie; `GET /api/auth/whoami` returns 200 only when the cookie verifies [source: web/api/main.py].
- `/api/health` remains public, preserving health-check behavior for the isolated API port [source: web/api/main.py].

## Frontend Contract

`AppShell` checks `/api/auth/whoami` for every non-login route; unauthenticated users are redirected to `/login`. Authenticated users get the normal sidebar/header shell plus a Logout button that calls `/api/auth/logout` and redirects back to `/login` [source: web/frontend/components/AppShell.tsx]. The `/login` page posts the shared password to `/api/auth/login` and returns to `/` on success [source: web/frontend/app/login/page.tsx].

Frontend e2e tests now authenticate through `page.request.post('/api/auth/login')` in the shared fixture, while `auth.spec.ts` owns the unauthenticated redirect + login coverage [source: web/frontend/tests/fixtures.ts] [source: web/frontend/tests/auth.spec.ts].

## CLI Contract

`python -m web.cli.podium set-password` reads and confirms a password, prints `PODIUM_PASSWORD_HASH=<bcrypt>` to stdout, and does not write secrets to disk. Operator remains responsible for pasting the hash into the host env file [source: web/cli/podium.py] [source: web/cli/tests/test_skills_refresh.py].

## Operational Helper

`web/README.md` now documents password rotation under "Change Podium password": run the helper or manual CLI, paste only `PODIUM_PASSWORD_HASH=...` into `/home/james/symphony-host.env`, restart `podium-api.service`, and health-check `127.0.0.1:8090` [source: web/README.md]. The helper `scripts/podium-change-password.sh` wraps `uv run python -m web.cli.podium set-password`, prints next steps, and intentionally does not edit the env file or restart services [source: scripts/podium-change-password.sh]. Existing signed sessions remain valid after changing only the password hash; rotating `PODIUM_SESSION_SECRET` is the documented force-logout path [source: web/README.md] [source: scripts/podium-change-password.sh].

## Verification Evidence

Automated coverage includes backend auth behavior, missing-secret startup failure, public health, CLI stdout-only hash generation, and Playwright redirect/login/board rendering [source: web/api/tests/test_auth.py] [source: web/cli/tests/test_skills_refresh.py] [source: web/frontend/tests/auth.spec.ts]. Ralph verification passed `uv run pytest`, `pnpm test:e2e`, `pnpm exec tsc --noEmit`, and touched-file LSP diagnostics with no critical errors. The password helper was syntax-checked with `bash -n scripts/podium-change-password.sh` and the docs/script diff passed `git diff --check` [source: scripts/podium-change-password.sh].

## Notes For Future Slices

- Podium WebSocket clients must carry the same session cookie as HTTP API requests [source: web/api/main.py].
- Frontend tests that create extra browser contexts must authenticate those pages explicitly; the shared fixture authenticates only the default page [source: web/frontend/tests/live-sync.spec.ts].
- `pnpm lint` still prompts because ESLint is not configured; use `pnpm exec tsc --noEmit` as the frontend typecheck until a lint config lands.
