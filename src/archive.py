"""
Archive and restore workspace data.
Compresses the remote ~/workspace directory using tar+zstd,
downloads it locally, and stores metadata in the state registry.
"""

import os
import shlex
import subprocess
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from src import log as _log, state, ssh_config
from src.ui import info, success, error, warn


def _run(cmd: list[str], check: bool = True, capture: bool = False) -> subprocess.CompletedProcess:
    if _log.DRY_RUN:
        _log.dry_cmd(cmd)
        return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
    _log.get().debug("run: %s", " ".join(shlex.quote(c) for c in cmd))
    kwargs = {"check": check}
    if capture:
        kwargs["capture_output"] = True
        kwargs["text"] = True
    return subprocess.run(cmd, **kwargs)


def create_archive(
    server_name: str,
    server_info: dict,
    archive_name: str,
    local_archive_dir: Path,
) -> Optional[Path]:
    """
    SSH into the server, tar+zstd the workspace, download it, and register it.
    Returns the local archive path on success.
    """
    username = server_info.get("username", "ubuntu")
    hostname = server_info.get("ipv6_address") or server_info.get("hostname")
    
    # Determine identity file
    id_file = server_info.get("identity_file")
    
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    remote_filename = f"workspace_{archive_name}_{timestamp}.tar.zst"
    remote_path = f"/tmp/{remote_filename}"

    # Build SSH base command
    ssh_base = ["ssh", "-o", "StrictHostKeyChecking=accept-new"]
    if id_file:
        ssh_base += ["-i", id_file]
    ssh_target = f"{username}@{hostname}" if ":" in str(hostname) else f"{username}@{hostname}"

    # Use server name alias if SSH config entry exists
    if ssh_config.entry_exists(server_name):
        ssh_target = server_name

    info(f"Creating archive on remote server...")
    try:
        _run(ssh_base + [ssh_target,
            f"tar -cf - -C /home/{username} workspace | zstd -T0 -3 -o {remote_path}"
        ])
    except subprocess.CalledProcessError as e:
        error(f"Failed to create archive on remote: {e}")
        return None

    local_filename = f"{archive_name}_{timestamp}.tar.zst"
    local_path = local_archive_dir / local_filename

    info(f"Downloading archive to {local_path}...")
    try:
        if ssh_config.entry_exists(server_name):
            _run(["scp", f"{server_name}:{remote_path}", str(local_path)])
        else:
            scp_src = f"{ssh_target}:{remote_path}"
            scp_cmd = ["scp", "-o", "StrictHostKeyChecking=accept-new"]
            if id_file:
                scp_cmd += ["-i", id_file]
            scp_cmd += [scp_src, str(local_path)]
            _run(scp_cmd)
    except subprocess.CalledProcessError as e:
        error(f"Failed to download archive: {e}")
        return None

    # Cleanup remote
    try:
        _run(ssh_base + [ssh_target, f"rm -f {remote_path}"])
    except subprocess.CalledProcessError:
        warn("Could not remove remote temp file (non-fatal).")

    # Get size
    size_bytes = local_path.stat().st_size if local_path.exists() else 0
    size_mb = size_bytes / (1024 * 1024)

    success(f"Archive saved: {local_path} ({size_mb:.1f} MB)")
    return local_path


def restore_archive_path(archive_name: str) -> Optional[Path]:
    """Return the local path for a named archive."""
    info = state.get_archive(archive_name)
    if not info:
        return None
    p = Path(info.get("local_path", ""))
    return p if p.exists() else None


def get_archive_cloud_init_snippet(local_path: Path, username: str) -> list[str]:
    """
    Returns runcmd lines to restore a workspace archive that was uploaded
    as a multipart via cloud-init (for small archives).
    For large archives, we recommend manual rsync after provisioning.
    """
    size_mb = local_path.stat().st_size / (1024 * 1024) if local_path.exists() else 0
    if size_mb > 50:
        return [
            f"# Archive too large for cloud-init inline ({size_mb:.0f}MB). Use post-provision restore.",
        ]
    # For small archives, just note path for post-provision copy
    return []


def list_local_archives() -> list[dict]:
    """List all archives registered in state."""
    return list(state.list_archives().values())
