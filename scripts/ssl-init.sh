#!/usr/bin/env bash
# Issue a Let's Encrypt certificate for ODOO_DOMAIN, then start nginx+odoo.
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

if [[ -z ${ODOO_DOMAIN:-} || -z ${LETSENCRYPT_EMAIL:-} ]]; then
  echo "Set ODOO_DOMAIN and LETSENCRYPT_EMAIL in .env" >&2
  exit 1
fi

python3 scripts/render-odoo-conf.py
python3 scripts/render-nginx.py
mkdir -p certs/www

# HTTP-only first so ACME can answer.
docker compose --env-file .env up -d db odoo
docker compose --env-file .env --profile prod up -d nginx

docker compose --env-file .env --profile prod run --rm --entrypoint certbot certbot certonly \
  --webroot -w /var/www/certbot \
  -d "$ODOO_DOMAIN" \
  --email "$LETSENCRYPT_EMAIL" \
  --agree-tos --no-eff-email

docker compose --env-file .env --profile prod up -d nginx
echo "TLS is active for Live 2: https://${ODOO_DOMAIN}"
echo "Live 1 (${LIVE1_DOMAIN:-brodansh.de.com.eg}) was not changed."
