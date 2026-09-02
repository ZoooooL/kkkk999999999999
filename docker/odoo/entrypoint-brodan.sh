#!/bin/bash
set -euo pipefail

# Production: live Enterprise tree is bind-mounted at /odoo/odoo-server.
# Demo: official image odoo binary (Community).
if [ -x /odoo/odoo-server/odoo-bin ]; then
  cd /odoo/odoo-server
  if [ "${1:-}" = "python3" ] || [ "${1:-}" = "odoo" ]; then
    exec "$@"
  fi
  exec python3 /odoo/odoo-server/odoo-bin "$@"
fi

if [ -x /entrypoint.sh ]; then
  if [ $# -eq 0 ]; then
    set -- odoo
  fi
  exec /entrypoint.sh "$@"
fi

exec odoo "$@"
