#!/usr/bin/env bash
# READ-ONLY dump of Live 1. Run this ON the current AWS host (or copy the
# script there). Does not restart Odoo, does not change DNS, does not write
# into the live databases.
#
# Dumps EVERY Odoo database (Live 1 has brodan, brodan2026, brodansh, test).
set -euo pipefail

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT=${1:-/tmp/brodansh-live1-readonly-${STAMP}}
FILESTORE=${LIVE_FILESTORE:-/var/lib/odoo/.local/share/Odoo/filestore}
ENTERPRISE=${LIVE_ENTERPRISE:-/opt/odoo/enterprise}
CUSTOM=${LIVE_CUSTOM_ADDONS:-/opt/odoo/custom-addons}
mkdir -p "$OUT"

echo "Live 1 READ-ONLY export → $OUT"
echo "Odoo is not restarted. DNS is not changed. No writes to the databases."

postgres_cmd() {
  if command -v docker >/dev/null && docker ps --format '{{.Names}}' | grep -Eq 'db|postgres'; then
    local c
    c=$(docker ps --format '{{.Names}}' | grep -E 'db|postgres' | head -1)
    docker exec "$c" "$@"
    return
  fi
  if id postgres >/dev/null 2>&1; then
    sudo -u postgres "$@"
    return
  fi
  echo "Could not find PostgreSQL." >&2
  exit 1
}

list_dbs() {
  if [[ -n ${LIVE_ODOO_DBS:-} ]]; then
    printf '%s' "$LIVE_ODOO_DBS" | tr ',' '\n' | sed '/^$/d'
    return
  fi
  postgres_cmd psql -d postgres -Atc \
    "SELECT datname FROM pg_database WHERE datistemplate = false AND datname NOT IN ('postgres') ORDER BY 1"
}

mapfile -t DBS < <(list_dbs)
if [[ ${#DBS[@]} -eq 0 ]]; then
  echo "No databases found to dump." >&2
  exit 1
fi
echo "Databases: ${DBS[*]}"

for db in "${DBS[@]}"; do
  echo "pg_dump -Fc $db"
  if command -v docker >/dev/null && docker ps --format '{{.Names}}' | grep -Eq 'db|postgres'; then
    c=$(docker ps --format '{{.Names}}' | grep -E 'db|postgres' | head -1)
    docker exec "$c" pg_dump -U odoo -Fc "$db" > "$OUT/${db}.dump"
  elif id postgres >/dev/null 2>&1; then
    sudo -u postgres pg_dump -Fc "$db" > "$OUT/${db}.dump"
  else
    echo "Could not dump $db" >&2
    exit 1
  fi
done

if command -v docker >/dev/null && docker ps --format '{{.Names}}' | grep -Eq 'db|postgres'; then
  c=$(docker ps --format '{{.Names}}' | grep -E 'db|postgres' | head -1)
  docker exec "$c" pg_dumpall -U odoo --clean --if-exists > "$OUT/postgres.sql" || true
elif id postgres >/dev/null 2>&1; then
  sudo -u postgres pg_dumpall --clean --if-exists > "$OUT/postgres.sql" || true
fi

if [[ -d $FILESTORE ]]; then
  tar -C "$FILESTORE" -czf "$OUT/filestore.tgz" .
  echo "Filestore packed from $FILESTORE"
else
  echo "Filestore not found at $FILESTORE (continuing)."
fi

if [[ -d $ENTERPRISE ]]; then
  tar -C "$ENTERPRISE" -czf "$OUT/enterprise.tgz" .
  echo "Enterprise packed from $ENTERPRISE"
else
  echo "WARNING: $ENTERPRISE missing — Live 2 cannot be 18.0+e without it."
fi
if [[ -d $CUSTOM ]]; then
  tar -C "$CUSTOM" -czf "$OUT/addons.tgz" .
fi

{
  echo "readonly-export $STAMP"
  echo "databases=${DBS[*]}"
  echo "live1_untouched=1"
} > "$OUT/MANIFEST.txt"
printf '%s\n' "${DBS[@]}" > "$OUT/DATABASES.txt"

TARBALL="${OUT}.tar.gz"
tar -C "$(dirname "$OUT")" -czf "$TARBALL" "$(basename "$OUT")"
echo "Done: $TARBALL"
echo "Copy this file to Live 2 and run:"
echo "  ./scripts/import-live1-dump-to-live2.sh $TARBALL"
echo "Do not change brodansh.de.com.eg DNS."
