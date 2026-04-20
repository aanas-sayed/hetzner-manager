#!/usr/bin/env bash
# Install: Ollama
# Usage: bash ollama.sh <username>
set -euo pipefail

USERNAME="${1:?Usage: $0 <username>}"

echo "[ollama] Installing Ollama via official script..."
curl -fsSL https://ollama.com/install.sh | sh

echo "[ollama] Enabling and starting Ollama service..."
systemctl enable ollama
systemctl start ollama

echo "[ollama] Done."
