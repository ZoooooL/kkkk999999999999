#!/usr/bin/env bash
# Create a Community database and prove /web/login is reachable.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
# shellcheck disable=SC1091
set -a
source .env
set +a

BASE=http://127.0.0.1:${ODOO_HTTP_PORT:-8069}

echo "== docker compose ps =="
docker compose --env-file .env ps

echo "== health =="
curl -fsS "$BASE/web/health" && echo
curl -fsS -o /tmp/odoo-selector.html -w "selector_http=%{http_code}\n" "$BASE/web/database/selector"

echo "== create database ${ODOO_DB_NAME} =="
# Skip if the database already exists.
if docker compose --env-file .env exec -T db \
    psql -U "$POSTGRES_USER" -d postgres -tAc "SELECT 1 FROM pg_database WHERE datname='${ODOO_DB_NAME}'" | grep -q 1; then
  echo "database ${ODOO_DB_NAME} already exists"
else
  curl -fsS -X POST "$BASE/web/database/create" \
    -H "Content-Type: application/x-www-form-urlencoded" \
    --data-urlencode "master_pwd=${ODOO_ADMIN_PASSWORD}" \
    --data-urlencode "name=${ODOO_DB_NAME}" \
    --data-urlencode "login=admin" \
    --data-urlencode "password=admin" \
    --data-urlencode "lang=ar_001" \
    --data-urlencode "country_code=eg" \
    --data-urlencode "phone=" \
    -o /tmp/odoo-create.html -w "create_http=%{http_code}\n"
fi

sleep 5
curl -fsS -o /tmp/odoo-login.html -w "login_http=%{http_code}\n" "$BASE/web/login"
grep -qi odoo /tmp/odoo-login.html
echo "smoke test passed: ${BASE}/web/login"
