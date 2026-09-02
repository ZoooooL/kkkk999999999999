#!/usr/bin/env bash
# Install Docker Engine + Compose on Ubuntu 22.04 / 24.04 for Odoo.
set -euo pipefail

if [[ ${EUID} -ne 0 ]]; then
  exec sudo -- "$0" "$@"
fi

export DEBIAN_FRONTEND=noninteractive

. /etc/os-release
if [[ ${ID} != ubuntu ]]; then
  echo "This installer supports Ubuntu only (found: ${ID})." >&2
  exit 1
fi

apt-get update -qq
apt-get install -y -qq ca-certificates curl gnupg ufw fail2ban unattended-upgrades

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu ${VERSION_CODENAME} stable" \
  > /etc/apt/sources.list.d/docker.list

apt-get update -qq
apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

FSTYPE=$(findmnt -n -o FSTYPE / || true)
STORAGE_DRIVER=overlay2
if [[ ${FSTYPE} == overlay* ]]; then
  echo "Root filesystem is ${FSTYPE}; using vfs so nested Docker can start."
  STORAGE_DRIVER=vfs
fi

install -m 0644 /dev/null /etc/docker/daemon.json
cat > /etc/docker/daemon.json <<JSON
{
  "storage-driver": "${STORAGE_DRIVER}",
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "5"
  },
  "live-restore": true
}
JSON

# Nested/cloud VMs often send docker-bridge traffic through iptables
# (bridge-nf-call-iptables=1), which drops Odoo -> Postgres on 5432.
sysctl -w net.ipv4.ip_forward=1 >/dev/null
if [[ -w /proc/sys/net/bridge/bridge-nf-call-iptables ]]; then
  sysctl -w net.bridge.bridge-nf-call-iptables=0 >/dev/null || true
  sysctl -w net.bridge.bridge-nf-call-ip6tables=0 >/dev/null || true
fi
mkdir -p /etc/sysctl.d
cat > /etc/sysctl.d/99-odoo-docker.conf <<'SYSCTL'
net.ipv4.ip_forward=1
net.bridge.bridge-nf-call-iptables=0
net.bridge.bridge-nf-call-ip6tables=0
SYSCTL

if command -v systemctl >/dev/null 2>&1 && systemctl is-system-running >/dev/null 2>&1; then
  systemctl enable --now docker
else
  service docker restart || service docker start
fi

TARGET_USER=${SUDO_USER:-ubuntu}
if id "${TARGET_USER}" >/dev/null 2>&1; then
  usermod -aG docker "${TARGET_USER}"
fi

ufw allow OpenSSH
ufw allow 80/tcp
ufw allow 443/tcp
ufw --force enable || true

docker --version
docker compose version
docker run --rm hello-world

echo
echo "Docker is ready. Log out and back in (or run: newgrp docker), then:"
echo "  cp .env.example .env"
echo "  ./scripts/up.sh"
