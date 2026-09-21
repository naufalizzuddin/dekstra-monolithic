#!/usr/bin/env bash
set -Eeuo pipefail

if [[ ${EUID} -ne 0 ]]; then
  echo "Run this script with sudo: sudo bash deploy/ubuntu/install-docker.sh"
  exit 1
fi

source /etc/os-release
if [[ "${ID:-}" != "ubuntu" || "${VERSION_ID:-}" != "26.04" ]]; then
  echo "This installer targets Ubuntu 26.04. Detected: ${PRETTY_NAME:-unknown}"
  exit 1
fi

apt-get update
apt-get install -y ca-certificates curl openssl

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
  -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc

cat >/etc/apt/sources.list.d/docker.sources <<EOF
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: ${UBUNTU_CODENAME:-$VERSION_CODENAME}
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
EOF

apt-get update
apt-get install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin

systemctl enable --now docker

TARGET_USER="${SUDO_USER:-}"
if [[ -n "${TARGET_USER}" && "${TARGET_USER}" != "root" ]]; then
  usermod -aG docker "${TARGET_USER}"
  echo "Added ${TARGET_USER} to the docker group."
  echo "Log out and back in before running Docker without sudo."
fi

if command -v ufw >/dev/null 2>&1; then
  ufw allow OpenSSH
  ufw allow 8000/tcp
  echo "UFW rules added. The firewall was not enabled automatically."
fi

docker --version
docker compose version
