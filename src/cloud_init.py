"""
Cloud-init user-data builder.
Generates a hardened cloud config following Hetzner's basic-cloud-config tutorial.

Install scripts live in scripts/install/*.sh — each accepts a single argument: username.
Metadata (display labels, apt pre-requisites) lives in scripts/install/meta.json.
Adding a new tool = drop a .sh file + one entry in meta.json. No Python changes needed.
"""

import json
import sys
from pathlib import Path
from typing import Optional


# ── Script discovery ───────────────────────────────────────────────────────────

def _scripts_dir() -> Path:
    # sys._MEIPASS is set by PyInstaller (both --onefile and --onedir) and points
    # to where bundled data files live. In --onedir mode (PyInstaller 6+) this is
    # the _internal/ subdirectory, not the directory containing the executable.
    if getattr(sys, "frozen", False):
        return Path(sys._MEIPASS) / "scripts" / "install"
    return Path(__file__).parent.parent / "scripts" / "install"

SCRIPTS_DIR = _scripts_dir()


def _load_meta() -> dict:
    meta_path = SCRIPTS_DIR / "meta.json"
    if meta_path.exists():
        return json.loads(meta_path.read_text())
    return {}


def _load_script(key: str) -> Optional[str]:
    """Read a .sh script by key name. Returns None if not found."""
    path = SCRIPTS_DIR / f"{key}.sh"
    if path.exists():
        return path.read_text()
    return None


def get_install_options() -> list[dict]:
    """
    Return all available install options, discovered from scripts/install/*.sh.
    Each entry: {key, label, apt_packages}.
    Ordered to match meta.json key order, with unlisted scripts appended.
    """
    meta = _load_meta()
    available_scripts = {p.stem for p in SCRIPTS_DIR.glob("*.sh")}

    options = []
    # Respect meta.json ordering first
    for key, info in meta.items():
        if key in available_scripts:
            options.append({
                "key": key,
                "label": info.get("label", key),
                "apt_packages": info.get("apt_packages", []),
            })

    # Append any .sh scripts not listed in meta.json
    listed = {o["key"] for o in options}
    for key in sorted(available_scripts - listed):
        options.append({"key": key, "label": key, "apt_packages": []})

    return options


# ── Cloud-config builder ───────────────────────────────────────────────────────

def build_cloud_config(
    username: str,
    ssh_public_keys: list[str],
    packages_to_install: list[str],
) -> str:
    """
    Build a complete cloud-init #cloud-config YAML document.

    Args:
        username: The non-root user to create.
        ssh_public_keys: List of SSH public key strings.
        packages_to_install: List of script keys from scripts/install/.
    """

    meta = _load_meta()

    # ── Collect apt packages ────────────────────────────────────────────────
    base_packages = [
        "ca-certificates",
        "curl",
        "fail2ban",
        "gnupg",
        "htop",
        "lsb-release",
        "rsync",
        "tar",
        "unattended-upgrades",
        "ufw",
        "vim",
        "wget",
        "zstd",
    ]
    extra_packages = []
    for key in packages_to_install:
        extra_packages.extend(meta.get(key, {}).get("apt_packages", []))

    all_packages = sorted(set(base_packages + extra_packages))

    # ── Load and embed install scripts via write_files ──────────────────────
    write_files_blocks = []
    scripts_to_run = []

    for key in packages_to_install:
        script_content = _load_script(key)
        if script_content is None:
            continue

        remote_path = f"/opt/install/{key}.sh"

        # Indent script content for YAML block scalar (6 spaces)
        indented = "\n".join(
            "      " + line if line else ""
            for line in script_content.splitlines()
        )

        write_files_blocks.append(
            f"  - path: {remote_path}\n"
            f"    permissions: '0755'\n"
            f"    owner: root:root\n"
            f"    content: |\n"
            f"{indented}"
        )

        scripts_to_run.append((key, remote_path))

    # ── Format YAML sections ────────────────────────────────────────────────
    ssh_keys_yaml = "\n".join(f"    - {k}" for k in ssh_public_keys)
    packages_yaml = "\n".join(f"  - {p}" for p in all_packages)
    write_files_yaml = "\n".join(write_files_blocks)

    # ── runcmd ───────────────────────────────────────────────────────────────
    runcmd_lines = [
        "  - timedatectl set-timezone UTC",
        "",
        "  # Firewall",
        "  - ufw default deny incoming",
        "  - ufw default allow outgoing",
        "  - \"ufw allow 22/tcp comment 'SSH'\"",
        "  - ufw --force enable",
        "",
        "  # Fail2ban",
        "  - systemctl enable fail2ban",
        "  - systemctl start fail2ban",
        "",
        "  # Automatic security updates",
        "  - dpkg-reconfigure -f noninteractive unattended-upgrades",
        "",
        "  # SSH hardening",
        "  - \"sed -i 's/^#*PermitRootLogin.*/PermitRootLogin prohibit-password/' /etc/ssh/sshd_config\"",
        "  - \"sed -i 's/^#*PasswordAuthentication.*/PasswordAuthentication no/' /etc/ssh/sshd_config\"",
        "  - \"sed -i 's/^#*ChallengeResponseAuthentication.*/ChallengeResponseAuthentication no/' /etc/ssh/sshd_config\"",
        "  - systemctl reload sshd",
        "",
        "  # Kernel hardening",
        "  - sysctl -p /etc/sysctl.d/99-hardening.conf",
        "",
        f"  # Workspace directory",
        f"  - mkdir -p /home/{username}/workspace",
        f"  - chown -R {username}:{username} /home/{username}/workspace",
        "  - mkdir -p /opt/install",
    ]

    if scripts_to_run:
        runcmd_lines += ["", "  # Software installs"]
        for key, remote_path in scripts_to_run:
            runcmd_lines.append(f"  - bash {remote_path} {username}")

    runcmd_lines += [
        "",
        "  # Mark setup complete",
        f"  - \"echo 'setup_done' > /home/{username}/workspace/.setup_done\"",
    ]

    runcmd_yaml = "\n".join(runcmd_lines)

    # ── Assemble full cloud-config ────────────────────────────────────────────
    write_files_section = f"\n{write_files_yaml}\n" if write_files_yaml else ""

    cloud_config = f"""\
#cloud-config

# ── Users ─────────────────────────────────────────────────────────────────────
users:
  - name: {username}
    groups: sudo
    shell: /bin/bash
    sudo: ALL=(ALL) NOPASSWD:ALL
    lock_passwd: true
    ssh_authorized_keys:
{ssh_keys_yaml}

disable_root: false

# ── Packages ──────────────────────────────────────────────────────────────────
package_update: true
package_upgrade: true

packages:
{packages_yaml}

# ── Write files ───────────────────────────────────────────────────────────────
write_files:
  - path: /etc/fail2ban/jail.local
    owner: root:root
    permissions: '0644'
    content: |
      [DEFAULT]
      bantime  = 3600
      findtime = 600
      maxretry = 5

      [sshd]
      enabled  = true
      port     = ssh
      filter   = sshd
      logpath  = /var/log/auth.log
      maxretry = 3

  - path: /etc/sysctl.d/99-hardening.conf
    owner: root:root
    permissions: '0644'
    content: |
      net.ipv4.conf.all.rp_filter = 1
      net.ipv4.conf.default.rp_filter = 1
      net.ipv4.icmp_echo_ignore_broadcasts = 1
      net.ipv4.conf.all.accept_source_route = 0
      net.ipv4.conf.all.send_redirects = 0
      net.ipv4.tcp_syncookies = 1
      net.ipv4.tcp_max_syn_backlog = 2048
      net.ipv4.tcp_synack_retries = 2
      net.ipv4.tcp_syn_retries = 5
      net.ipv6.conf.all.accept_redirects = 0
{write_files_section}
# ── Run commands ──────────────────────────────────────────────────────────────
runcmd:
{runcmd_yaml}

# ── Final message ─────────────────────────────────────────────────────────────
final_message: |
  Hetzner workspace provisioning complete!
  User: {username}
  Workspace: /home/{username}/workspace
"""
    return cloud_config
