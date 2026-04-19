# Hetzner Workspace Manager

A CLI tool for provisioning, archiving, restoring, and deleting Hetzner Cloud workspace servers — with SSH config management, server hardening, and software install automation.

---

## Quick Start

```bash
# 1. Configure your API token
cp .env.example .env
# edit .env and set HETZNER_API_TOKEN

# 2. Run (uv handles deps and .env automatically)
uv run main.py
```

---

## Workflows

### `create` — Provision a new workspace
```bash
uv run main.py create
```
Steps you'll be guided through:
1. **Server type** — sorted cheapest first, showing CPU/RAM/arch/price. Location auto-selected (cheapest region first).
2. **Base image** — all available system images listed (Ubuntu first).
3. **SSH keys** — uses your Hetzner account keys if available, falls back to local `~/.ssh/*.pub` files.
4. **Username** — default user to create on the server.
5. **Software** — pick from: git, docker, uv, npm, homebrew, go.
6. **Config name** — saved to `~/.hetzner-workspace/configs.json` for reuse.
7. **Server name** — used as the SSH alias in `~/.ssh/config`.

Server is provisioned with:
- UFW firewall (deny inbound except SSH)
- Fail2ban (3 strikes → 1hr ban)
- Automatic security updates
- SSH hardening (key-only, no passwords, no root login)
- Kernel hardening via sysctl
- `~/workspace` directory created

SSH config entry added with:
- `ForwardAgent yes`
- `ServerAliveInterval 60`
- `StrictHostKeyChecking accept-new`

### `archive` — Save workspace and delete server
```bash
uv run main.py archive
```
1. Select which running server to archive
2. Name the archive
3. SSH into server → `tar + zstd` compress `~/workspace`
4. Download archive to `~/.hetzner-workspace/archives/`
5. Delete Hetzner server (stops billing)
6. Remove SSH config entry and known_hosts entry
7. Register archive metadata for later restore

### `restore` — Restore from archive
```bash
uv run main.py restore
```
1. List all local archives with metadata
2. Pick archive to restore
3. Shows original build config if available
4. Runs the `create` workflow with archive restore at end
5. SCP archive to new server → extract into `~/workspace`

### `delete` — Delete without archiving
```bash
uv run main.py delete
```
1. Select server
2. **Offers to archive first** (recommended)
3. Double confirmation before deletion
4. Deletes Hetzner server, removes SSH config and known_hosts

### `list` — View current state
```bash
uv run main.py list
```
Shows running servers, saved configs, and local archives.

---

## State Storage

Everything is stored in `~/.hetzner-workspace/`:

```
~/.hetzner-workspace/
  configs.json          # named build configurations
  servers.json          # registered running servers
  archives.json         # archive metadata
  archives/
    myserver_20241201_120000.tar.zst
    ...
```

Override location: `export HW_STATE_DIR=/path/to/dir`

---

## Environment Variables

Set these in `.env` (copy from `.env.example`):

| Variable | Purpose |
|----------|---------|
| `HETZNER_API_TOKEN` | Hetzner Cloud API token (required) |
| `HW_STATE_DIR` | Override state directory (default: `~/.hetzner-workspace`) |

---

## Networking

- **IPv6 only** — no IPv4 assigned (saves money, Hetzner IPv6 is free)
- Default networking only; no private networks added

> **Note**: If connecting from an IPv4-only network, you'll need to use a proxy or add IPv4 via the Hetzner console.

---

## SSH Config Example

After `create`, your `~/.ssh/config` will have an entry like:

```
# BEGIN hetzner-workspace: my-server
Host my-server
    HostName 2a01:4f8:xxxx:xxxx::1
    User ubuntu
    Port 22
    ForwardAgent yes
    ServerAliveInterval 60
    ServerAliveCountMax 3
    StrictHostKeyChecking accept-new
    IdentityFile ~/.ssh/id_ed25519
# END hetzner-workspace: my-server
```

---

## Software Install Options

| Key | What gets installed |
|-----|-------------------|
| `git` | git via apt |
| `docker` | Docker CE via official script + post-install (user added to docker group, service enabled) |
| `uv` | uv Python package manager |
| `npm` | Node.js LTS + npm via NodeSource |
| `homebrew` | Linuxbrew (installed as workspace user) |
| `go` | Latest stable Go (downloaded from go.dev) |

---

## Archive Format

Archives use `tar + zstd` compression:
- Compression level 3 (fast, ~40% smaller than gzip)
- Multi-threaded (`-T0`)
- Format: `{archive_name}_{YYYYMMDD_HHMMSS}.tar.zst`

---

## Requirements

- Python 3.10+
- [uv](https://docs.astral.sh/uv/) (`requests` and `rich` managed automatically)
- `ssh`, `scp` available in PATH
- `zstd` on remote server (installed automatically via apt)
