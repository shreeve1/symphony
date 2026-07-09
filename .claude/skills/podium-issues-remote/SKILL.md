---
disable-model-invocation: true
name: podium-issues-remote
description: "Slice an approved plan into Podium issues from a remote binding over the dispatch reverse tunnel. Unattended: POSTs slices to the Podium API (no DB, no bindings.yml, no operator approval). Operator reviews the board afterward."
---

# Podium Issues (Remote)

Turn an approved plan into Podium issues from an **unattended agent running a
remote binding**, without leaving Podium (ADR-0036). Unlike the on-box
`podium-issues` skill, this one has no `/var/lib/symphony/podium.db` and no
`bindings.yml` — it POSTs slices to this Symphony's Podium API over the SSH
reverse tunnel the harness opens for `podium-issues-remote` runs.

## When to use

You are running as a dispatched Podium slice against a remote binding whose
issue set `preferred_skill=podium-issues-remote`. There is **no operator
approval step** (you run unattended); the operator reviews the created issues in
the board afterward.

## Prerequisites (harness-provided)

The dispatch harness exports these into your env — do not set them yourself:

- `PODIUM_BASE_URL` — always `http://127.0.0.1:<port>` (the reverse tunnel).
- `PODIUM_API_TOKEN` — the global Podium bearer token.
- `SYMPHONY_BINDING_NAME` — the binding to create issues against.

Python 3 must be on the remote PATH (true for all current remote bindings). The
bundled client is stdlib-only, so no venv is required.

## Authoring rules

Draft vertical tracer-bullet slices using the `/to-issues` rules:

- each slice is end-to-end and independently useful;
- acceptance criteria are objective;
- verification is a repo-correct runnable command, not prose — a single line
  wrapped in a single pair of single backticks (`` ` ``), never a fenced code
  block; slicer-created issues are stamped `auto_land=true`, and the review
  backstop re-runs this command;
  - **Refactor/move slices must use the full test suite**
    (`.venv/bin/python -m pytest -q`). Relocating a function into a different
    module can silently break monkeypatches or imports in *any* test file —
    scoped per-file verification will miss regressions in sibling suites.
    Scoped verification is fine for additive slices that do not touch existing
    call-site modules.
- blockers are explicit (`blocked_by` lists other slice keys);
- `locks` labels identify resources that must not co-run.
- **Migration lock (C-0335):** any slice that creates an Alembic revision under
  `web/api/migrations/` MUST carry `locks: [migrations]`. Parallel slices
  branching a new revision from the same parent produce two Alembic heads. Use
  the single coarse `migrations` lock on *every* migration-creating slice — not
  a per-file lock — so dispatch serializes them.

### Model / agent — omit by default

Unlike the local skill (which validates each slice `model` against `models.yml`
at create time), the remote client **cannot** validate models — it has no
`models.yml`, the API does not validate models on create, and the
`symphony-models` skill is not shipped to the remote. A bad model name is caught
only at dispatch (a broken `todo` row), not at create.

Therefore **omit `model`/`agent` entirely** so issues inherit the binding
default — unless the operator named an exact catalog model in the plan.

## Slice spec (JSON)

Write a JSON spec (not YAML — the remote has no `pyyaml`). Example
`/tmp/podium-slices.json`:

```json
{
  "slices": [
    {
      "key": "schema",
      "title": "Add dependency columns",
      "description": "Add the columns and read-path coercion.",
      "acceptance": ["issue rows expose blocked_by and locks as typed lists"],
      "verification": "uv run pytest web/api/tests/test_alembic_baseline.py -q",
      "locks": ["schema"]
    },
    {
      "key": "api",
      "title": "Carry dependencies through API",
      "description": "Create/patch accepts blocked_by and locks.",
      "acceptance": ["create response includes blocked_by and locks"],
      "verification": "uv run pytest web/api/tests/test_issue_create.py -q",
      "blocked_by": ["schema"],
      "locks": ["web-api"]
    }
  ]
}
```

Each slice: `key`, `title`, `description`, `acceptance[]`, `verification` are
required; `blocked_by[]` (keys of other slices), `locks[]`, and optional
`priority` are honored. Omit `model`/`agent` per the rule above.

## Workflow

1. Read the plan from the conversation or the file the operator names.
2. Draft the slices per the authoring rules above.
3. Write the JSON spec (e.g. `/tmp/podium-slices.json`).
4. Dry-run first (posts nothing, prints planned payloads):

   ```bash
   python3 create_issues.py /tmp/podium-slices.json --dry-run
   ```

5. Create live (POSTs blockers first, threads returned ids into dependents'
   `blocked_by`):

   ```bash
   python3 create_issues.py /tmp/podium-slices.json
   ```

`create_issues.py` sits next to this SKILL.md (shipped together over SSH). Run
it from the skill directory, or pass its absolute path.

## Safety rules

- The live command creates `todo` Podium issues with `auto_land=true` and
  `worktree_active=true`; they may become dispatchable on the next scheduler
  poll. Dry-run first.
- Dependencies are created blocker-first; dependent `blocked_by` uses the real
  Podium ids returned by earlier inserts.
- The client exits nonzero and surfaces the API error body on any HTTP 4xx/5xx.
- No operator approval gate — the operator reviews the board after you finish.
