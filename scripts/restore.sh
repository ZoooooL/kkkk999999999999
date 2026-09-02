#!/usr/bin/env bash
# Restore a backup created by scripts/backup.sh into this Docker stack.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

BACKUP_DIR=${1:-}
if [[ -z ${BACKUP_DIR} || ! -d ${BACKUP_DIR} ]]; then
  echo "Usage: $0 backups/YYYYMMDDTHHMMSSZ" >&2
  exit 1
fi
# shellcheck disable=SC1091
set -a
source .env
set +a

python3 scripts/render-odoo-conf.py
docker compose --env-file .env up -d db
for _ in $(seq 1 30); do
  docker compose --env-file .env exec -T db pg_isready -U "$POSTGRES_USER" && break
  sleep 2
done

echo "Restoring PostgreSQL..."
docker compose --env-file .env exec -T db \
  psql -U "$POSTGRES_USER" -d postgres < "$BACKUP_DIR/postgres.sql"

echo "Restoring filestore..."
docker compose --env-file .env up -d odoo
sleep 5
docker compose --env-file .env stop odoo
docker compose --env-file .env run --rm --no-deps --entrypoint tar odoo \
  -C /var/lib/odoo -xzf - < "$BACKUP_DIR/filestore.tgz"
docker compose --env-file .env up -d odoo
echo "Restore complete."
