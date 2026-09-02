#!/usr/bin/env bash
# Run as root ON the Hetzner VM (Cloud Console), never on Live 1 / the shop.
# Installs Docker and starts Live 2 from this public GitHub branch.
set -euo pipefail

REPO=${REPO:-https://github.com/ZoooooL/kkkk999999999999.git}
BRANCH=${BRANCH:-cursor/odoo-docker-ubuntu-d375}
DEST=${DEST:-/opt/odoo}
LIVE1_IP=${LIVE1_IP:-18.133.13.149}
SHOP_IP=${SHOP_IP:-46.101.110.51}

if [[ ${EUID} -ne 0 ]]; then
  exec sudo -- "$0" "$@"
fi

MYIP=$(curl -fsS --max-time 10 https://ifconfig.me || true)
if [[ $MYIP == "$LIVE1_IP" || $MYIP == 3.8.46.165 || $MYIP == "$SHOP_IP" ]]; then
  echo "Refusing: this machine is Live 1 or the shop. Run only on the Hetzner Live 2 VPS." >&2
  exit 1
fi

export DEBIAN_FRONTEND=noninteractive
apt-get update -qq
apt-get install -y -qq git curl ca-certificates python3 openssl

if [[ ! -d $DEST/.git ]]; then
  git clone --branch "$BRANCH" --depth 1 "$REPO" "$DEST"
else
  git -C "$DEST" fetch --depth 1 origin "$BRANCH"
  git -C "$DEST" checkout "$BRANCH"
  git -C "$DEST" reset --hard "origin/$BRANCH"
fi
cd "$DEST"
chmod +x scripts/*.sh scripts/*.py 2>/dev/null || true

"$DEST/scripts/install-ubuntu-docker.sh"
ufw allow 8069/tcp || true

if [[ ! -f $DEST/.env ]]; then
  cp "$DEST/.env.example" "$DEST/.env"
  PG=$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 24)
  ADM=$(openssl rand -base64 24 | tr -dc 'A-Za-z0-9' | head -c 24)
  sed -i "s/^POSTGRES_PASSWORD=.*/POSTGRES_PASSWORD=${PG}/" "$DEST/.env"
  sed -i "s/^ODOO_ADMIN_PASSWORD=.*/ODOO_ADMIN_PASSWORD=${ADM}/" "$DEST/.env"
  sed -i 's/^ODOO_BIND=.*/ODOO_BIND=0.0.0.0/' "$DEST/.env"
  sed -i 's|^HETZNER_SSH=.*|HETZNER_SSH=root@167.233.205.193|' "$DEST/.env"
  echo "Wrote $DEST/.env (master password printed once below)."
  echo "ODOO_ADMIN_PASSWORD=${ADM}"
fi

"$DEST/scripts/up.sh"
echo
echo "Live 2 Docker is on this Hetzner server."
echo "Open: http://${MYIP:-167.233.205.193}:8069"
echo "Do not change brodansh.de.com.eg or zouljanaheen.com DNS."
echo "Optional A record: odoo.zouljanaheen.com → ${MYIP:-167.233.205.193}"
