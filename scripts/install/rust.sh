#!/usr/bin/env bash
# Install: Rust via rustup
# Usage: bash rust.sh <username>
set -euo pipefail

USERNAME="${1:?Usage: $0 <username>}"

echo "[rust] Installing Rust via rustup for $USERNAME..."
su - "$USERNAME" -c 'curl -fsSL https://sh.rustup.rs | sh -s -- -y --no-modify-path'

echo "[rust] Adding cargo to PATH..."
cat > /etc/profile.d/rust.sh << 'EOF'
export PATH=$PATH:$HOME/.cargo/bin
EOF
chmod +x /etc/profile.d/rust.sh

su - "$USERNAME" -c "echo 'source \$HOME/.cargo/env' >> ~/.bashrc"

echo "[rust] Done. Version: $(su - "$USERNAME" -c 'source $HOME/.cargo/env && rustc --version')"
