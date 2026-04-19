#!/usr/bin/env bash
# Install: Node.js LTS + npm (via NodeSource)
# Usage: bash npm.sh <username>
set -euo pipefail

USERNAME="${1:?Usage: $0 <username>}"

echo "[npm] Adding NodeSource LTS repository..."
curl -fsSL https://deb.nodesource.com/setup_lts.x | bash -

echo "[npm] Installing Node.js and npm..."
apt-get install -y nodejs

echo "[npm] Configuring npm global prefix for $USERNAME (no sudo needed)..."
NPM_GLOBAL="/home/$USERNAME/.npm-global"
su - "$USERNAME" -c "mkdir -p $NPM_GLOBAL"
su - "$USERNAME" -c "npm config set prefix '$NPM_GLOBAL'"
su - "$USERNAME" -c "echo 'export PATH=\"\$HOME/.npm-global/bin:\$PATH\"' >> ~/.bashrc"

echo "[npm] Done. Node: $(node --version), npm: $(npm --version)"
