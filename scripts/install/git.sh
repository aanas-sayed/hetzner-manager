#!/usr/bin/env bash
# Install: Git
# Usage: bash git.sh <username>
set -euo pipefail

USERNAME="${1:?Usage: $0 <username>}"

echo "[git] Installing git..."
apt-get install -y git

echo "[git] Configuring safe directory for $USERNAME..."
su - "$USERNAME" -c 'git config --global init.defaultBranch main'

echo "[git] Done."
