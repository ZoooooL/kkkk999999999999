#!/usr/bin/env bash
# Publish THIS Live 2 (local Docker on :8069) on a temporary HTTPS URL.
# Does not change DNS for Live 1, the shop, or odoo.zouljanaheen.com.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib/protect-live1.sh"

forbid_touching_live1 "${1:-}"

if ! command -v cloudflared >/dev/null; then
  echo "Installing cloudflared..."
  curl -fsSL https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64 \
    -o /tmp/cloudflared
  chmod +x /tmp/cloudflared
  sudo mv /tmp/cloudflared /usr/local/bin/cloudflared
fi

"$ROOT/scripts/up.sh"

echo "Starting public tunnel to http://127.0.0.1:${ODOO_HTTP_PORT:-8069}"
echo "Live 1 and zouljanaheen.com DNS are not changed."
exec cloudflared tunnel --no-autoupdate --url "http://127.0.0.1:${ODOO_HTTP_PORT:-8069}"
