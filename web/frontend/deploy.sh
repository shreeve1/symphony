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

if ! git diff --quiet HEAD -- tsconfig.json; then
	echo "Refusing deploy: tsconfig.json has pre-existing changes" >&2
	exit 1
fi

echo "==> Building into $STAGING (live .next untouched)"
# Bust Next's persistent cache so a successful deploy cannot reuse stale modules.
rm -rf .next/cache "$STAGING"
trap 'git checkout -- tsconfig.json' EXIT
NEXT_DIST_DIR="$STAGING" pnpm build

# `next build` rewrites tsconfig.json (reformat + a transient staging-types
# include). That is machine noise, not a source change — drop it so deploys
# leave the tree clean, including when the build fails.
git checkout -- tsconfig.json
trap - EXIT

echo "==> Swapping build and restarting $SERVICE"
if ! sudo systemctl stop "$SERVICE"; then
	echo "Stop failed; restarting the untouched current build" >&2
	sudo systemctl restart "$SERVICE"
	systemctl is-active --quiet "$SERVICE"
	exit 1
fi
for _ in {1..20}; do
	STATE="$(systemctl is-active "$SERVICE" || true)"
	[[ "$STATE" != deactivating ]] && break
	sleep 1
done
if [[ "$STATE" != inactive && "$STATE" != failed ]]; then
	echo "Stop did not settle in 20s; restarting the untouched current build" >&2
	sudo systemctl restart "$SERVICE"
	systemctl is-active --quiet "$SERVICE"
	exit 1
fi
rm -rf .next.prev
mv .next .next.prev 2>/dev/null || true
mv "$STAGING" .next
sudo systemctl start "$SERVICE"

echo "==> Verifying"
sleep 3
systemctl is-active "$SERVICE"
STATUS="$(curl -fsS -o /dev/null -w '%{http_code}' "http://${HOST}:${PORT}/")"
[ "$STATUS" = 200 ]
echo "root=$STATUS"
echo "==> Done. Rollback: mv .next .next.bad && mv .next.prev .next && sudo systemctl restart $SERVICE"
