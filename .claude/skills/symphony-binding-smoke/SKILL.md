---
name: symphony-binding-smoke
description: File a low-risk smoke Issue through Podium POST /api/bindings/{name}/issues, poll the Issue Run rows, and report verdict. Refuses if WORKFLOW.md is still the scaffold stub.
---

# Symphony Binding Smoke

File one low-risk Podium Issue for a binding and watch the resulting Run.

## Prerequisites

- Binding exists in Podium and `bindings.yml`.
- Binding repository has a real `WORKFLOW.md`; the scaffold stub is refused.
- Podium API is reachable on localhost or a FastAPI test client is available.

## Workflow

1. Resolve the binding by `GET /api/bindings`.
2. Read the binding repository `WORKFLOW.md` and refuse the scaffold stub line.
3. Create the smoke Issue with `POST /api/bindings/{name}/issues`.
4. Poll `GET /api/issues/{issue_id}/runs` until a Run row appears or the timeout expires.
5. Fetch the final Run with `GET /api/runs/{run_id}` when needed.
6. Report Issue id, Run id, state, verdict, and summary.

## Safety rules

- No Plane API calls.
- No `plane_adapter` imports.
- Do not emit live alerts, Telegram messages, or paging webhooks during verification.
- In unattended automation, operator approval for the local Podium write is already granted by the Ralph runner.
- Leave the smoke Issue in Podium as audit evidence unless a later cleanup task says otherwise.

## Verification

Run:

```bash
cd /home/james/symphony && uv run pytest tests/skills/test_binding_smoke.py
```
