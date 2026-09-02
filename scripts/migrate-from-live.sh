#!/usr/bin/env bash
# Copy PostgreSQL + filestore + Enterprise addons from the live Ubuntu host
# into this Docker stack. Requires SSH access to the current Odoo server.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
# shellcheck disable=SC1091
set -a
source .env
set +a

if [[ -z ${LIVE_SSH_HOST:-} ]]; then
  echo "Set LIVE_SSH_HOST in .env (the current Ubuntu Odoo server)." >&2
  exit 1
fi

SSH=(ssh -p "${LIVE_SSH_PORT:-22}" -o StrictHostKeyChecking=accept-new "${LIVE_SSH_USER}@${LIVE_SSH_HOST}")
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
STAGE="$ROOT/backups/live-$STAMP"
mkdir -p "$STAGE" enterprise addons

echo "1/4 Inspecting live server ${LIVE_SSH_USER}@${LIVE_SSH_HOST}..."
"${SSH[@]}" 'set -e
  echo "hostname=$(hostname)"
  echo "os=$(. /etc/os-release; echo $PRETTY_NAME)"
  command -v docker >/dev/null && docker ps --format "docker={{.Names}} {{.Image}}" || echo "docker=not-running"
  command -v psql >/dev/null && echo "psql=$(psql --version)" || true
  ls -d /var/lib/odoo /opt/odoo /home/odoo 2>/dev/null || true
'

echo "2/4 Dumping live database ${LIVE_ODOO_DB}..."
# Prefer docker exec when the live host already runs Postgres in Docker.
if "${SSH[@]}" 'docker ps --format "{{.Names}}" | grep -Eq "db|postgres|odoo"'; then
  DB_CONTAINER=$("${SSH[@]}" 'docker ps --format "{{.Names}}" | grep -E "db|postgres" | head -1')
  "${SSH[@]}" "docker exec -t ${DB_CONTAINER} pg_dump -U odoo -Fc ${LIVE_ODOO_DB}" > "$STAGE/${LIVE_ODOO_DB}.dump" \
    || "${SSH[@]}" "docker exec -t ${DB_CONTAINER} pg_dump -U odoo -Fc postgres" > "$STAGE/${LIVE_ODOO_DB}.dump"
else
  "${SSH[@]}" "sudo -u postgres pg_dump -Fc ${LIVE_ODOO_DB}" > "$STAGE/${LIVE_ODOO_DB}.dump"
fi

echo "3/4 Copying filestore and Enterprise addons..."
rsync -az --info=progress2 -e "ssh -p ${LIVE_SSH_PORT:-22}" \
  "${LIVE_SSH_USER}@${LIVE_SSH_HOST}:${LIVE_FILESTORE}/${LIVE_ODOO_DB}/" \
  "$STAGE/filestore/" || true
if [[ -n ${LIVE_ENTERPRISE:-} ]]; then
  rsync -az --info=progress2 -e "ssh -p ${LIVE_SSH_PORT:-22}" \
    "${LIVE_SSH_USER}@${LIVE_SSH_HOST}:${LIVE_ENTERPRISE}/" \
    "$ROOT/enterprise/" || true
fi
if [[ -n ${LIVE_CUSTOM_ADDONS:-} ]]; then
  rsync -az --info=progress2 -e "ssh -p ${LIVE_SSH_PORT:-22}" \
    "${LIVE_SSH_USER}@${LIVE_SSH_HOST}:${LIVE_CUSTOM_ADDONS}/" \
    "$ROOT/addons/" || true
fi

echo "4/4 Restoring into Docker..."
python3 scripts/render-odoo-conf.py
docker compose --env-file .env up -d db
for _ in $(seq 1 30); do
  docker compose --env-file .env exec -T db pg_isready -U "$POSTGRES_USER" && break
  sleep 2
done

docker compose --env-file .env exec -T db \
  pg_restore --verbose --no-owner --role="$POSTGRES_USER" -U "$POSTGRES_USER" -d postgres --create \
  < "$STAGE/${LIVE_ODOO_DB}.dump" \
  || docker compose --env-file .env exec -T db \
       pg_restore --verbose --no-owner --role="$POSTGRES_USER" -U "$POSTGRES_USER" -d "$LIVE_ODOO_DB" \
       < "$STAGE/${LIVE_ODOO_DB}.dump"

if [[ -d $STAGE/filestore && -n $(ls -A "$STAGE/filestore" 2>/dev/null || true) ]]; then
  docker compose --env-file .env up -d odoo
  docker compose --env-file .env stop odoo
  docker compose --env-file .env run --rm --no-deps --entrypoint bash odoo -lc \
    "mkdir -p /var/lib/odoo/filestore/${LIVE_ODOO_DB}"
  docker compose --env-file .env run --rm --no-deps --entrypoint tar odoo \
    -C "/var/lib/odoo/filestore/${LIVE_ODOO_DB}" -xzf - < <(tar -C "$STAGE/filestore" -czf - .)
fi

docker compose --env-file .env up -d odoo
echo "Live restore staged from $STAGE"
echo "Open http://127.0.0.1:${ODOO_HTTP_PORT:-8069} and confirm ${LIVE_ODOO_DB}."
echo "Then switch DNS ${ODOO_DOMAIN} to the new server and run: ./scripts/ssl-init.sh"
