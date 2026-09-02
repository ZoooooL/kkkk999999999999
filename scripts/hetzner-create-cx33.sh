#!/usr/bin/env bash
# Create the locked Brodansh production VPS:
#   Hetzner CX33 · Ubuntu 24.04 · Falkenstein (fsn1), fallback Nuremberg (nbg1)
#
# Does not spend money unless HCLOUD_TOKEN is set. Console steps are printed either way.
set -euo pipefail

SERVER_NAME=${HCLOUD_SERVER_NAME:-brodansh-odoo}
SERVER_TYPE=${HCLOUD_SERVER_TYPE:-cx33}
IMAGE=${HCLOUD_IMAGE:-ubuntu-24.04}
PRIMARY_LOCATION=${HCLOUD_LOCATION:-fsn1}
FALLBACK_LOCATION=${HCLOUD_FALLBACK_LOCATION:-nbg1}
SSH_KEY_NAME=${HCLOUD_SSH_KEY:-}

ROOT=$(cd "$(dirname "$0")/.." && pwd)
USER_DATA="$ROOT/hetzner/cloud-init.yaml"

echo "Locked target: Hetzner ${SERVER_TYPE} / ${IMAGE}"
echo "  1) ${PRIMARY_LOCATION}  Falkenstein"
echo "  2) ${FALLBACK_LOCATION}  Nuremberg (if FSN1 is sold out)"
echo

print_console_steps() {
  cat <<'EOF'
Create it in the console (no API token needed):

  1. https://console.hetzner.cloud  → project → Add Server
  2. Location: Falkenstein (fsn1). If unavailable, Nuremberg (nbg1).
  3. Image: Ubuntu 24.04
  4. Type: CX33  (4 vCPU / 8 GB / 80 GB NVMe)
  5. Networking: IPv4 + IPv6
  6. Enable Backups
  7. SSH key: your public key
  8. Name: brodansh-odoo
  9. Create (~€8.99/mo with IPv4, +20% for backups)

Then:

  ssh root@SERVER_IP
  git clone <this-repo> /opt/odoo && cd /opt/odoo
  ./scripts/install-ubuntu-docker.sh
  cp .env.example .env && vim .env
  ./scripts/up.sh
EOF
}

print_console_steps

if [[ -z ${HCLOUD_TOKEN:-} ]]; then
  echo
  echo "No HCLOUD_TOKEN in the environment, so nothing was ordered."
  echo "Put a read/write project token in HCLOUD_TOKEN and re-run to create it from the CLI."
  exit 0
fi

if ! command -v hcloud >/dev/null 2>&1; then
  echo "Installing hcloud CLI..."
  ARCH=$(uname -m)
  case "$ARCH" in
    x86_64) HC_ARCH=amd64 ;;
    aarch64|arm64) HC_ARCH=arm64 ;;
    *) echo "Unsupported arch: $ARCH" >&2; exit 1 ;;
  esac
  TMP=$(mktemp -d)
  curl -fsSL "https://github.com/hetznercloud/cli/releases/latest/download/hcloud-linux-${HC_ARCH}.tar.gz" \
    | tar -xz -C "$TMP"
  sudo install -m 0755 "$TMP/hcloud" /usr/local/bin/hcloud
  rm -rf "$TMP"
fi

export HCLOUD_TOKEN
hcloud version

if [[ -z $SSH_KEY_NAME ]]; then
  SSH_KEY_NAME=$(hcloud ssh-key list -o noheader -o columns=name | awk 'NF{print; exit}')
fi
if [[ -z $SSH_KEY_NAME ]]; then
  echo "Upload an SSH key in the Hetzner console, or set HCLOUD_SSH_KEY." >&2
  exit 1
fi

if hcloud server describe "$SERVER_NAME" >/dev/null 2>&1; then
  echo "Server ${SERVER_NAME} already exists:"
  hcloud server describe "$SERVER_NAME"
  exit 0
fi

create_in() {
  local loc=$1
  echo "Creating ${SERVER_NAME} (${SERVER_TYPE}) in ${loc}..."
  hcloud server create \
    --name "$SERVER_NAME" \
    --type "$SERVER_TYPE" \
    --image "$IMAGE" \
    --location "$loc" \
    --ssh-key "$SSH_KEY_NAME" \
    --user-data-from-file "$USER_DATA" \
    --label "app=odoo" \
    --label "project=brodansh"
}

if ! create_in "$PRIMARY_LOCATION"; then
  echo "${PRIMARY_LOCATION} failed; trying ${FALLBACK_LOCATION}..."
  create_in "$FALLBACK_LOCATION"
fi

hcloud server enable-backup "$SERVER_NAME" || true

# Restrict public ports. Ignore if the firewall already exists.
if ! hcloud firewall describe brodansh-odoo >/dev/null 2>&1; then
  hcloud firewall create --name brodansh-odoo
  hcloud firewall add-rule brodansh-odoo --direction in --protocol tcp --port 22 --source-ips 0.0.0.0/0 --source-ips ::/0
  hcloud firewall add-rule brodansh-odoo --direction in --protocol tcp --port 80 --source-ips 0.0.0.0/0 --source-ips ::/0
  hcloud firewall add-rule brodansh-odoo --direction in --protocol tcp --port 443 --source-ips 0.0.0.0/0 --source-ips ::/0
fi
hcloud firewall apply-to-resource brodansh-odoo --type server --server "$SERVER_NAME" || true

echo
hcloud server describe "$SERVER_NAME"
IPV4=$(hcloud server ip "$SERVER_NAME")
echo
echo "SSH: ssh root@${IPV4}"
echo "After cloud-init finishes (~1–2 min): clone this repo into /opt/odoo and run ./scripts/up.sh"
echo "Keep DNS on the old host until migrate-from-live.sh and POS checks succeed."
