#!/usr/bin/env bash
# Install: act (run GitHub Actions locally)
# Usage: bash act.sh <username>
set -euo pipefail

USERNAME="${1:?Usage: $0 <username>}"

echo "[act] Fetching latest act release..."
ARCH=$(uname -m)
case "$ARCH" in
    x86_64)  ACT_ARCH="x86_64" ;;
    aarch64) ACT_ARCH="arm64" ;;
    *)
        echo "[act] ERROR: Unsupported architecture: $ARCH"
        exit 1
        ;;
esac

VERSION=$(curl -fsSL "https://api.github.com/repos/nektos/act/releases/latest" \
    | grep '"tag_name"' | head -1 | cut -d'"' -f4)

if [ -z "$VERSION" ]; then
    echo "[act] ERROR: Could not determine latest act version."
    exit 1
fi

echo "[act] Installing act $VERSION..."
TARBALL="act_Linux_${ACT_ARCH}.tar.gz"
URL="https://github.com/nektos/act/releases/download/${VERSION}/${TARBALL}"

curl -fsSL "$URL" | tar -C /usr/local/bin -xzf - act

chmod +x /usr/local/bin/act

echo "[act] Done. Version: $(act --version)"
