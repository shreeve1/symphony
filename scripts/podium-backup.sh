#!/usr/bin/env bash
set -euo pipefail

REPO_ROOT=${REPO_ROOT:-/home/james/symphony}
BACKUP_DIR=${BACKUP_DIR:-/backup}
RETENTION_DAYS=${RETENTION_DAYS:-14}

cd "$REPO_ROOT"

read -r DB_PATH RUN_ROOT < <(
  python3 - <<'PY'
from web.api.db import resolve_db_path, resolve_run_log_root
print(resolve_db_path(), resolve_run_log_root())
PY
)

if [[ ! -f "$DB_PATH" ]]; then
  echo "Podium database not found: $DB_PATH" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
STAMP=$(date +%F)
TMP_DB="$BACKUP_DIR/.podium-$STAMP.db.tmp"
FINAL_DB="$BACKUP_DIR/podium-$STAMP.db"

sqlite3 "$DB_PATH" ".backup '$TMP_DB'"
mv "$TMP_DB" "$FINAL_DB"

if [[ -d "$RUN_ROOT" ]]; then
  TMP_RUNS="$BACKUP_DIR/.podium-runs-$STAMP.tar.gz.tmp"
  FINAL_RUNS="$BACKUP_DIR/podium-runs-$STAMP.tar.gz"
  tar -C "$(dirname "$RUN_ROOT")" -czf "$TMP_RUNS" "$(basename "$RUN_ROOT")"
  mv "$TMP_RUNS" "$FINAL_RUNS"
fi

find "$BACKUP_DIR" -maxdepth 1 -type f -name 'podium-*.db' -mtime +"$RETENTION_DAYS" -delete
find "$BACKUP_DIR" -maxdepth 1 -type f -name 'podium-runs-*.tar.gz' -mtime +"$RETENTION_DAYS" -delete
