#!/bin/sh
set -eu

DEST="${DEST:-onedrive}"
mkdir -p /var/lib/tailscale /var/lib/rclone /var/run/tailscale /tmp

if [ "${1:-}" = "bash" ] || [ "${1:-}" = "sh" ]; then
  exec "$@"
fi

if [ "$DEST" = "sftp" ]; then
  if [ -z "${TS_AUTHKEY:-}" ]; then
    echo "DEST=sftp requires TS_AUTHKEY from https://login.tailscale.com/admin/settings/keys" >&2
    exit 1
  fi
  tailscaled \
    --state=/var/lib/tailscale/tailscaled.state \
    --socket=/var/run/tailscale/tailscaled.sock \
    --tun=userspace-networking \
    --socks5-server=127.0.0.1:1055 \
    --outbound-http-proxy-listen=localhost:1056 &
  i=0
  while [ "$i" -lt 30 ]; do
    if [ -S /var/run/tailscale/tailscaled.sock ]; then
      break
    fi
    i=$((i + 1))
    sleep 1
  done
  tailscale --socket=/var/run/tailscale/tailscaled.sock up \
    --authkey="$TS_AUTHKEY" \
    --hostname="${TS_HOSTNAME:-brodan-backup}" \
    --accept-dns=false
fi

if command -v pg_isready >/dev/null 2>&1; then
  pg_isready -d "${PGDATABASE:-brodansh}" -t 8 || echo "warning: postgres not ready yet, dump may fail"
fi

exec python3 /app/run_backup.py "$@"
