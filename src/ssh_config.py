"""
SSH config manager.
Adds and removes Host entries from ~/.ssh/config with agent forwarding.
"""

import os
import re
from pathlib import Path
from typing import Optional


SSH_CONFIG_PATH = Path.home() / ".ssh" / "config"
BLOCK_START = "# BEGIN hetzner-workspace: {name}"
BLOCK_END = "# END hetzner-workspace: {name}"


def _read_config() -> str:
    if SSH_CONFIG_PATH.exists():
        return SSH_CONFIG_PATH.read_text()
    return ""


def _write_config(content: str) -> None:
    SSH_CONFIG_PATH.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    SSH_CONFIG_PATH.write_text(content)
    SSH_CONFIG_PATH.chmod(0o600)


def build_entry(
    name: str,
    hostname: str,
    username: str,
    identity_file: Optional[str] = None,
    port: int = 22,
) -> str:
    """Build an SSH config Host entry block."""
    lines = [
        BLOCK_START.format(name=name),
        f"Host {name}",
        f"    HostName {hostname}",
        f"    User {username}",
        f"    Port {port}",
        "    ForwardAgent yes",
        "    ServerAliveInterval 60",
        "    ServerAliveCountMax 3",
        "    StrictHostKeyChecking accept-new",
    ]
    if identity_file:
        lines.append(f"    IdentityFile {identity_file}")
    lines.append(BLOCK_END.format(name=name))
    lines.append("")  # trailing newline
    return "\n".join(lines)


def add_entry(
    name: str,
    hostname: str,
    username: str,
    identity_file: Optional[str] = None,
    port: int = 22,
) -> bool:
    """
    Add an SSH config entry. Returns True if added, False if already exists.
    """
    current = _read_config()
    marker = BLOCK_START.format(name=name)
    if marker in current:
        # Update existing
        remove_entry(name)
        current = _read_config()

    entry = build_entry(name, hostname, username, identity_file, port)
    # Ensure file ends with newline before appending
    if current and not current.endswith("\n"):
        current += "\n"
    current += "\n" + entry
    _write_config(current)
    return True


def remove_entry(name: str) -> bool:
    """Remove an SSH config entry by name. Returns True if found and removed."""
    current = _read_config()
    start = BLOCK_START.format(name=name)
    end = BLOCK_END.format(name=name)

    if start not in current:
        return False

    # Remove from start marker to end marker (inclusive), plus surrounding blank lines
    pattern = rf"\n?{re.escape(start)}.*?{re.escape(end)}\n?"
    updated = re.sub(pattern, "\n", current, flags=re.DOTALL)
    _write_config(updated)
    return True


def entry_exists(name: str) -> bool:
    return BLOCK_START.format(name=name) in _read_config()


def remove_known_host(hostname: str) -> None:
    """Remove a hostname from ~/.ssh/known_hosts to prevent stale key errors."""
    known_hosts = Path.home() / ".ssh" / "known_hosts"
    if not known_hosts.exists():
        return
    content = known_hosts.read_text()
    lines = [l for l in content.splitlines() if not l.startswith(hostname)]
    known_hosts.write_text("\n".join(lines) + "\n")


def get_local_ssh_public_keys() -> list[dict]:
    """Discover all SSH public keys in ~/.ssh/."""
    ssh_dir = Path.home() / ".ssh"
    keys = []
    for path in sorted(ssh_dir.glob("*.pub")):
        try:
            content = path.read_text().strip()
            if content:
                keys.append({
                    "path": str(path),
                    "name": path.stem,
                    "key": content,
                    "fingerprint": _key_fingerprint(content),
                })
        except OSError:
            pass
    return keys


def _key_fingerprint(pubkey: str) -> str:
    """Return a short display fingerprint for a public key."""
    parts = pubkey.split()
    if len(parts) >= 2:
        comment = parts[2] if len(parts) >= 3 else ""
        prefix = parts[1][:16] + "..." if len(parts[1]) > 16 else parts[1]
        return f"{parts[0]} {prefix} {comment}".strip()
    return pubkey[:40] + "..."
