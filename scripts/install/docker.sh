#!/usr/bin/env bash
# Install: Docker CE
# Usage: bash docker.sh <username>
set -euo pipefail

USERNAME="${1:?Usage: $0 <username>}"

echo "[docker] Installing Docker CE via official script..."
curl -fsSL https://get.docker.com | sh

echo "[docker] Adding $USERNAME to docker group..."
usermod -aG docker "$USERNAME"

echo "[docker] Enabling and starting Docker service..."
systemctl enable docker
systemctl start docker

echo "[docker] Installing Docker Compose plugin..."
apt-get install -y docker-compose-plugin

echo "[docker] Done. Note: group change takes effect on next login."
