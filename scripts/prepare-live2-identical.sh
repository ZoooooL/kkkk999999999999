#!/usr/bin/env bash
# Prepare this Docker stack as Live 2 to match Live 1.
# Never SSHes to AWS. Never changes Live 1 DNS/SSL/processes.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
# shellcheck disable=SC1091
source "$ROOT/scripts/lib/protect-live1.sh"

if [[ ! -f .env ]]; then
  echo "Copy .env.example to .env and set passwords first." >&2
  exit 1
fi

# shellcheck disable=SC1091
set -a
source .env
set +a

forbid_touching_live1 "${ODOO_DOMAIN:-}"
forbid_touching_live1 "${HETZNER_SSH:-}"

echo "== 1/4 Live 1 public fingerprint (read-only HTTP, no SSH) =="
"$ROOT/scripts/fingerprint-live1.sh" "$ROOT/live1/fingerprint.runtime.json" || true

echo "== 2/4 Render Live 2 config to match Live 1 (list_db, all databases) =="
python3 scripts/render-odoo-conf.py
python3 scripts/render-nginx.py
mkdir -p addons enterprise backups certs/www

echo "== 3/4 Start Live 2 Docker (this machine only) =="
"$ROOT/scripts/up.sh"

DUMP=$(ls -1t "$ROOT"/backups/brodansh-live1-readonly-*.tar.gz 2>/dev/null | head -1 || true)
if [[ -n ${DUMP:-} ]]; then
  echo "== 4/4 Found dump $(basename "$DUMP") — importing into Live 2 only =="
  "$ROOT/scripts/import-live1-dump-to-live2.sh" "$DUMP"
else
  echo "== 4/4 No Live 1 dump in backups/ — stack is ready, data not cloned yet =="
  echo "Live 1 stays frozen. To reach 100% copy:"
  echo "  1. On AWS (read-only): sudo ./scripts/export-live1-readonly.sh"
  echo "  2. Copy the tar.gz into this repo's backups/ folder"
  echo "  3. Re-run: ./scripts/prepare-live2-identical.sh"
fi

echo
"$ROOT/scripts/check-live-parity.sh" || true
echo
echo "Live 1 (${LIVE1_DOMAIN:-brodansh.de.com.eg} / ${LIVE1_IP:-18.133.13.149}) was not modified."
