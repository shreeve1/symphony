---
name: symphony-bindings-status
description: Read-only Podium status report using GET /api/bindings plus per-binding GET /api/bindings/{name}/issues, with journal context when available.
---

# Symphony Bindings Status

Report current Symphony bindings without mutating tracker state.

## Prerequisites

- Podium API is reachable on localhost or a FastAPI test client is available.
- Journal reads are optional; lack of journal access should degrade the journal columns only.

## Workflow

1. Fetch `GET /api/bindings`.
2. For each binding, fetch `GET /api/bindings/{name}/issues`.
3. Count non-`done` Issues as open.
4. Render the same table shape as the previous status skill: binding, project/display name, repo hint if known, last reconcile, last dispatch, open Issue count.
5. Add a **dispatch** column from `bindings.yml` (`/api/bindings` does not carry it): `default_agent` plus, for pi bindings, `pi_mode` (`rpc` or `one-shot`). `rpc` means pi dispatches via `pi --mode rpc` (ADR-0010, the live standard); a stray `one-shot` on an otherwise-rpc fleet is worth flagging.
6. If journal access is available, add the latest `reconcile_startup_*` and `dispatch_completed` evidence.
7. Optional, when explaining a coding binding's open count (ADR-0021/0023): an open Issue may be in `in_review` (awaiting the review phase or an operator merge) or a `todo` that is dependency/lock-gated and intentionally withheld — not stuck. If asked why an Issue isn't progressing, point at `/api/issues/{id}` (`state`, `blocked_by`, `locks`, `auto_land`) or hand off to `symphony-troubleshooter` rather than expanding this report.

## Safety rules

- Read-only by construction.
- No Plane API calls.
- No `plane_adapter` imports.
- Never invoke `systemctl restart`, `stop`, or `start`.
- Never read or print secret env files.

## Verification

Run:

```bash
cd /home/james/symphony && uv run pytest tests/skills/test_bindings_status.py
```
