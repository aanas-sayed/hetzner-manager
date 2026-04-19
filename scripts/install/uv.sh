#!/usr/bin/env bash
# Install: uv (fast Python package/project manager)
# Usage: bash uv.sh <username>
set -euo pipefail

USERNAME="${1:?Usage: $0 <username>}"

echo "[uv] Installing uv for $USERNAME..."
su - "$USERNAME" -c 'curl -LsSf https://astral.sh/uv/install.sh | sh'

echo "[uv] Linking uv to /usr/local/bin for system-wide access..."
UV_BIN="/home/$USERNAME/.local/bin/uv"
if [ -f "$UV_BIN" ]; then
    ln -sf "$UV_BIN" /usr/local/bin/uv
else
    # Fallback: root install location
    ln -sf /root/.local/bin/uv /usr/local/bin/uv 2>/dev/null || true
fi

echo "[uv] Adding uv to $USERNAME shell profile..."
su - "$USERNAME" -c 'echo "export PATH=\"\$HOME/.local/bin:\$PATH\"" >> ~/.bashrc'

echo "[uv] Done. Version: $(uv --version 2>/dev/null || echo 'check after login')"
