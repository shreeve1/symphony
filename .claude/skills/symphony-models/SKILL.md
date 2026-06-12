---
name: symphony-models
description: List, add, or remove entries in repo-root models.yml for the Podium Model dropdown. Reuses web.api.main _load_models/_validate_models for linting.
---

# Symphony Models Catalog Maintenance

Maintain the git-tracked `models.yml` catalog that feeds `/api/bindings/{name}/options` and the new-Issue Model dropdown.

## Prerequisites

- Run from `/home/james/symphony`.
- `models.yml` exists at the repo root.
- `web.api.main._load_models()` and `web.api.main._validate_models()` are the validation source of truth.

## Commands

### list

Show current models grouped by agent:

```bash
cd /home/james/symphony && uv run python - <<'PY'
from pathlib import Path
from collections import defaultdict
from web.api.main import _load_models

models = _load_models(Path('models.yml'))
by_agent = defaultdict(list)
for item in models:
    by_agent[item['agent']].append(item)
for agent in sorted(by_agent):
    print(f'{agent}:')
    for item in by_agent[agent]:
        details = []
        if item.get('provider'):
            details.append(f"provider={item['provider']}")
        if item.get('label'):
            details.append(f"label={item['label']}")
        suffix = f" ({', '.join(details)})" if details else ''
        print(f"  - {item['id']}{suffix}")
PY
```

### add

1. Edit `models.yml` and append one entry under `models:`:

   ```yaml
   - id: claude-example
     agent: claude
     label: Example
   ```

2. Required fields: `id`, `agent`.
3. Optional fields: `provider`, `label`.
4. `agent` must be `pi` or `claude`.
5. `id` must be unique.
6. Lint with the shared validator:

   ```bash
   cd /home/james/symphony && uv run python - <<'PY'
from pathlib import Path
from web.api.main import _load_models

models = _load_models(Path('models.yml'))
print(f'valid models.yml: {len(models)} models')
PY
   ```

### remove

1. Edit `models.yml` and delete the entry whose `id` matches the requested model.
2. Lint with the same shared validator command from `add`.
3. Confirm `/api/bindings/{name}/options` can still load the catalog by relying on the same `_load_models()` path used by the endpoint.

## Operator notes

- `models.yml` is git-tracked authored config. Commit intentional changes.
- `preferred_model` remains free text server-side. Unlisted models still dispatch; the catalog only improves dropdown discovery.
- Keep YAML stable and readable; do not sort or rewrite unrelated entries unless the requested edit requires it.

## Safety rules

- No service restart, start, stop, enable, or unit edit.
- No Plane API calls.
- No `.env` or `/home/james/symphony-host.env` reads.
- No secret printing.
- Do not edit Podium SQLite directly from this skill.

## Verification

Run:

```bash
cd /home/james/symphony && uv run pytest tests/skills/test_catalog_maintenance_skills.py
```
