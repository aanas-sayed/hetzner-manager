#!/usr/bin/env sh
# Install hw (Hetzner Workspace Manager)
# Usage: curl -fsSL https://raw.githubusercontent.com/aanas-sayed/hetzner-manager/main/install.sh | sh
set -eu

REPO="aanas-sayed/hetzner-manager"
INSTALL_DIR="${HW_INSTALL_DIR:-$HOME/.local/lib/hw}"
BIN_DIR="${HW_BIN_DIR:-$HOME/.local/bin}"

# ── Detect OS ─────────────────────────────────────────────────────────────────

OS=$(uname -s | tr '[:upper:]' '[:lower:]')
case "$OS" in
    linux)  ;;
    darwin) ;;
    *)
        echo "Unsupported OS: $OS"
        exit 1
        ;;
esac

# ── Detect arch ───────────────────────────────────────────────────────────────

ARCH=$(uname -m)
case "$ARCH" in
    x86_64)        ARCH="x86_64" ;;
    arm64|aarch64) ARCH="arm64" ;;
    *)
        echo "Unsupported architecture: $ARCH"
        exit 1
        ;;
esac

# ── Fetch latest version ──────────────────────────────────────────────────────

VERSION=$(curl -fsSL "https://api.github.com/repos/${REPO}/releases/latest" \
    | grep '"tag_name"' | head -1 | cut -d'"' -f4)

if [ -z "$VERSION" ]; then
    echo "Could not determine latest release version."
    exit 1
fi

# ── Download & extract ────────────────────────────────────────────────────────

FILENAME="hw-${VERSION}-${OS}-${ARCH}.tar.gz"
URL="https://github.com/${REPO}/releases/download/${VERSION}/${FILENAME}"

echo "Installing hw ${VERSION} (${OS}/${ARCH})..."

TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT

curl -fsSL "$URL" -o "$TMP/$FILENAME"
tar -xzf "$TMP/$FILENAME" -C "$TMP"

# ── Install ───────────────────────────────────────────────────────────────────

rm -rf "$INSTALL_DIR"
mkdir -p "$INSTALL_DIR" "$BIN_DIR"
cp -r "$TMP/hw/." "$INSTALL_DIR/"
chmod +x "$INSTALL_DIR/hw"
ln -sf "$INSTALL_DIR/hw" "$BIN_DIR/hw"

# ── Done ──────────────────────────────────────────────────────────────────────

echo ""
echo "hw ${VERSION} installed to $BIN_DIR/hw"
echo ""

if ! echo ":$PATH:" | grep -q ":$BIN_DIR:"; then
    echo "Add $BIN_DIR to your PATH:"
    echo "  export PATH=\"\$HOME/.local/bin:\$PATH\""
    echo ""
fi

echo "Run: hw"
