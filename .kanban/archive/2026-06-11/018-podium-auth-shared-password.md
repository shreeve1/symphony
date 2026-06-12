---
id: 018
title: Podium auth — bcrypt shared password + localhost binding
status: done
blocked_by: [012a]
parent: null
priority: 0
created: 2026-06-10
updated: 2026-06-11
actor: ralph
---

## What to build

Gate Podium behind a single bcrypt-hashed shared password (single-user
system per ADR-0005). Network exposure is bounded by `127.0.0.1` binding
already set in S012; this slice adds the application-level check.

Backend:

- Read `PODIUM_PASSWORD_HASH` from environment at startup (sourced from
  `/home/james/symphony-host.env` when running under systemd; from a `.env`
  file for dev).
- `POST /api/auth/login` — body `{"password": "..."}`. On match, sets a
  signed httpOnly session cookie (`podium_session`, `SameSite=Lax`,
  `Max-Age=86400`). On mismatch, sleeps 250ms and returns 401.
- `POST /api/auth/logout` — clears the cookie.
- `GET /api/auth/whoami` — 200 if authenticated, 401 otherwise.
- Middleware enforces auth on all `/api/*` except `/api/auth/*` and
  `/api/health`.
- Session signing key in `PODIUM_SESSION_SECRET` (env). Startup error if
  unset.
- Rate limit: 5 failed attempts per IP per minute → 429 with
  `Retry-After: 60`.

Frontend:

- Unauthenticated requests trigger redirect to `/login`.
- `/login` page: password input + submit. On success, redirect to `/`.
- `/logout` button in header clears the session.

CLI helper:

- `python -m web.cli.podium set-password` prompts for password, writes
  `PODIUM_PASSWORD_HASH=<bcrypt>` to stdout for the operator to paste into
  `symphony-host.env`. Never writes secrets to disk itself.

## Acceptance criteria

- [x] `web/api/tests/test_auth.py` covers: correct password → 200 + cookie; wrong password → 401 with 250ms+ latency; missing cookie on protected route → 401; logout clears cookie; rate limit kicks in after 5 failures.
- [x] `PODIUM_SESSION_SECRET` unset at startup → app exits 1 with a clear error.
- [x] `/api/health` accessible without auth.
- [x] Playwright `auth.spec.ts`: visit `/`, redirected to `/login`, log in with seeded password, board renders.
- [x] `python -m web.cli.podium set-password` writes hash to stdout only; verify by piping to `/dev/null` and asserting nothing in `~/`.
- [x] Both ports still bind `127.0.0.1` (no regression).

## Verification

```
cd /home/james/symphony && uv run pytest && \
cd web/frontend && pnpm test:e2e
```

## Implementation Notes

Added bcrypt-backed Podium auth with signed `podium_session` cookies, failed-login rate limiting, `/api/auth/*` endpoints, API/WS auth guards, frontend login/logout flow, and `python -m web.cli.podium set-password` helper. Existing e2e specs authenticate through the login endpoint; `auth.spec.ts` covers the unauthenticated redirect and login path. Verification passed with `uv run pytest`, `pnpm test:e2e`, `pnpm exec tsc --noEmit`, and touched-file LSP diagnostics had no critical errors.

## Blocked by

- #012
