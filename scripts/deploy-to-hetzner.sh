#!/usr/bin/env bash
# Copy a local Docker pack to Hetzner CX33 and import it.
set -euo pipefail
ROOT=$(cd "$(dirname "$0")/.." && pwd)
# shellcheck disable=SC1091
source "$ROOT/scripts/lib/protect-live1.sh"

DEST=${1:-${HETZNER_SSH:-}}
PACK=${2:-}
forbid_touching_live1 "$DEST"
if [[ -z $DEST ]]; then
  echo "Usage: $0 root@CX33_IP [pack.tar.gz]" >&2
  echo "Example: $0 root@162.55.x.x backups/brodansh-cx33-XXXX.tar.gz" >&2
  exit 1
fi

if [[ -z $PACK ]]; then
  PACK=$(ls -1t "$ROOT"/backups/brodansh-cx33-*.tar.gz 2>/dev/null | head -1 || true)
fi
if [[ -z $PACK || ! -f $PACK ]]; then
  echo "No pack found. Run ./scripts/pack-for-hetzner.sh first." >&2
  exit 1
fi

REMOTE_PACK=/tmp/$(basename "$PACK")
echo "Uploading $PACK → $DEST:$REMOTE_PACK"
scp -o StrictHostKeyChecking=accept-new "$PACK" "$DEST:$REMOTE_PACK"
scp -o StrictHostKeyChecking=accept-new "$ROOT/scripts/import-hetzner-pack.sh" "$DEST:/tmp/import-hetzner-pack.sh"

ssh -o StrictHostKeyChecking=accept-new "$DEST" bash -s <<EOF
set -euo pipefail
if ! command -v docker >/dev/null; then
  curl -fsSL https://get.docker.com | sh
fi
sysctl -w net.ipv4.ip_forward=1 >/dev/null || true
[[ -w /proc/sys/net/bridge/bridge-nf-call-iptables ]] && sysctl -w net.bridge.bridge-nf-call-iptables=0 || true
install -d -m 0755 /opt/odoo
chmod +x /tmp/import-hetzner-pack.sh
/tmp/import-hetzner-pack.sh $REMOTE_PACK /opt/odoo
EOF

echo "Deployed Live 2 to $DEST. Live 1 DNS (${LIVE1_DOMAIN:-brodansh.de.com.eg}) was not changed."
echo "Add a NEW A record odoo.zouljanaheen.com → this CX33 IP. Do not change brodansh.de.com.eg or zouljanaheen.com."
