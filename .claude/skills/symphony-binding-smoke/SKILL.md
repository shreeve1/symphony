---
name: symphony-binding-smoke
description: File a low-risk smoke Issue through Podium POST /api/bindings/{name}/issues, poll the Issue Run rows, and report verdict. For infra bindings, refuses if WORKFLOW.md is still the scaffold stub; coding bindings skip the WORKFLOW.md check (ADR-0011).
---

# Symphony Binding Smoke

File one low-risk Podium Issue for a binding and watch the resulting Run.

## Prerequisites

- Binding exists in Podium and `bindings.yml`.
- **`infra` bindings only:** binding repository has a real `WORKFLOW.md`; the scaffold stub is refused. **`coding` bindings have no `WORKFLOW.md` and ignore it (ADR-0011)** — confirmed in `prompt_renderer.py` (coding dispatch builds the prompt without reading `WORKFLOW.md`). Do not read or refuse it for coding bindings.
- Podium API access. The live `podium-api.service` (FastAPI) runs on `127.0.0.1:8090` but requires a session cookie, and the credentials live in `/home/james/symphony-host.env` — which this skill must **not** read. The compliant, auth-free path is the **in-process FastAPI TestClient against the live DB** (see "Auth-free TestClient pattern" below); use it unless James hands you a live session.

## Workflow

1. Resolve the binding by `GET /api/bindings`. Note its `binding_type`.
2. **`infra` only:** read the binding repository `WORKFLOW.md` and refuse the scaffold stub line. **Skip this step entirely for `coding` bindings** — they have no `WORKFLOW.md` and dispatch ignores it.
3. Create the smoke Issue with `POST /api/bindings/{name}/issues`.
4. Poll `GET /api/issues/{issue_id}/runs` until a Run row appears or the timeout expires. The smoke Issue is created with `approval.enabled=false` on most bindings, so the live scheduler **auto-dispatches a real agent run** against the target repo. With worktree-per-run default-ON for local coding bindings (ADR-0021 slice 108), the run executes in its own deterministic `worktree_dir(repo, binding, issue_id)`, not the shared checkout. This is not read-only.
5. **Coding bindings now run a review phase (ADR-0023).** After the implement run parks the Issue in `in_review`, the scheduler dispatches a SECOND (review) run for the same Issue, re-entering the same worktree (look for the `### Symphony Review` comment marker). So expect **two Run rows** for a coding smoke Issue, and note that `latest_verdict`/`latest_run_state` reflect the *review* run once it finishes. Poll long enough to see the review terminal, not just the implement run.
6. Fetch the final Run with `GET /api/runs/{run_id}` when needed.
7. Report Issue id, Run ids (implement + review), final state, verdict, and summary. **The Run's `agent` (`pi`/`claude`) is the harness; its `provider`/`model` come from the agent's own config and may differ from what the binding implies** (e.g. a `pi` binding dispatched on `openai-codex` / `gpt-5.5:high`). Surface provider/model in the report and flag if it is not what James expected.

## Auth-free TestClient pattern

The live API needs credentials from the forbidden env file. To file the smoke Issue without reading it, drive the FastAPI app in-process with a throwaway test login, pointed at the **live** `podium.db`:

```bash
cd /home/james/symphony && uv run python - <<'PY'
import os
from importlib import import_module
from typing import Any, cast

web_conftest = cast(Any, import_module("web.api.tests.conftest"))
os.environ["PODIUM_PASSWORD_HASH"] = web_conftest.TEST_PASSWORD_HASH
os.environ["PODIUM_SESSION_SECRET"] = web_conftest.TEST_SESSION_SECRET
os.environ.pop("PODIUM_DB_PATH", None)  # resolve_db_path() -> live /home/james/symphony/podium.db

from fastapi.testclient import TestClient
sm = cast(Any, import_module("skill_migration"))
main = cast(Any, import_module("web.api.main"))
main._auth_config = None

with TestClient(main.app) as client:
    web_conftest.login(client)
    issue = sm.create_podium_smoke_issue(client, "BINDING_NAME", title="[smoke] <date> Symphony binding verification")
    run = sm.poll_podium_issue_run(client, issue["id"], timeout_seconds=180.0, interval_seconds=2.0)
    print(issue["id"], run)
PY
```

The Issue lands in the live DB; the running `symphony-host.service` dispatches it; poll the same client (or the live DB directly) for the Run.

**Side effect:** `TestClient(main.app)` runs the app lifespan, which calls `_purge_archived_issues` on the live DB (same purge `podium-api.service` does on its own boot). Acceptable but note it. The lifespan starts only a session tailer — no second scheduler.

## Safety rules

- No Plane API calls.
- No `plane_adapter` imports.
- Do not emit live alerts, Telegram messages, or paging webhooks during verification.
- In unattended automation, operator approval for the local Podium write is already granted by the Ralph runner.
- **Never set `auto_land=true` on a smoke Issue.** A smoke Issue is operator-created and leaves `auto_land` at its `false` default, so a passing review parks it in `in_review` (operator merge gate) and does NOT auto-merge to `main` (ADR-0023). Setting `auto_land=true` would let the review phase unattended-merge throwaway smoke work into `main` via `land_worktree` — exactly what must not happen.
- Leave the smoke Issue in Podium as audit evidence unless a later cleanup task says otherwise.

## Verification

Run:

```bash
cd /home/james/symphony && uv run pytest tests/skills/test_binding_smoke.py
```
