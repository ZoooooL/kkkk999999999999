#!/usr/bin/env bash
# Restore a Live-1 READ-ONLY dump into THIS Live-2 Docker stack.
# Never connects to AWS except if you pass a local dump file.
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
if [[ -z $DUMP || ! -f $DUMP ]]; then
  echo "Usage: $0 /path/to/brodansh-live1-readonly-XXXX.tar.gz" >&2
  echo "Create the dump on Live 1 with scripts/export-live1-readonly.sh (read-only)." >&2
  exit 1
fi

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
tar -C "$TMP" -xzf "$DUMP"
INNER=$(find "$TMP" -maxdepth 1 -mindepth 1 -type d | head -1)
[[ -n $INNER ]] || { echo "Empty dump." >&2; exit 1; }

mkdir -p enterprise addons
if [[ -f $INNER/enterprise.tgz ]]; then
  tar -C "$ROOT/enterprise" -xzf "$INNER/enterprise.tgz"
fi
if [[ -f $INNER/addons.tgz ]]; then
  tar -C "$ROOT/addons" -xzf "$INNER/addons.tgz"
fi

python3 scripts/render-odoo-conf.py
docker compose --env-file .env up -d db
for _ in $(seq 1 40); do
  docker compose --env-file .env exec -T db pg_isready -U "$POSTGRES_USER" && break
  sleep 2
done

if [[ -f $INNER/brodansh.dump ]]; then
  echo "Restoring database into Live 2 only..."
  docker compose --env-file .env exec -T db \
    pg_restore --verbose --no-owner --role="$POSTGRES_USER" -U "$POSTGRES_USER" -d postgres --create \
    < "$INNER/brodansh.dump" \
    || docker compose --env-file .env exec -T db \
         pg_restore --verbose --no-owner --role="$POSTGRES_USER" -U "$POSTGRES_USER" -d "${LIVE_ODOO_DB:-brodansh}" \
         < "$INNER/brodansh.dump"
fi

if [[ -f $INNER/filestore.tgz ]]; then
  docker compose --env-file .env up -d odoo
  docker compose --env-file .env stop odoo
  docker compose --env-file .env run --rm --no-deps --entrypoint bash odoo -lc \
    "mkdir -p /var/lib/odoo/filestore/${LIVE_ODOO_DB:-brodansh}"
  docker compose --env-file .env run --rm --no-deps --entrypoint tar odoo \
    -C "/var/lib/odoo/filestore/${LIVE_ODOO_DB:-brodansh}" -xzf - < "$INNER/filestore.tgz"
fi

docker compose --env-file .env up -d odoo
echo "Live 2 restored from $(basename "$DUMP")."
echo "Live 1 (${LIVE1_DOMAIN}) was not modified."
echo "Open Live 2: http://127.0.0.1:${ODOO_HTTP_PORT:-8069}"
