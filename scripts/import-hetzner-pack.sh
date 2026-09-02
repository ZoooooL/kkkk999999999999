#!/usr/bin/env bash
# Load a pack created by pack-for-hetzner.sh onto this machine (the CX33).
set -euo pipefail

PACK=${1:-}
if [[ -z $PACK ]]; then
  echo "Usage: $0 /path/to/brodansh-cx33-YYYYMMDDTHHMMSSZ.tar.gz" >&2
  exit 1
fi

WORKDIR=${2:-/opt/odoo}
mkdir -p "$WORKDIR"
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

echo "Extracting $PACK..."
tar -C "$TMP" -xzf "$PACK"
INNER=$(find "$TMP" -maxdepth 1 -mindepth 1 -type d | head -1)
[[ -n $INNER ]] || { echo "Pack has no directory." >&2; exit 1; }

echo "Installing stack into $WORKDIR..."
mkdir -p "$WORKDIR"
cp -a "$INNER/stack/." "$WORKDIR/"
cd "$WORKDIR"

if [[ -d $INNER/images ]]; then
  shopt -s nullglob
  for img in "$INNER/images"/*.tar; do
    echo "docker load $(basename "$img")"
    docker load -i "$img"
  done
fi

chmod +x scripts/*.sh scripts/*.py 2>/dev/null || true
if [[ ! -f .env ]]; then
  echo "Missing .env inside the pack." >&2
  exit 1
fi

# Production bind: nginx in front on the VPS.
if grep -q '^ODOO_BIND=' .env; then
  sed -i 's/^ODOO_BIND=.*/ODOO_BIND=127.0.0.1/' .env
else
  echo 'ODOO_BIND=127.0.0.1' >> .env
fi
if grep -q '^ODOO_CONF_FILE=' .env; then
  sed -i 's/^ODOO_CONF_FILE=.*/ODOO_CONF_FILE=odoo.prod.conf.runtime/' .env
else
  echo 'ODOO_CONF_FILE=odoo.prod.conf.runtime' >> .env
fi

python3 scripts/render-odoo-conf.py
docker compose --env-file .env up -d db
for _ in $(seq 1 40); do
  docker compose --env-file .env exec -T db pg_isready -U odoo && break
  sleep 2
done

echo "Restoring database + filestore..."
./scripts/restore.sh "$INNER/data"
docker compose --env-file .env up -d odoo
echo "Import complete. Open http://$(hostname -I | awk '{print $1}'):8069"
echo "Do not point brodansh.de.com.eg here. Add A record odoo.zouljanaheen.com then ./scripts/ssl-init.sh"
