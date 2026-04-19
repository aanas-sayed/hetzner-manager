#!/usr/bin/env bash
# Install: uv (fast Python package/project manager)
# Usage: bash uv.sh <username>
set -euo pipefail

USERNAME="${1:?Usage: $0 <username>}"

echo "[uv] Installing uv to /usr/local/bin..."
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh

echo "[uv] Done. Version: $(uv --version)"
