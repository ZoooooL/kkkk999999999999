#!/bin/bash
# Move brodansh.de.com.eg Odoo (8069/8072) into Docker on the live host.
# Requires root. Does not copy the 51GB database. Does not stop brodan-att.
set -euo pipefail

if [ "$(id -u)" -ne 0 ]; then
  echo "cutover.sh must run as root on the Odoo server" >&2
  exit 1
fi

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

if ! command -v docker >/dev/null 2>&1; then
  echo "Install Docker Engine first (docker.io / docker-ce) then re-run." >&2
  exit 1
fi

if [ ! -x /odoo/odoo-server/odoo-bin ]; then
  echo "Missing /odoo/odoo-server/odoo-bin — refusing to start Community against Enterprise." >&2
  exit 1
fi

if [ ! -f /etc/odoo-server.conf ]; then
  echo "Missing /etc/odoo-server.conf" >&2
  exit 1
fi

if ! ls /var/run/postgresql/.s.PGSQL.* >/dev/null 2>&1; then
  echo "PostgreSQL unix socket not found under /var/run/postgresql" >&2
  exit 1
fi

if [ ! -f .env ]; then
  cp .env.example .env
  UID_NUM="$(id -u odoo 2>/dev/null || echo 111)"
  GID_NUM="$(id -g odoo 2>/dev/null || echo 116)"
  sed -i "s/^ODOO_UID=.*/ODOO_UID=${UID_NUM}/" .env
  sed -i "s/^ODOO_GID=.*/ODOO_GID=${GID_NUM}/" .env
  echo "Wrote .env with ODOO_UID=${UID_NUM} ODOO_GID=${GID_NUM}. Edit ODOO_DATA_DIR if filestore is not /home/odoo/.local/share/Odoo"
fi

# Stop only the brodansh config process. Never match odoo-server-att.conf.
if systemctl list-unit-files --type=service 2>/dev/null | grep -qE '^odoo-server\.service|^odoo\.service'; then
  systemctl stop odoo-server 2>/dev/null || true
  systemctl stop odoo 2>/dev/null || true
fi

pkill -f '/odoo/odoo-server/odoo-bin -c /etc/odoo-server.conf' 2>/dev/null || true
sleep 2
if pgrep -f '/odoo/odoo-server/odoo-bin -c /etc/odoo-server.conf' >/dev/null; then
  echo "brodansh Odoo is still running; stop it manually then re-run." >&2
  exit 1
fi

if ! pgrep -f '/odoo/odoo-server/odoo-bin -c /etc/odoo-server-att.conf' >/dev/null; then
  echo "note: brodan-att process was not found (8079). Continuing with brodansh only."
fi

docker compose -f docker-compose.prod.yml --env-file .env up -d --build
echo "Brodansh Odoo is in Docker. Nginx still serves https://brodansh.de.com.eg/odoo"
echo "Rollback: docker compose -f docker-compose.prod.yml down && start the previous odoo-bin -c /etc/odoo-server.conf process."
