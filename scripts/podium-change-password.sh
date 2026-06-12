#!/usr/bin/env bash
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"

cat <<'MSG'
Podium password rotation helper

This generates a new bcrypt hash for the shared Podium password.
It does not edit /home/james/symphony-host.env and does not restart services.
MSG

uv run python -m web.cli.podium set-password

cat <<'MSG'

Next steps:
1. Copy the PODIUM_PASSWORD_HASH=... line above.
2. Edit the host env file:

   sudoedit /home/james/symphony-host.env

3. Replace only PODIUM_PASSWORD_HASH=...
4. Restart and verify the API:

   sudo systemctl restart podium-api.service
   systemctl status podium-api.service --no-pager
   curl -s http://127.0.0.1:8090/api/health

Existing browser sessions remain valid. To force everyone to log in again,
also rotate PODIUM_SESSION_SECRET in /home/james/symphony-host.env:

   openssl rand -hex 32

Set PODIUM_SESSION_SECRET to the printed value, then restart podium-api.service.
MSG
