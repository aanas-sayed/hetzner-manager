"""
Main CLI entry point.
Four workflows: create, archive, restore, delete.
"""

import argparse
import shlex
import sys
import os
import time
import subprocess
from pathlib import Path
from typing import Optional

from src import log as _log, state, ssh_config, archive as archive_mod
from src.hetzner import get_client, HetznerAPIError
from src.cloud_init import build_cloud_config, get_install_options
from src.ui import (
    print_header, print_rule, info, success, error, warn, dim, blank,
    prompt_input, prompt_confirm, choose_from_list, choose_from_table, choose_multiple,
    print_table, print_key_value, print_code, spinner_context,
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _fmt_price(price_str) -> str:
    try:
        return f"€{float(price_str):.4f}/hr"
    except (TypeError, ValueError):
        return str(price_str)


def _pick_best_location(client, server_type_name: str) -> Optional[dict]:
    """
    Auto-select: cheapest location for the given server type.
    Hetzner prices are usually the same across locations but we pick
    the one with most availability.  Strategy: prefer HEL (Helsinki) or 
    FSN (Falkenstein) as they often have the widest catalog, then NBG.
    """
    locations = client.get_locations()
    # Priority order for lowest-cost / most available regions
    PRIORITY = ["hel1", "fsn1", "nbg1", "ash", "hil", "sin"]
    loc_map = {l["name"]: l for l in locations}
    for p in PRIORITY:
        if p in loc_map:
            return loc_map[p]
    return locations[0] if locations else None


def _wait_for_server(client, server_id: int, timeout: int = 300) -> dict:
    """Poll until server is running."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        srv = client.get_server(server_id)
        status = srv.get("status", "")
        if status == "running":
            return srv
        if status == "error":
            raise RuntimeError(f"Server entered error state during provisioning.")
        time.sleep(5)
    raise TimeoutError(f"Server did not become 'running' within {timeout}s.")


def _get_ssh_keys_from_account(client) -> list[dict]:
    try:
        return client.get_ssh_keys()
    except HetznerAPIError:
        return []


def _get_local_ssh_keys() -> list[dict]:
    return ssh_config.get_local_ssh_public_keys()


def _select_ssh_keys(client, default_identity_file: Optional[str] = None) -> tuple[list[str], Optional[str]]:
    """
    Let user pick SSH keys to install on the server.
    Returns (list_of_pubkey_strings, identity_file_path_or_None).
    """
    print_rule("SSH Key Selection")
    account_keys = _get_ssh_keys_from_account(client)
    local_keys = _get_local_ssh_keys()

    chosen_pubkeys: list[str] = []
    identity_file: Optional[str] = None

    if account_keys:
        info(f"Found {len(account_keys)} SSH key(s) on your Hetzner account.")
        use_account = prompt_confirm("Use all Hetzner account SSH keys?", default=True)
        if use_account:
            chosen_pubkeys = [k["public_key"] for k in account_keys]
        else:
            selected = choose_multiple(
                account_keys,
                "Select which account keys to install (comma-separated numbers):",
                display_fn=lambda k: f"{k['name']}  [dim]{k.get('fingerprint', '')}[/dim]",
            )
            chosen_pubkeys = [k["public_key"] for k in selected]

    if not chosen_pubkeys and local_keys:
        info("No account keys selected. Checking local SSH public keys...")
        selected = choose_multiple(
            local_keys,
            "Select local public keys to install:",
            display_fn=lambda k: f"{k['name']}  ({k['fingerprint']})",
        )
        chosen_pubkeys = [k["key"] for k in selected]
        if selected:
            identity_file = selected[0]["path"].replace(".pub", "")

    if not chosen_pubkeys:
        warn("No SSH keys selected. You may not be able to log in!")
        manual = prompt_input("Paste a public key manually (or press Enter to skip)").strip()
        if manual:
            chosen_pubkeys = [manual]

    # Offer to pick identity file for SSH config
    if local_keys and identity_file is None:
        skip_entry = {"name": "Skip — let SSH try keys automatically", "path": None}
        options = local_keys + [skip_entry]

        # Pre-select default based on saved config
        default_idx = None
        if default_identity_file:
            for i, k in enumerate(local_keys):
                if k.get("path", "").replace(".pub", "") == default_identity_file:
                    default_idx = i + 1  # 1-based
                    break

        label = "Which local key matches your Hetzner account key? (sets IdentityFile in SSH config)"

        chosen_key = choose_from_list(
            options,
            label,
            display_fn=lambda k: k["name"] + (f"  [dim]{k.get('path', '')}[/dim]" if k.get("path") else ""),
            default_idx=default_idx,
        )
        if chosen_key and chosen_key.get("path"):
            identity_file = chosen_key["path"].replace(".pub", "")

    return chosen_pubkeys, identity_file


# ─────────────────────────────────────────────────────────────────────────────
# Workflow: CREATE
# ─────────────────────────────────────────────────────────────────────────────

def workflow_create(client, restore_from: Optional[str] = None):
    print_header(
        "Create Workspace",
        "Provision a new Hetzner cloud server with your configuration",
    )

    # ── 0. Optionally load a saved config ────────────────────────────────────
    saved_configs = state.list_configs()
    loaded_config: Optional[dict] = None
    if saved_configs:
        use_config = prompt_confirm("Load a saved config?", default=True)
        if use_config:
            config_items = [{"name": k, **v} for k, v in saved_configs.items()]
            chosen_cfg = choose_from_list(
                config_items,
                "Choose a config:",
                display_fn=lambda c: (
                    f"[bold]{c['name']}[/bold]  "
                    f"[dim]{c.get('server_type','?')} · {c.get('image','?')} · "
                    f"user={c.get('username','?')} · "
                    f"install=[{', '.join(c.get('install', []))}][/dim]"
                ),
            )
            if chosen_cfg:
                loaded_config = chosen_cfg

    # ── 1. Pick server type ──────────────────────────────────────────────────
    print_rule("Server Selection")
    info("Fetching available server types...")

    try:
        server_types = client.get_server_types()
    except HetznerAPIError as e:
        error(f"Could not fetch server types: {e}")
        sys.exit(1)

    # Filter out deprecated
    server_types = [s for s in server_types if not s.get("deprecation")]

    # Sort: cheapest first by hourly gross price, then by name
    def _hourly(st):
        try:
            prices = st.get("prices", [])
            for p in prices:
                if p.get("location") in ("hel1", "fsn1", "nbg1", ""):
                    gross = p.get("price_hourly", {}).get("gross", "9999")
                    return float(gross)
            if prices:
                return float(prices[0].get("price_hourly", {}).get("gross", 9999))
        except (TypeError, ValueError):
            pass
        return 9999.0

    server_types.sort(key=_hourly)

    # Build table rows
    def _tier_label(st) -> str:
        name = st.get("name", "")
        cpu_type = st.get("cpu_type", "shared")
        if name.startswith("cax"):
            return "Arm64", "[white]shared[/white]"
        if name.startswith("cpx"):
            return "AMD", "[yellow]shared-perf[/yellow]"
        if name.startswith("ccx"):
            return "AMD", "[bold green]dedicated[/bold green]"
        tier = "dedicated" if cpu_type == "dedicated" else "shared"
        tier_markup = "[bold green]dedicated[/bold green]" if tier == "dedicated" else "[white]shared[/white]"
        return "Intel/AMD", tier_markup

    def _server_type_row(st):
        vendor, tier = _tier_label(st)
        price = _hourly(st)
        price_str = f"[green]€{price:.4f}[/green]" if price < 9999 else "?"
        return [
            f"[bold]{st['name']}[/bold]",
            f"[cyan]{st.get('cores', '?')}[/cyan]",
            vendor,
            tier,
            f"[cyan]{st.get('memory', '?')}[/cyan]",
            f"[dim]{st.get('disk', '?')}[/dim]",
            price_str,
        ]

    if loaded_config:
        chosen_type = next(
            (s for s in server_types if s["name"] == loaded_config.get("server_type")), None
        )
        if not chosen_type:
            warn(f"Saved server type '{loaded_config.get('server_type')}' not available — please choose manually.")
            chosen_type = choose_from_table(
                server_types,
                "Choose a server type (sorted by price, cheapest first):",
                headers=["Name", "vCPU", "CPU", "Tier", "RAM (GB)", "Disk (GB)", "€/hr"],
                row_fn=_server_type_row,
            )
        else:
            info(f"Server type: [bold]{chosen_type['name']}[/bold] (from config)")
    else:
        chosen_type = choose_from_table(
            server_types,
            "Choose a server type (sorted by price, cheapest first):",
            headers=["Name", "vCPU", "CPU", "Tier", "RAM (GB)", "Disk (GB)", "€/hr"],
            row_fn=_server_type_row,
        )
    if not chosen_type:
        sys.exit(1)

    # ── 2. Auto-select location ──────────────────────────────────────────────
    print_rule("Location")
    location = _pick_best_location(client, chosen_type["name"])
    if location:
        info(f"Auto-selected location: [bold]{location['name']}[/bold] ({location.get('description', '')})")
    else:
        error("No locations available.")
        sys.exit(1)

    # ── 3. Choose base image ─────────────────────────────────────────────────
    print_rule("Base Image")
    info("Fetching available images...")
    try:
        images = client.get_images(image_type="system")
    except HetznerAPIError as e:
        error(f"Could not fetch images: {e}")
        sys.exit(1)

    # Filter by exact architecture match for the chosen server type
    arch = chosen_type.get("architecture", "x86")
    images = [
        img for img in images
        if not img.get("deprecated")
        and img.get("architecture", "x86") == arch
    ]

    # Sort: Ubuntu first, then alphabetically by name
    def _img_sort(img):
        name = img.get("name", "")
        return f"0_{name}" if name.startswith("ubuntu") else f"1_{name}"

    images.sort(key=_img_sort)

    def _image_row(img):
        name = img.get("name", "?")
        desc = img.get("description", "")
        img_arch = img.get("architecture", "x86")
        size = img.get("disk_size", "?")
        arch_label = "[cyan]arm64[/cyan]" if img_arch == "arm" else "[dim]x86[/dim]"
        return [f"[bold]{name}[/bold]", desc, arch_label, f"{size} GB"]

    _image_headers = ["Name", "Description", "Arch", "Disk"]

    if loaded_config:
        chosen_image = next(
            (img for img in images if img["name"] == loaded_config.get("image")), None
        )
        if not chosen_image:
            warn(f"Saved image '{loaded_config.get('image')}' not available — please choose manually.")
            chosen_image = choose_from_table(images, "Choose a base image:", headers=_image_headers, row_fn=_image_row)
        else:
            info(f"Image: [bold]{chosen_image['name']}[/bold] (from config)")
    else:
        chosen_image = choose_from_table(images, "Choose a base image:", headers=_image_headers, row_fn=_image_row)
    if not chosen_image:
        sys.exit(1)

    # ── 4. SSH Keys ──────────────────────────────────────────────────────────
    pubkeys, identity_file = _select_ssh_keys(
        client,
        default_identity_file=loaded_config.get("identity_file") if loaded_config else None,
    )

    # Look up Hetzner account SSH key IDs for the chosen pubkeys
    account_keys = _get_ssh_keys_from_account(client)
    account_key_ids = []
    for pk in pubkeys:
        for ak in account_keys:
            if ak["public_key"].strip() == pk.strip():
                account_key_ids.append(ak["id"])
                break

    # ── 5. Username ──────────────────────────────────────────────────────────
    print_rule("User Configuration")
    default_user = loaded_config.get("username", "ubuntu") if loaded_config else "ubuntu"
    username = prompt_input("Default username", default=default_user).strip() or default_user

    # ── 6. Restore from archive? ─────────────────────────────────────────────
    restore_archive_path: Optional[Path] = None
    if restore_from:
        restore_archive_path = archive_mod.restore_archive_path(restore_from)
        if restore_archive_path:
            success(f"Will restore workspace from: {restore_archive_path}")
        else:
            warn(f"Archive '{restore_from}' not found locally. Skipping restore.")

    # ── 7. Software to install ───────────────────────────────────────────────
    print_rule("Software Installation")

    all_options = get_install_options()

    if loaded_config:
        saved_keys = set(loaded_config.get("install", []))
        pre_selected = [o for o in all_options if o["key"] in saved_keys]
        info(f"Software from config: [bold]{', '.join(saved_keys) if saved_keys else 'none'}[/bold]")
        if prompt_confirm("Use this software selection?", default=True):
            install_keys = list(saved_keys)
        else:
            selected_software = choose_multiple(
                all_options,
                "Select software to install (comma-separated numbers, or Enter to skip all):",
                display_fn=lambda x: f"{x['label']}  [dim]({x['key']})[/dim]",
            )
            install_keys = [s["key"] for s in selected_software]
    else:
        selected_software = choose_multiple(
            all_options,
            "Select software to install (comma-separated numbers, or Enter to skip all):",
            display_fn=lambda x: f"{x['label']}  [dim]({x['key']})[/dim]",
        )
        install_keys = [s["key"] for s in selected_software]

    # ── 8. Network ───────────────────────────────────────────────────────────
    print_rule("Network")
    default_ipv4 = loaded_config.get("enable_ipv4", True) if loaded_config else True
    warn(
        "IPv6-only servers cannot reach GitHub, AWS S3, or Docker Hub — "
        "tools like uv, act, rclone, and Docker image pulls may fail."
    )
    enable_ipv4 = prompt_confirm("Enable IPv4? (recommended)", default=default_ipv4)

    # ── 9. Config name ───────────────────────────────────────────────────────
    print_rule("Configuration")
    if loaded_config:
        default_config_name = loaded_config["name"]
        raw = prompt_input(
            "Config name (Enter to keep existing, or type a new name to save as copy, or '-' to skip saving)",
            default=default_config_name,
        ).strip()
        if raw == "-":
            config_name = None
        else:
            config_name = raw or default_config_name
    else:
        config_name = prompt_input("Save this configuration as (name)").strip()
        if not config_name:
            config_name = f"config_{int(time.time())}"

    # ── 9b. Server name ──────────────────────────────────────────────────────
    server_name = prompt_input("Server/SSH alias name").strip()
    if not server_name:
        server_name = f"workspace-{int(time.time())}"

    # ── 10. Preview & confirm ─────────────────────────────────────────────────
    blank()
    print_rule("Summary")
    print_key_value([
        ("Server type", f"{chosen_type['name']} ({chosen_type.get('cores')} vCPU, {chosen_type.get('memory')} GB RAM)"),
        ("Location", f"{location['name']} ({location.get('description', '')})"),
        ("Image", chosen_image.get("name", "?")),
        ("Username", username),
        ("Software", ", ".join(install_keys) if install_keys else "none"),
        ("SSH keys", f"{len(pubkeys)} key(s) selected"),
        ("Config name", config_name if config_name else "[dim]not saving[/dim]"),
        ("Server name", server_name),
        ("Network", "IPv4 + IPv6" if enable_ipv4 else "[yellow]IPv6 only[/yellow]"),
        ("Restore archive", str(restore_archive_path) if restore_archive_path else "none"),
    ])
    blank()

    if not prompt_confirm("Proceed with provisioning?", default=True):
        info("Aborted.")
        sys.exit(0)

    # ── 11. Build cloud-init ──────────────────────────────────────────────────
    user_data = build_cloud_config(
        username=username,
        ssh_public_keys=pubkeys,
        packages_to_install=install_keys,
    )

    # ── 12. Create server ─────────────────────────────────────────────────────
    info("Creating server on Hetzner...")

    payload = {
        "name": server_name,
        "server_type": chosen_type["name"],
        "image": chosen_image["name"],
        "location": location["name"],
        "user_data": user_data,
        "public_net": {
            "enable_ipv4": enable_ipv4,
            "enable_ipv6": True,
        },
        "start_after_create": True,
    }

    if account_key_ids:
        payload["ssh_keys"] = account_key_ids

    try:
        result = client.create_server(payload)
    except HetznerAPIError as e:
        error(f"Failed to create server: {e}")
        sys.exit(1)

    if _log.DRY_RUN:
        blank()
        print_rule("Dry-run — steps that would follow")
        _log.dry_action("poll until server status == running")
        _log.dry_action(f"add SSH config entry '{server_name}'")
        _log.dry_action(f"save config '{config_name}' to state")
        _log.dry_action("register server in state")
        if restore_archive_path:
            _log.dry_action(f"wait 60s for cloud-init, SCP {restore_archive_path.name}, extract")
        blank()
        return

    server = result.get("server", {})
    server_id = server.get("id")
    public_net = server.get("public_net", {})

    # Get IPv4 address
    ipv4_host = public_net.get("ipv4", {}).get("ip", "") if enable_ipv4 else ""

    # Get IPv6 address
    ipv6_network = public_net.get("ipv6", {})
    ipv6_address = ipv6_network.get("ip", "")
    if ipv6_address and "/" in ipv6_address:
        ipv6_prefix = ipv6_address.split("/")[0]
        ipv6_host = ipv6_prefix + "1" if ipv6_prefix.endswith("::") else ipv6_prefix
    else:
        ipv6_host = ipv6_address

    # Prefer IPv4 for SSH when available
    ssh_host = ipv4_host if ipv4_host else ipv6_host

    success(f"Server created! ID: {server_id}")
    if ipv4_host:
        info(f"IPv4: {ipv4_host}")
    info(f"IPv6: {ipv6_host}")
    info("Waiting for server to become ready (this may take 1-2 minutes)...")

    try:
        ready_server = _wait_for_server(client, server_id)
        success("Server is running!")
    except (RuntimeError, TimeoutError) as e:
        warn(f"Server status check failed: {e}. It may still be provisioning.")
        ready_server = server

    # ── 13. Update SSH config ─────────────────────────────────────────────────
    if ssh_host:
        info(f"Adding SSH config entry: [bold]{server_name}[/bold]")
        ssh_config.add_entry(
            name=server_name,
            hostname=ssh_host,
            username=username,
            identity_file=identity_file,
        )
        success(f"SSH config updated. Connect with: [bold]ssh {server_name}[/bold]")
    else:
        warn("Could not determine server IP. SSH config not updated.")

    # ── 14. Save config & register server ────────────────────────────────────
    config_data = {
        "server_type": chosen_type["name"],
        "location": location["name"],
        "image": chosen_image["name"],
        "username": username,
        "install": install_keys,
        "ssh_key_count": len(pubkeys),
        "identity_file": identity_file,
        "enable_ipv4": enable_ipv4,
    }
    if config_name:
        state.save_config(config_name, config_data)

    server_info = {
        "server_id": server_id,
        "name": server_name,
        "config_name": config_name,
        "username": username,
        "ipv4_address": ipv4_host,
        "ipv6_address": ipv6_host,
        "hostname": ssh_host,
        "identity_file": identity_file,
        "server_type": chosen_type["name"],
        "location": location["name"],
        "image": chosen_image["name"],
    }
    state.register_server(server_info)

    # ── 15. Restore archive if requested ─────────────────────────────────────
    if restore_archive_path and restore_archive_path.exists():
        blank()
        info("Waiting 60 seconds for cloud-init to complete before restoring archive...")
        time.sleep(60)
        _do_restore_archive(server_name, server_info, restore_archive_path, username)

    blank()
    print_rule("Done")
    addr_pairs = []
    if ipv4_host:
        addr_pairs.append(("IPv4", ipv4_host))
    addr_pairs.append(("IPv6", ipv6_host))
    print_key_value([
        ("Server", server_name),
        ("ID", str(server_id)),
        *addr_pairs,
        ("Connect", f"ssh {server_name}"),
        ("Config saved", config_name if config_name else "not saved"),
    ])
    blank()


def _do_restore_archive(server_name: str, server_info: dict, archive_path: Path, username: str):
    """SCP archive to server and extract it."""
    hostname = server_info.get("ipv6_address") or server_info.get("hostname")
    id_file = server_info.get("identity_file")

    ssh_opts = ["-o", "StrictHostKeyChecking=accept-new", "-o", "ConnectTimeout=10"]
    if id_file:
        ssh_opts += ["-i", id_file]

    target = server_name if ssh_config.entry_exists(server_name) else f"{username}@{hostname}"

    info(f"Copying archive to server...")
    scp_cmd = ["scp"] + ssh_opts + [str(archive_path), f"{target}:/tmp/workspace_restore.tar.zst"]
    _log.get().debug("run: %s", " ".join(shlex.quote(c) for c in scp_cmd))
    if _log.DRY_RUN:
        _log.dry_cmd(scp_cmd)
    else:
        try:
            subprocess.run(scp_cmd, check=True)
        except subprocess.CalledProcessError as e:
            error(f"Failed to copy archive: {e}")
            return

    info("Extracting archive on server...")
    extract_cmd = f"tar -xf /tmp/workspace_restore.tar.zst -C /home/{username}/workspace/ --strip-components=1 && rm /tmp/workspace_restore.tar.zst"
    ssh_cmd = ["ssh"] + ssh_opts + [target, extract_cmd]
    _log.get().debug("run: %s", " ".join(shlex.quote(c) for c in ssh_cmd))
    if _log.DRY_RUN:
        _log.dry_cmd(ssh_cmd)
    else:
        try:
            subprocess.run(ssh_cmd, check=True)
            success("Workspace restored!")
        except subprocess.CalledProcessError as e:
            error(f"Failed to extract archive: {e}")


# ─────────────────────────────────────────────────────────────────────────────
# Workflow: ARCHIVE
# ─────────────────────────────────────────────────────────────────────────────

def workflow_archive(client):
    print_header("Archive Workspace", "Compress and download your workspace, then delete the server")

    servers = state.list_servers()
    if not servers:
        warn("No registered servers found.")
        sys.exit(0)

    server_list = list(servers.values())
    chosen = choose_from_list(
        server_list,
        "Select server to archive:",
        display_fn=lambda s: f"[bold]{s['name']}[/bold]  [dim]({s.get('server_type', '?')} | {s.get('ipv6_address', '?')})[/dim]",
    )
    if not chosen:
        sys.exit(0)

    server_id = chosen["server_id"]
    server_name = chosen["name"]

    # Archive name
    archive_name = prompt_input(
        "Archive name",
        default=f"{server_name}",
    ).strip() or server_name

    # Confirm
    blank()
    print_key_value([
        ("Server", server_name),
        ("Archive name", archive_name),
        ("Destination", str(state.archive_dir())),
    ])
    blank()

    if not prompt_confirm("Proceed? This will archive and DELETE the server.", default=False):
        info("Aborted.")
        sys.exit(0)

    # Create archive
    local_path = archive_mod.create_archive(
        server_name=server_name,
        server_info=chosen,
        archive_name=archive_name,
        local_archive_dir=state.archive_dir(),
    )

    if not local_path and not _log.DRY_RUN:
        error("Archive failed. Server will NOT be deleted.")
        sys.exit(1)

    if _log.DRY_RUN:
        _log.dry_action(f"would register archive '{archive_name}' in state")
    else:
        state.register_archive({
            "archive_name": archive_name,
            "server_name": server_name,
            "config_name": chosen.get("config_name", ""),
            "server_type": chosen.get("server_type", ""),
            "local_path": str(local_path),
            "username": chosen.get("username", "ubuntu"),
            "identity_file": chosen.get("identity_file"),
        })

    # Delete server (dry-run handled inside)
    _delete_server_resources(client, chosen, skip_confirm=True)

    if not _log.DRY_RUN:
        success(f"Archive complete. Stored at: {local_path}")


# ─────────────────────────────────────────────────────────────────────────────
# Workflow: RESTORE
# ─────────────────────────────────────────────────────────────────────────────

def workflow_restore(client):
    print_header("Restore Workspace", "Provision a server and restore an archived workspace")

    archives = state.list_archives()
    if not archives:
        warn("No archives found.")
        sys.exit(0)

    archive_list = list(archives.values())
    chosen_archive = choose_from_list(
        archive_list,
        "Select archive to restore:",
        display_fn=lambda a: (
            f"[bold]{a['archive_name']}[/bold]  "
            f"[dim]{a.get('server_type', '?')} | {a.get('archived_at', '?')[:10]}[/dim]  "
            f"[cyan]{Path(a.get('local_path', '')).name if a.get('local_path') else '?'}[/cyan]"
        ),
    )
    if not chosen_archive:
        sys.exit(0)

    archive_path = Path(chosen_archive.get("local_path", ""))
    if not archive_path.exists():
        error(f"Archive file not found: {archive_path}")
        sys.exit(1)

    success(f"Found archive: {archive_path}")

    # Check if original config exists
    config_name = chosen_archive.get("config_name", "")
    original_config = state.load_config(config_name) if config_name else None
    
    if original_config:
        info(f"Original build config found: [bold]{config_name}[/bold]")
        print_key_value([
            ("Server type", original_config.get("server_type", "?")),
            ("Image", original_config.get("image", "?")),
            ("Username", original_config.get("username", "?")),
            ("Software", ", ".join(original_config.get("install", []))),
        ])
        use_original = prompt_confirm("Use original configuration?", default=True)
    else:
        use_original = False

    # Run create workflow with restore
    workflow_create(client, restore_from=chosen_archive["archive_name"])


# ─────────────────────────────────────────────────────────────────────────────
# Workflow: DELETE
# ─────────────────────────────────────────────────────────────────────────────

def workflow_delete(client):
    print_header("Delete Workspace", "Remove server and clean up SSH config")

    servers = state.list_servers()
    if not servers:
        warn("No registered servers found.")
        sys.exit(0)

    server_list = list(servers.values())
    chosen = choose_from_list(
        server_list,
        "Select server to delete:",
        display_fn=lambda s: f"[bold]{s['name']}[/bold]  [dim]({s.get('server_type', '?')} | {s.get('ipv6_address', '?')})[/dim]",
    )
    if not chosen:
        sys.exit(0)

    server_name = chosen["name"]

    # Offer to archive first
    blank()
    if prompt_confirm("Would you like to archive the workspace before deleting?", default=True):
        archive_name = prompt_input(
            "Archive name",
            default=server_name,
        ).strip() or server_name

        local_path = archive_mod.create_archive(
            server_name=server_name,
            server_info=chosen,
            archive_name=archive_name,
            local_archive_dir=state.archive_dir(),
        )

        if local_path and not _log.DRY_RUN:
            state.register_archive({
                "archive_name": archive_name,
                "server_name": server_name,
                "config_name": chosen.get("config_name", ""),
                "server_type": chosen.get("server_type", ""),
                "local_path": str(local_path),
                "username": chosen.get("username", "ubuntu"),
                "identity_file": chosen.get("identity_file"),
            })
            success(f"Archive saved: {local_path}")
        elif _log.DRY_RUN:
            _log.dry_action(f"would register archive '{archive_name}' in state")
        else:
            warn("Archive failed. Continuing with deletion...")

    # Double confirm
    blank()
    warn(f"You are about to PERMANENTLY DELETE server: [bold]{server_name}[/bold]")
    confirm1 = prompt_confirm("Are you sure you want to delete this server?", default=False)
    if not confirm1:
        info("Deletion cancelled.")
        sys.exit(0)

    confirm2 = prompt_confirm(
        f"FINAL CONFIRMATION: Delete '{server_name}' and stop all billing?",
        default=False,
    )
    if not confirm2:
        info("Deletion cancelled.")
        sys.exit(0)

    _delete_server_resources(client, chosen, skip_confirm=True)


def _delete_server_resources(client, server_info: dict, skip_confirm: bool = False):
    """Delete the Hetzner server and clean up local state."""
    server_id = server_info["server_id"]
    server_name = server_info["name"]
    username = server_info.get("username", "ubuntu")
    hostname = server_info.get("ipv6_address") or server_info.get("hostname", "")

    # Delete server
    info(f"Deleting server {server_id} on Hetzner...")
    try:
        client.delete_server(server_id)
        success("Server deleted.")
    except HetznerAPIError as e:
        error(f"Failed to delete server: {e}")
        warn("Continuing with local cleanup...")

    if _log.DRY_RUN:
        _log.dry_action(f"would remove SSH config entry '{server_name}'")
        for addr in filter(None, [server_info.get("ipv4_address"), server_info.get("ipv6_address")]):
            _log.dry_action(f"would remove '{addr}' from known_hosts")
        _log.dry_action(f"would unregister server {server_id} from state")
        return

    # Remove SSH config entry
    if ssh_config.remove_entry(server_name):
        success(f"Removed SSH config entry: {server_name}")

    # Remove from known_hosts (both IPv4 and IPv6 if present)
    ipv4 = server_info.get("ipv4_address", "")
    ipv6 = server_info.get("ipv6_address", "")
    for addr in filter(None, [ipv4, ipv6]):
        ssh_config.remove_known_host(addr)
    if ipv4 or ipv6:
        info("Removed from ~/.ssh/known_hosts")

    # Unregister from state
    state.unregister_server(server_id)
    success(f"Server '{server_name}' fully removed.")


# ─────────────────────────────────────────────────────────────────────────────
# Main entry
# ─────────────────────────────────────────────────────────────────────────────

MENU_OPTIONS = [
    {"key": "create",          "label": "Create new workspace server"},
    {"key": "archive",         "label": "Archive workspace & delete server"},
    {"key": "restore",         "label": "Restore workspace from archive"},
    {"key": "delete",          "label": "Delete server (with optional archive)"},
    {"key": "list",            "label": "List running servers & saved configs"},
    {"key": "delete-configs",  "label": "Delete saved configs"},
    {"key": "delete-archives", "label": "Delete local archives"},
    {"key": "quit",            "label": "Quit"},
]


def _workflow_list():
    blank()
    servers = state.list_servers()
    if servers:
        print_rule("Running Servers")
        rows = []
        for s in servers.values():
            rows.append([
                s.get("name", "?"),
                s.get("server_type", "?"),
                s.get("ipv6_address", "?"),
                s.get("config_name", "?"),
                s.get("registered_at", "?")[:10],
            ])
        print_table(
            ["Name", "Type", "IPv6", "Config", "Since"],
            rows,
            title="Running Servers",
        )
    else:
        info("No running servers registered.")

    configs = state.list_configs()
    if configs:
        print_rule("Saved Configs")
        rows = [[name, c.get("server_type", "?"), c.get("image", "?"),
                 ", ".join(c.get("install", [])), c.get("saved_at", "?")[:10]]
                for name, c in configs.items()]
        print_table(["Name", "Type", "Image", "Software", "Saved"], rows, title="Saved Configs")

    archives = state.list_archives()
    if archives:
        print_rule("Archives")
        rows = []
        for name, a in archives.items():
            path = Path(a.get("local_path", ""))
            size = f"{path.stat().st_size / 1048576:.1f} MB" if path.exists() else "missing"
            rows.append([name, a.get("server_type", "?"), a.get("archived_at", "?")[:10], size])
        print_table(["Archive", "Type", "Date", "Size"], rows, title="Archives")
    blank()


def _workflow_delete_configs():
    configs = state.list_configs()
    if not configs:
        info("No saved configs.")
        return

    items = [{"name": name, **cfg} for name, cfg in configs.items()]

    def _row(c):
        return [c["name"], c.get("server_type", "?"), c.get("image", "?"),
                ", ".join(c.get("install", [])) or "none", c.get("saved_at", "?")[:10]]

    chosen = choose_multiple(items, "Select configs to delete:", headers=["Name", "Type", "Image", "Software", "Saved"], row_fn=_row)
    if not chosen:
        info("Nothing selected.")
        return

    names = [c["name"] for c in chosen]
    warn(f"About to delete {len(names)} config(s): {', '.join(names)}")
    if not prompt_confirm("Confirm?", default=False):
        info("Cancelled.")
        return

    for name in names:
        state.delete_config(name)
        success(f"Deleted config: {name}")


def _workflow_delete_archives():
    archives = state.list_archives()
    if not archives:
        info("No saved archives.")
        return

    items = [{"name": name, **a} for name, a in archives.items()]

    def _row(a):
        path = Path(a.get("local_path", ""))
        size = f"{path.stat().st_size / 1048576:.1f} MB" if path.exists() else "missing"
        return [a["name"], a.get("server_type", "?"), a.get("archived_at", "?")[:10], size]

    chosen = choose_multiple(items, "Select archives to delete:", headers=["Archive", "Type", "Date", "Size"], row_fn=_row)
    if not chosen:
        info("Nothing selected.")
        return

    names = [a["name"] for a in chosen]
    warn(f"About to permanently delete {len(names)} archive(s): {', '.join(names)}")
    if not prompt_confirm("Confirm?", default=False):
        info("Cancelled.")
        return

    for a in chosen:
        path = Path(a.get("local_path", ""))
        if path.exists():
            path.unlink()
        state.delete_archive_record(a["name"])
        success(f"Deleted archive: {a['name']}")


def main():
    parser = argparse.ArgumentParser(prog="hw", description="Hetzner Workspace Manager")
    parser.add_argument(
        "workflow",
        nargs="?",
        choices=["create", "archive", "restore", "delete", "list", "delete-configs", "delete-archives"],
        help="Workflow to run (omit for interactive menu)",
    )
    parser.add_argument(
        "-v", dest="verbosity", action="count", default=0,
        help="Verbosity: -v INFO, -vv DEBUG (written to logs/)",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="Show what would happen without making any changes",
    )
    args = parser.parse_args()
    _log.setup(verbosity=args.verbosity, dry_run=args.dry_run)

    print_header(
        "Hetzner Workspace Manager",
        "Provision · Archive · Restore · Delete cloud workspaces",
    )

    if args.workflow:
        chosen_workflow = args.workflow
    else:
        choice = choose_from_list(
            MENU_OPTIONS,
            "What would you like to do?",
            display_fn=lambda o: f"[bold]{o['key']}[/bold]  [dim]{o['label']}[/dim]",
        )
        chosen_workflow = choice["key"] if choice else "quit"

    if chosen_workflow == "quit":
        info("Goodbye!")
        sys.exit(0)

    if chosen_workflow == "list":
        _workflow_list()
        sys.exit(0)

    if chosen_workflow == "delete-configs":
        _workflow_delete_configs()
        sys.exit(0)

    if chosen_workflow == "delete-archives":
        _workflow_delete_archives()
        sys.exit(0)

    # All other workflows need API access
    try:
        client = get_client()
    except SystemExit:
        sys.exit(1)

    if chosen_workflow == "create":
        workflow_create(client)
    elif chosen_workflow == "archive":
        workflow_archive(client)
    elif chosen_workflow == "restore":
        workflow_restore(client)
    elif chosen_workflow == "delete":
        workflow_delete(client)
