#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
# shellcheck disable=SC1091
set -a
source .env
set +a

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT_DIR=${1:-"$ROOT/backups/$STAMP"}
mkdir -p "$OUT_DIR"

echo "Dumping PostgreSQL..."
docker compose --env-file .env exec -T db \
  pg_dumpall -U "$POSTGRES_USER" --clean --if-exists \
  > "$OUT_DIR/postgres.sql"

echo "Archiving Odoo filestore..."
docker compose --env-file .env exec -T odoo \
  tar -C /var/lib/odoo -czf - . \
  > "$OUT_DIR/filestore.tgz"

cp config/odoo.conf.runtime "$OUT_DIR/odoo.conf" 2>/dev/null || true
echo "$STAMP" > "$OUT_DIR/MANIFEST.txt"
echo "Backup written to $OUT_DIR"
