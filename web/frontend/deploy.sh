#!/usr/bin/env bash
# Atomic deploy for the Podium frontend (podium-web.service, `next start`).
#
# Why this exists: `next build` overwrites .next in place. The running server
# keeps serving the old in-memory HTML while the on-disk chunk hashes change,
# so any request in that window 400s with the wrong MIME type. This script
# builds into a staging dir (live site untouched), then does a fast
# stop -> swap -> start so there is no mismatch window — only ~3s of downtime.
#
# The previous build is kept at .next.prev for a quick manual rollback.
set -euo pipefail

cd "$(dirname "$0")"

SERVICE=podium-web.service
HOST="${HOST:-10.20.20.16}"
PORT=8091
STAGING=.next.staging

echo "==> Building into $STAGING (live .next untouched)"
rm -rf "$STAGING"
NEXT_DIST_DIR="$STAGING" pnpm build

# `next build` rewrites tsconfig.json (reformat + a transient staging-types
# include). That is machine noise, not a source change — drop it so deploys
# leave the tree clean.
git checkout -- tsconfig.json 2>/dev/null || true

echo "==> Swapping build and restarting $SERVICE"
sudo systemctl stop "$SERVICE"
rm -rf .next.prev
mv .next .next.prev 2>/dev/null || true
mv "$STAGING" .next
sudo systemctl start "$SERVICE"

echo "==> Verifying"
sleep 3
systemctl is-active "$SERVICE"
curl -sS -o /dev/null -w "root=%{http_code}\n" "http://${HOST}:${PORT}/"
echo "==> Done. Rollback: mv .next .next.bad && mv .next.prev .next && sudo systemctl restart $SERVICE"
