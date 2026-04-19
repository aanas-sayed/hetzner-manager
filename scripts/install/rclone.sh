#!/usr/bin/env bash
# Install: rclone
# Usage: bash rclone.sh <username>
set -euo pipefail

USERNAME="${1:?Usage: $0 <username>}"

echo "[rclone] Installing rclone via official script..."
curl -fsSL https://rclone.org/install.sh | bash

echo "[rclone] Done. Version: $(rclone --version | head -1)"
