# Hetzner Workspace Manager

> **⚠ Preview / personal use** — this tool provisions and deletes real cloud servers. Running it will incur costs and make destructive changes. Use with care.

A CLI tool for provisioning, archiving, restoring, and deleting Hetzner Cloud workspace servers — with SSH config management, server hardening, and software install automation.

---

## Installation

### Option A — Download binary (recommended)

Download the latest binary for your platform from [Releases](../../releases/latest):

| Platform | File |
|----------|------|
| macOS (Apple Silicon) | `hetzner-workspace-darwin-arm64` |
| macOS (Intel) | `hetzner-workspace-darwin-x86_64` |
| Linux x86_64 | `hetzner-workspace-linux-x86_64` |
| Linux arm64 | `hetzner-workspace-linux-arm64` |

```bash
# make executable and move to PATH
chmod +x hetzner-workspace-darwin-arm64
mv hetzner-workspace-darwin-arm64 /usr/local/bin/hetzner-workspace

hetzner-workspace
```

On first run with no API token configured, you'll be prompted to enter it and asked whether to save it to `~/.hetzner-workspace/.env` — after that, no further setup needed.

Add a shell alias for convenience:
```bash
alias hw='hetzner-workspace'
```

### Option B — Run from source

Requires [uv](https://docs.astral.sh/uv/).

```bash
git clone <repo>
cd hetzner-workspace
uv run main.py
```

On first run you'll be prompted for your API token and offered the option to save it. Alternatively, copy `.env.example` to `.env` and set `HETZNER_API_TOKEN` manually.

Add a shell alias:
```bash
alias hw='uv run /path/to/hetzner-workspace/main.py'
```

### Building the binary locally

```bash
uv run --with pyinstaller pyinstaller --onefile --name hetzner-workspace main.py
# binary written to dist/hetzner-workspace
```

---

## Workflows

### `create` — Provision a new workspace
```bash
hetzner-workspace create   # binary
uv run main.py create      # from source
```
Steps you'll be guided through:
1. **Load saved config** — optionally pre-fill all options from a previous config.
2. **Server type** — sorted cheapest first, showing CPU/RAM/arch/price. Location auto-selected (cheapest region first).
3. **Base image** — filtered by server architecture, Ubuntu listed first.
4. **SSH keys** — uses your Hetzner account keys if available, falls back to local `~/.ssh/*.pub` files.
5. **Username** — default user to create on the server.
6. **Software** — pick any combination of available tools (see [Software Install Options](#software-install-options)).
7. **Network** — IPv4 optional (IPv6 always assigned). IPv6-only servers can't reach GitHub/Docker Hub/AWS S3.
8. **Config name** — saved to `~/.hetzner-workspace/configs.json` for reuse.
9. **Server name** — used as the SSH alias in `~/.ssh/config`.

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
hetzner-workspace archive
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
hetzner-workspace restore
uv run main.py restore
```
1. List all local archives with metadata
2. Pick archive to restore
3. Shows original build config if available
4. Runs the `create` workflow with archive restore at end
5. SCP archive to new server → extract into `~/workspace`

### `delete` — Delete without archiving
```bash
hetzner-workspace delete
uv run main.py delete
```
1. Select server
2. **Offers to archive first** (recommended)
3. Double confirmation before deletion
4. Deletes Hetzner server, removes SSH config and known_hosts

### `list` — View current state
```bash
hetzner-workspace list
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

| Variable | Purpose |
|----------|---------|
| `HETZNER_API_TOKEN` | Hetzner Cloud API token — prompted on first run, saved to `~/.hetzner-workspace/.env` |
| `HW_STATE_DIR` | Override state directory (default: `~/.hetzner-workspace`) |

Loaded from (in order, first match wins): project `.env` → current directory `.env` → `~/.hetzner-workspace/.env`.

---

## Networking

- **IPv4 optional** — prompted during `create`. IPv6 is always assigned. Enabling IPv4 adds a small cost (~€0.001/hr).
- Default networking only; no private networks added

> **Note**: IPv6-only servers cannot reach GitHub, Docker Hub, or AWS S3 — enable IPv4 if you need those during setup.

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
| `docker` | Docker CE + Compose plugin via official script; user added to docker group |
| `uv` | uv Python package manager |
| `npm` | Node.js LTS + npm via NodeSource |
| `homebrew` | Linuxbrew (installed as workspace user) |
| `go` | Latest stable Go, arch-aware (downloaded from go.dev) |
| `rust` | Rust toolchain via rustup |
| `tmux` | tmux terminal multiplexer via apt |
| `act` | act — run GitHub Actions locally |
| `rclone` | rclone — sync files to/from cloud storage |

New tools can be added without touching Python — see [Adding a New Install Tool](#adding-a-new-install-tool).

---

## Adding a New Install Tool

1. Create `scripts/install/<name>.sh` — must accept `$1` as username, use `set -euo pipefail`
2. Add an entry to `scripts/install/meta.json`:
   ```json
   "name": {
     "label": "Human-readable label",
     "apt_packages": ["any-apt-deps-needed-before-script-runs"]
   }
   ```
3. Done — it auto-appears in the CLI software selection menu.

Scripts are embedded into cloud-init and run on the server as `bash /opt/install/<name>.sh <username>`.

---

## Archive Format

Archives use `tar + zstd` compression:
- Compression level 3 (fast, ~40% smaller than gzip)
- Multi-threaded (`-T0`)
- Format: `{archive_name}_{YYYYMMDD_HHMMSS}.tar.zst`

---

## Requirements

**Binary**: no dependencies — download and run.

**From source**: Python 3.10+ and [uv](https://docs.astral.sh/uv/) (`requests` and `rich` managed automatically).
