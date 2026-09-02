#!/usr/bin/env bash
# Restore a Live-1 READ-ONLY dump into THIS Live-2 Docker stack.
# Never connects to AWS. Live 1 stays as-is.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib/protect-live1.sh"
# shellcheck disable=SC1091
set -a
source .env
set +a

forbid_touching_live1 "${ODOO_DOMAIN:-}"
forbid_touching_live1 "${HETZNER_SSH:-}"

DUMP=${1:-}
if [[ -z $DUMP ]]; then
  DUMP=$(ls -1t "$ROOT"/backups/brodansh-live1-readonly-*.tar.gz 2>/dev/null | head -1 || true)
fi
if [[ -z $DUMP || ! -f $DUMP ]]; then
  echo "Usage: $0 /path/to/brodansh-live1-readonly-XXXX.tar.gz" >&2
  echo "Create the dump on Live 1 with scripts/export-live1-readonly.sh (read-only)." >&2
  echo "Place the file in backups/ — this script never SSHes to AWS." >&2
  exit 1
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
tar -C "$TMP" -xzf "$DUMP"
INNER=$(find "$TMP" -maxdepth 2 -type f \( -name '*.dump' -o -name 'postgres.sql' -o -name 'MANIFEST.txt' \) | head -1 || true)
if [[ -n $INNER ]]; then
  INNER=$(dirname "$INNER")
else
  INNER=$(find "$TMP" -maxdepth 1 -mindepth 1 -type d | head -1)
fi
[[ -n $INNER ]] || { echo "Empty dump." >&2; exit 1; }

mkdir -p enterprise addons
if [[ -f $INNER/enterprise.tgz ]]; then
  tar -C "$ROOT/enterprise" -xzf "$INNER/enterprise.tgz"
  echo "Enterprise addons restored into ./enterprise"
fi
if [[ -f $INNER/addons.tgz ]]; then
  tar -C "$ROOT/addons" -xzf "$INNER/addons.tgz"
  echo "Custom addons restored into ./addons"
fi

python3 scripts/render-odoo-conf.py
docker compose --env-file .env stop odoo >/dev/null 2>&1 || true
docker compose --env-file .env up -d db
for _ in $(seq 1 40); do
  docker compose --env-file .env exec -T db pg_isready -U "$POSTGRES_USER" && break
  sleep 2
done

restore_custom_dump() {
  local dump_file=$1
  local db_name
  db_name=$(basename "$dump_file" .dump)
  echo "Restoring database $db_name into Live 2 only..."
  docker compose --env-file .env exec -T db \
    psql -U "$POSTGRES_USER" -d postgres -c "SELECT pg_terminate_backend(pid) FROM pg_stat_activity WHERE datname='${db_name}' AND pid <> pg_backend_pid();" \
    >/dev/null 2>&1 || true
  docker compose --env-file .env exec -T db \
    psql -U "$POSTGRES_USER" -d postgres -c "DROP DATABASE IF EXISTS \"${db_name}\";"
  docker compose --env-file .env exec -T db \
    psql -U "$POSTGRES_USER" -d postgres -c "CREATE DATABASE \"${db_name}\" OWNER ${POSTGRES_USER} TEMPLATE template0;"
  docker compose --env-file .env exec -T db \
    pg_restore --verbose --no-owner --role="$POSTGRES_USER" -U "$POSTGRES_USER" -d "$db_name" \
    < "$dump_file" || true
}

shopt -s nullglob
DUMPS=("$INNER"/*.dump)
if [[ ${#DUMPS[@]} -gt 0 ]]; then
  for dump_file in "${DUMPS[@]}"; do
    restore_custom_dump "$dump_file"
  done
elif [[ -f $INNER/postgres.sql ]]; then
  echo "Restoring pg_dumpall into Live 2 only..."
  docker compose --env-file .env exec -T db \
    psql -U "$POSTGRES_USER" -d postgres < "$INNER/postgres.sql" || true
elif [[ -f $INNER/brodansh.dump ]]; then
  restore_custom_dump "$INNER/brodansh.dump"
else
  echo "No PostgreSQL dump found in archive." >&2
  exit 1
fi

if [[ -f $INNER/filestore.tgz ]]; then
  docker compose --env-file .env up -d odoo
  docker compose --env-file .env stop odoo
  docker compose --env-file .env run --rm --no-deps --entrypoint bash odoo -lc \
    "mkdir -p /var/lib/odoo/filestore && chown -R odoo:odoo /var/lib/odoo"
  docker compose --env-file .env run --rm --no-deps --entrypoint tar odoo \
    -C /var/lib/odoo/filestore -xzf - < "$INNER/filestore.tgz"
fi

docker compose --env-file .env up -d --build odoo
echo "Live 2 restored from $(basename "$DUMP")."
echo "Live 1 (${LIVE1_DOMAIN:-brodansh.de.com.eg}) was not modified."
echo "Open Live 2: http://127.0.0.1:${ODOO_HTTP_PORT:-8069}/web/database/selector"
