#!/usr/bin/env bash
# Optional READ-ONLY SSH pull of Live 1 into THIS Live-2 Docker stack.
# Disabled by default so Live 1 is never contacted.
# Prefer: export-live1-readonly.sh on AWS, then import-live1-dump-to-live2.sh here.
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

if [[ ${ALLOW_LIVE1_READONLY_SSH:-0} != 1 ]]; then
  echo "Refusing SSH to Live 1. Live 1 stays as-is." >&2
  echo "Copy a dump file into backups/ and run:" >&2
  echo "  ./scripts/import-live1-dump-to-live2.sh backups/brodansh-live1-readonly-XXXX.tar.gz" >&2
  echo "To opt in to a read-only SSH dump (no restart, no DNS change):" >&2
  echo "  ALLOW_LIVE1_READONLY_SSH=1 $0" >&2
  exit 1
fi

if [[ -z ${LIVE_SSH_HOST:-} ]]; then
  echo "Set LIVE_SSH_HOST in .env (the current Ubuntu Odoo server)." >&2
  exit 1
fi

SSH=(ssh -p "${LIVE_SSH_PORT:-22}" -o StrictHostKeyChecking=accept-new "${LIVE_SSH_USER}@${LIVE_SSH_HOST}")
STAMP=$(date -u +%Y%m%dT%H%M%SZ)
mkdir -p "$ROOT/backups" enterprise addons

echo "1/4 READ-ONLY inspect of Live 1 ${LIVE_SSH_USER}@${LIVE_SSH_HOST} (no restart)..."
"${SSH[@]}" 'set -e
  echo "hostname=$(hostname)"
  echo "os=$(. /etc/os-release; echo $PRETTY_NAME)"
  command -v docker >/dev/null && docker ps --format "docker={{.Names}} {{.Image}}" || echo "docker=not-running"
'

echo "2/4 READ-ONLY export of all databases (Live 1 stays online)..."
scp -P "${LIVE_SSH_PORT:-22}" -o StrictHostKeyChecking=accept-new \
  "$ROOT/scripts/export-live1-readonly.sh" \
  "${LIVE_SSH_USER}@${LIVE_SSH_HOST}:/tmp/export-live1-readonly.sh"
REMOTE_OUT=/tmp/brodansh-live1-readonly-${STAMP}
"${SSH[@]}" "sudo env LIVE_ODOO_DBS='${LIVE_ODOO_DBS:-brodan,brodan2026,brodansh,test}' LIVE_FILESTORE='${LIVE_FILESTORE}' LIVE_ENTERPRISE='${LIVE_ENTERPRISE}' LIVE_CUSTOM_ADDONS='${LIVE_CUSTOM_ADDONS}' bash /tmp/export-live1-readonly.sh ${REMOTE_OUT}"

echo "3/4 Copy dump off Live 1 into backups/..."
LOCAL_DUMP="$ROOT/backups/brodansh-live1-readonly-${STAMP}.tar.gz"
scp -P "${LIVE_SSH_PORT:-22}" -o StrictHostKeyChecking=accept-new \
  "${LIVE_SSH_USER}@${LIVE_SSH_HOST}:${REMOTE_OUT}.tar.gz" \
  "$LOCAL_DUMP"

echo "4/4 Restore into Live 2 Docker only..."
"$ROOT/scripts/import-live1-dump-to-live2.sh" "$LOCAL_DUMP"
echo "Live 1 (${LIVE1_DOMAIN:-brodansh.de.com.eg} / ${LIVE1_IP:-18.133.13.149}) was not restarted or re-pointed."
