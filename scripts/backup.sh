#!/usr/bin/env bash
# Backup of the Checkorca-CE database (phase C10-B, docs/backup-restore.md):
# one pg_dump in the custom format per run, written next to the project.
#
#   bash scripts/backup.sh [output file]
#
# Works against the Docker Compose install of README.md (the db service of
# docker-compose.yml). On another install run the same pg_dump against your
# own PostgreSQL; the dump names only this database.
#
# The dump holds the database, not the environment: the secrets of .env
# (SECRET_KEY, FERNET_KEY, and METRICS_TOKEN and EXTERNAL_HEARTBEAT_URL when
# set) are not in it and never printed. Keep them in your password manager,
# and keep every FERNET_KEY you ever used next to the backups
# (docs/auth.md, rotation), or the stored credentials of a restore cannot
# be read.
set -euo pipefail

cd "$(dirname "$0")/.."
when="$(date -u +%Y%m%d-%H%M%S)"
out="${1:-checkorca-backup-${when}.dump}"
if [[ -e "${out}" ]]; then
  echo "backup: ${out} already exists; give a new file name" >&2
  exit 1
fi
docker compose exec -T db pg_dump --format=custom checkorca > "${out}"
size="$(du -h "${out}" | cut -f1)"
echo "backup: wrote ${out} (${size}); keep the .env secrets and every old FERNET_KEY with it (docs/backup-restore.md)."
