#!/usr/bin/env bash
# READ-ONLY dump of Live 1. Run this ON the current AWS host (or via SSH).
# Does not restart Odoo, does not change DNS, does not write into the live DB.
set -euo pipefail

DB=${LIVE_ODOO_DB:-brodansh}
FILESTORE=${LIVE_FILESTORE:-/var/lib/odoo/.local/share/Odoo/filestore}
ENTERPRISE=${LIVE_ENTERPRISE:-/opt/odoo/enterprise}
CUSTOM=${LIVE_CUSTOM_ADDONS:-/opt/odoo/custom-addons}
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
OUT=${1:-/tmp/brodansh-live1-readonly-${STAMP}}
mkdir -p "$OUT"

echo "Live 1 READ-ONLY export → $OUT"
echo "Odoo is not restarted. DNS is not changed."

dump_sql() {
  if command -v docker >/dev/null && docker ps --format '{{.Names}}' | grep -Eq 'db|postgres'; then
    local c
    c=$(docker ps --format '{{.Names}}' | grep -E 'db|postgres' | head -1)
    docker exec "$c" pg_dump -U odoo -Fc "$DB" > "$OUT/brodansh.dump"
    return
  fi
  if id postgres >/dev/null 2>&1; then
    sudo -u postgres pg_dump -Fc "$DB" > "$OUT/brodansh.dump"
    return
  fi
  echo "Could not find PostgreSQL to dump." >&2
  exit 1
}

dump_sql

if [[ -d ${FILESTORE}/${DB} ]]; then
  tar -C "${FILESTORE}/${DB}" -czf "$OUT/filestore.tgz" .
elif [[ -d $FILESTORE ]]; then
  tar -C "$FILESTORE" -czf "$OUT/filestore.tgz" .
else
  echo "Filestore not found at $FILESTORE (continuing)."
fi

if [[ -d $ENTERPRISE ]]; then
  tar -C "$ENTERPRISE" -czf "$OUT/enterprise.tgz" .
fi
if [[ -d $CUSTOM ]]; then
  tar -C "$CUSTOM" -czf "$OUT/addons.tgz" .
fi

echo "readonly-export $STAMP db=$DB" > "$OUT/MANIFEST.txt"
TARBALL="${OUT}.tar.gz"
tar -C "$(dirname "$OUT")" -czf "$TARBALL" "$(basename "$OUT")"
echo "Done: $TARBALL"
echo "Copy this file to Live 2 and run: ./scripts/import-live1-dump-to-live2.sh $TARBALL"
echo "Do not change brodansh.de.com.eg DNS."
