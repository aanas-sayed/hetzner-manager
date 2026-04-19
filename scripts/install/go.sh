#!/usr/bin/env bash
# Install: Go (latest stable)
# Usage: bash go.sh <username>
set -euo pipefail

USERNAME="${1:?Usage: $0 <username>}"

echo "[go] Fetching latest Go version..."
GO_VERSION=$(curl -fsSL "https://go.dev/VERSION?m=text" | head -1)

if [ -z "$GO_VERSION" ]; then
    echo "[go] ERROR: Could not determine latest Go version."
    exit 1
fi

echo "[go] Installing $GO_VERSION..."

# Detect architecture
ARCH=$(uname -m)
case "$ARCH" in
    x86_64)  GOARCH="amd64" ;;
    aarch64) GOARCH="arm64" ;;
    armv6l)  GOARCH="armv6l" ;;
    *)
        echo "[go] ERROR: Unsupported architecture: $ARCH"
        exit 1
        ;;
esac

TARBALL="${GO_VERSION}.linux-${GOARCH}.tar.gz"
URL="https://dl.google.com/go/${TARBALL}"

echo "[go] Downloading $URL..."
curl -fsSL "$URL" | tar -C /usr/local -xzf -

echo "[go] Adding Go to system PATH..."
cat > /etc/profile.d/go.sh << 'EOF'
export PATH=$PATH:/usr/local/go/bin
export GOPATH=$HOME/go
export PATH=$PATH:$GOPATH/bin
EOF
chmod +x /etc/profile.d/go.sh

echo "[go] Adding Go to $USERNAME profile..."
su - "$USERNAME" -c "echo 'source /etc/profile.d/go.sh' >> ~/.bashrc"

echo "[go] Done. Version: $(/usr/local/go/bin/go version)"
