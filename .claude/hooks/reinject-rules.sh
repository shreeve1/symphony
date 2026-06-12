#!/usr/bin/env bash
# reinject-rules — re-print Symphony live-infra invariants after a context compaction.
# Single-quoted heredoc with a unique sentinel — no shell expansion, no early termination.
cat <<'REINJECT_EOF_SENTINEL'
Symphony is LIVE host-native infrastructure: symphony-host.service runs `python -m main` from this repo and polls Plane/Podium for Todo tickets. Honor these invariants:
- Treat as live infrastructure — edits affect a running scheduler.
- Never cat or print values from /home/james/symphony-host.env (mode 0600).
- Ask James before: systemctl restart/stop, unit edits, Plane/Podium API mutations, or smoke-ticket requeues — unless already approved for that exact action.
- Git remote uses the github-personal SSH host alias (authenticates as shreeve1), never default github.com.
- bindings.yml at the repo root is the source of truth for what dispatches where.
- Tests run under the uv venv: `uv run pytest` (system python3 lacks alembic and other deps).
REINJECT_EOF_SENTINEL
