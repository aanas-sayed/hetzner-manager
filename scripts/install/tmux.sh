#!/usr/bin/env bash
# Install: tmux
# Usage: bash tmux.sh <username>
set -euo pipefail

USERNAME="${1:?Usage: $0 <username>}"

echo "[tmux] Installing tmux..."
apt-get install -y tmux

echo "[tmux] Done. Version: $(tmux -V)"
