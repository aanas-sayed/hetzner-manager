#!/usr/bin/env bash
# Install: Wine
# Usage: bash wine.sh <username>
set -euo pipefail

USERNAME="${1:?Usage: $0 <username>}"

echo "[wine] Enabling 32-bit architecture..."
dpkg --add-architecture i386

echo "[wine] Adding WineHQ repository..."
mkdir -pm755 /etc/apt/keyrings
curl -fsSL https://dl.winehq.org/wine-builds/winehq.key \
    | gpg --dearmor -o /etc/apt/keyrings/winehq-archive.key

. /etc/os-release
curl -fsSL "https://dl.winehq.org/wine-builds/ubuntu/dists/${UBUNTU_CODENAME}/winehq-${UBUNTU_CODENAME}.sources" \
    -o "/etc/apt/sources.list.d/winehq-${UBUNTU_CODENAME}.sources"

echo "[wine] Installing Wine stable..."
apt-get update -qq
apt-get install -y --install-recommends winehq-stable

echo "[wine] Done."
