#!/usr/bin/env bash
# Restore a Checkorca-CE backup made by scripts/backup.sh (phase C10-B,
# docs/backup-restore.md):
#
#   bash scripts/restore.sh checkorca-backup-YYYYmmdd-HHMMSS.dump
#
# Stops the app (the web and worker containers), replaces the database
# content with the dump's, and starts the app again: on start the web
# container runs the migrations, so a restored schema moves forward to this
# image's revision (the one-release-back rule of docs/upgrade.md). The
# environment of .env is untouched: the same SECRET_KEY and FERNET_KEY must
# still be set, or sign-in sessions and stored credentials cannot be read.
set -euo pipefail

cd "$(dirname "$0")/.."
dump="${1:-}"
if [[ -z "${dump}" || ! -f "${dump}" ]]; then
  echo "restore: name the backup file: bash scripts/restore.sh <file.dump>" >&2
  exit 1
fi
echo "restore: stopping the app"
docker compose stop web worker > /dev/null
echo "restore: loading ${dump} into the database"
docker compose exec -T db pg_restore --clean --if-exists --no-owner --dbname=checkorca < "${dump}"
echo "restore: starting the app (the web container runs the migrations)"
docker compose up -d --wait
echo "restore: open /healthz and /readyz, sign in, and check the data (docs/backup-restore.md)."
