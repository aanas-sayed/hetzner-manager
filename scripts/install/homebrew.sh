#!/usr/bin/env bash
# Install: Homebrew (Linuxbrew)
# Usage: bash homebrew.sh <username>
set -euo pipefail

USERNAME="${1:?Usage: $0 <username>}"

echo "[homebrew] Installing dependencies..."
apt-get install -y build-essential procps curl file git

echo "[homebrew] Installing Homebrew as $USERNAME..."
su - "$USERNAME" -c \
    'NONINTERACTIVE=1 /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"'

echo "[homebrew] Adding brew to $USERNAME shell profile..."
# Homebrew on Linux installs to ~/.linuxbrew or /home/linuxbrew/.linuxbrew
BREW_PATHS=(
    "/home/$USERNAME/.linuxbrew/bin/brew"
    "/home/linuxbrew/.linuxbrew/bin/brew"
    "/usr/local/bin/brew"
)
for BREW_BIN in "${BREW_PATHS[@]}"; do
    if [ -f "$BREW_BIN" ]; then
        su - "$USERNAME" -c "echo 'eval \"\$(${BREW_BIN} shellenv)\"' >> ~/.bashrc"
        su - "$USERNAME" -c "echo 'eval \"\$(${BREW_BIN} shellenv)\"' >> ~/.profile"
        echo "[homebrew] Brew shellenv added from $BREW_BIN"
        break
    fi
done

echo "[homebrew] Done."
