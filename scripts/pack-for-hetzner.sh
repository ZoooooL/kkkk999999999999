#!/usr/bin/env bash
# Pack the running local Docker Odoo so it can be copied to Hetzner CX33
# and run like https://brodansh.de.com.eg.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
cd "$ROOT"
# shellcheck disable=SC1091
set -a
source .env
set +a

WITH_IMAGES=1
REQUIRE_ENTERPRISE=0
for arg in "$@"; do
  case "$arg" in
    --skip-images) WITH_IMAGES=0 ;;
    --require-enterprise) REQUIRE_ENTERPRISE=1 ;;
    -h|--help)
      echo "Usage: $0 [--skip-images] [--require-enterprise]"
      exit 0
      ;;
    *) echo "Unknown option: $arg" >&2; exit 1 ;;
  esac
done

if [[ $REQUIRE_ENTERPRISE -eq 1 ]]; then
  if [[ ! -d $ROOT/enterprise/web_enterprise && ! -d $ROOT/enterprise/web_studio ]]; then
    echo "Live is Odoo 18.0+e. Copy Enterprise addons into ./enterprise first:" >&2
    echo "  rsync -az root@${LIVE_SSH_HOST:-LIVE}:/opt/odoo/enterprise/ ./enterprise/" >&2
    exit 1
  fi
fi

STAMP=$(date -u +%Y%m%dT%H%M%SZ)
PACK_NAME="brodansh-cx33-${STAMP}"
PACK_DIR="$ROOT/backups/$PACK_NAME"
mkdir -p "$PACK_DIR/images" "$PACK_DIR/data" "$PACK_DIR/stack"

echo "1/4 Backup database + filestore..."
"$ROOT/scripts/backup.sh" "$PACK_DIR/data"

echo "2/4 Copy stack files..."
tar -C "$ROOT" -cf - \
  --exclude .git \
  --exclude backups \
  --exclude certs \
  --exclude '.env' \
  compose.yaml Dockerfile .dockerignore .env.example .gitignore \
  README.md SERVERS.md \
  addons config db hetzner nginx scripts enterprise \
  | tar -C "$PACK_DIR/stack" -xf -
if [[ -f $ROOT/.env ]]; then
  cp "$ROOT/.env" "$PACK_DIR/stack/.env"
  chmod 600 "$PACK_DIR/stack/.env"
fi
printf '%s\n' "$STAMP" "target=Hetzner CX33 Ubuntu 24.04 fsn1/nbg1" \
  "live=https://brodansh.de.com.eg" "live_version=18.0+e" \
  > "$PACK_DIR/MANIFEST.txt"

if [[ $WITH_IMAGES -eq 1 ]]; then
  echo "3/4 Saving Docker images (this can take a few minutes)..."
  docker compose --env-file .env pull db nginx 2>/dev/null || true
  docker save -o "$PACK_DIR/images/postgres-16.tar" "postgres:${POSTGRES_VERSION:-16}"
  docker save -o "$PACK_DIR/images/brodansh-odoo-18.tar" "brodansh-odoo:${ODOO_VERSION:-18.0}"
  docker save -o "$PACK_DIR/images/nginx.tar" nginx:1.27-alpine
else
  echo "3/4 Skipping image save (--skip-images)."
  echo "skip-images=1" >> "$PACK_DIR/MANIFEST.txt"
fi

echo "4/4 Compressing pack..."
tar -C "$ROOT/backups" -czf "$ROOT/backups/${PACK_NAME}.tar.gz" "$PACK_NAME"
echo "Pack ready: $ROOT/backups/${PACK_NAME}.tar.gz"
ls -lh "$ROOT/backups/${PACK_NAME}.tar.gz"
echo
echo "Copy to Hetzner CX33:"
echo "  ./scripts/deploy-to-hetzner.sh root@SERVER_IP $ROOT/backups/${PACK_NAME}.tar.gz"
