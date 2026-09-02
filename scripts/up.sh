#!/usr/bin/env bash
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"

if [[ ! -f .env ]]; then
  echo "Copy .env.example to .env and set passwords first." >&2
  exit 1
fi

# shellcheck disable=SC1091
source "$ROOT/scripts/lib/protect-live1.sh"
# shellcheck disable=SC1091
set -a
source .env
set +a

forbid_touching_live1 "${ODOO_DOMAIN:-}"

python3 scripts/render-odoo-conf.py
python3 scripts/render-nginx.py

mkdir -p addons enterprise backups certs/www

if [[ ! -f config/odoo.conf.runtime ]]; then
  echo "Missing rendered Odoo config." >&2
  exit 1
fi

# Compose mounts the rendered file.
export COMPOSE_FILE=${COMPOSE_FILE:-compose.yaml}
docker compose --env-file .env up -d --build "$@"

echo "Waiting for Odoo health..."
for _ in $(seq 1 60); do
  if curl -fsS "http://127.0.0.1:${ODOO_HTTP_PORT:-8069}/web/health" >/dev/null 2>&1 \
    || curl -fsS "http://127.0.0.1:${ODOO_HTTP_PORT:-8069}/web/database/selector" >/dev/null 2>&1 \
    || curl -fsS "http://127.0.0.1:${ODOO_HTTP_PORT:-8069}/web/login" >/dev/null 2>&1; then
    echo "Odoo Live 2 is up: http://127.0.0.1:${ODOO_HTTP_PORT:-8069}"
    echo "Live 1 (${LIVE1_DOMAIN:-brodansh.de.com.eg}) was not modified."
    exit 0
  fi
  sleep 3
done

echo "Odoo did not become healthy in time. Logs:" >&2
docker compose --env-file .env logs --tail=80 odoo db >&2
exit 1
