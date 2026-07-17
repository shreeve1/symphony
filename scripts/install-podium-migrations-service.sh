#!/usr/bin/env bash
# Install podium-migrations.service (auto-runs `alembic upgrade head` on boot
# and before podium-api.service). Idempotent: re-running reconverges.
#
# Why: when migrations are checked in but never applied against the live
# podium.db, podium-api crash-loops on startup with "schema drift: missing
# columns". Operators have hit this by treating it as a password issue
# (the symptom is /api/auth/login returning 500). This unit moves the
# migration step into the boot path so the failure mode is structurally
# impossible after every OS reboot.
#
# See: wiki/analyses/podium-018-auth.md and the post-deploy runbook.
set -euo pipefail

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [[ "$(id -u)" -ne 0 ]]; then
  echo "must run as root (sudo)" >&2
  exit 1
fi
if [[ ! -x "$repo_root/.venv/bin/alembic" ]]; then
  echo "expected alembic at $repo_root/.venv/bin/alembic" >&2
  exit 1
fi

systemctl_owners=james
host_env=/home/james/symphony-host.env

# 1. The oneshot migrations unit.
cat > /etc/systemd/system/podium-migrations.service <<EOF
[Unit]
Description=Podium Alembic migrations
Documentation=file://$repo_root/web/api/migrations
# Run before the API so ensure_schema never sees a missing column on a fresh
# DB. Skipped OnFailure= here: podium-api's existing alert path covers the
# common case (failed migration -> API crash on ensure_schema -> telegram
# alert). Two alerts for one root cause would just be noise.
Before=podium-api.service
After=network.target

[Service]
Type=oneshot
RemainAfterExit=yes
User=$systemctl_owners
Group=$systemctl_owners
WorkingDirectory=$repo_root
EnvironmentFile=$host_env
# Call alembic inside the project venv directly. systemctl strips PATH, so
# \`uv\` (at /home/james/.local/bin) is unreachable; the venv-resident
# alembic script invokes $repo_root/.venv/bin/python3 itself.
ExecStart=$repo_root/.venv/bin/alembic upgrade head
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# 2. The drop-in pulling migrations into podium-api's boot.
mkdir -p /etc/systemd/system/podium-api.service.d
cat > /etc/systemd/system/podium-api.service.d/migrations.conf <<EOF
[Unit]
Wants=podium-migrations.service
After=podium-migrations.service
EOF

# 3. Reload systemd to pick up the new files.
systemctl daemon-reload

# 4. Enable so multi-user.target pulls the migrations unit in on boot.
systemctl enable podium-migrations.service >/dev/null

cat <<MSG
Installed:
  /etc/systemd/system/podium-migrations.service
  /etc/systemd/system/podium-api.service.d/migrations.conf

Next step: run migrations and start the API:
  sudo systemctl start podium-migrations.service
  sudo systemctl restart podium-api.service
  systemctl is-active podium-migrations.service
  systemctl is-active podium-api.service
  curl -s http://127.0.0.1:8090/api/health

Both units are also enabled, so the next OS reboot will run
\`alembic upgrade head\` automatically before starting podium-api.
Re-running this script is safe; it overwrites the units and
re-enables, but does not start or restart any service.
MSG
