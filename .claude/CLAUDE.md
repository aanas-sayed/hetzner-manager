# Hetzner Workspace Manager — Project Context

A Python CLI tool for provisioning, archiving, restoring, and deleting Hetzner Cloud workspace servers. No frameworks — just stdlib + `requests` + `rich`.

---

## Project Layout

```
main.py                     # Entry point — calls src/cli.py:main()
pyproject.toml              # Project metadata + dependencies (requests, rich)
uv.lock                     # Locked dependency versions

src/
  cli.py                    # All four workflow functions + interactive menu
  hetzner.py                # Thin REST wrapper around api.hetzner.cloud/v1
  cloud_init.py             # Builds cloud-init #cloud-config YAML
  ssh_config.py             # Reads/writes ~/.ssh/config Host entries
  state.py                  # JSON state in ~/.hetzner-workspace/
  archive.py                # SSH/SCP-based tar+zstd archive logic
  ui.py                     # Rich-powered prompts, tables, spinners (graceful fallback if rich missing)
  log.py                    # Logging setup (stdlib), DRY_RUN flag, dry_cmd/dry_action helpers

scripts/install/
  meta.json                 # Display labels + apt pre-deps for each tool
  git.sh                    # Each script: #!/usr/bin/env bash, accepts $1=username
  docker.sh
  uv.sh
  npm.sh
  homebrew.sh
  go.sh
```

---

## The Four Workflows

### create
`src/cli.py:workflow_create(client)`

1. Fetch server types → sort by hourly price → user picks one
2. Auto-select location (priority: hel1 → fsn1 → nbg1)
3. Fetch images → list all, Ubuntu sorted first → user picks
4. SSH keys — tries Hetzner account keys via API first, falls back to `~/.ssh/*.pub`
5. Username prompt (default: `ubuntu`)
6. Software selection — driven by `scripts/install/*.sh` discovery
7. Config name (saved to state) + server name (used as SSH alias)
8. Builds cloud-init via `cloud_init.py:build_cloud_config()`
9. POSTs to Hetzner API — IPv6 only, no IPv4
10. Polls until server status == `running`
11. Writes SSH config entry via `ssh_config.py:add_entry()`
12. Saves config + registers server in state

### archive
`src/cli.py:workflow_archive(client)`

- SSH into server → `tar -cf - workspace | zstd -T0 -3` → SCP down to `~/.hetzner-workspace/archives/`
- Registers archive metadata in state
- Deletes server + removes SSH config entry

### restore
`src/cli.py:workflow_restore(client)`

- Lists local archives from state
- Runs `workflow_create()` then SCPs archive up and extracts into `~/workspace`

### delete
`src/cli.py:workflow_delete(client)`

- Offers to archive first
- Double-confirms
- Calls `_delete_server_resources()` — deletes server, removes SSH config, removes known_hosts entry, unregisters from state

---

## State Storage

All state lives in `~/.hetzner-workspace/` (override with `HW_STATE_DIR` env var):

```
configs.json    # {name: {server_type, image, username, install[], ...}}
servers.json    # {server_id: {name, ipv6_address, config_name, identity_file, ...}}
archives.json   # {archive_name: {local_path, server_type, archived_at, ...}}
archives/       # .tar.zst files
```

State functions are all in `src/state.py` — straightforward JSON read/write, no database.

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
3. Done — it auto-appears in the CLI menu. No Python changes needed.

Scripts are embedded into cloud-init `write_files` (landing at `/opt/install/<name>.sh` on the server) and executed via `runcmd` as `bash /opt/install/<name>.sh <username>`.

---

## Key Design Decisions

- **IPv6 only** — no IPv4 assigned. If you need IPv4 access add it via Hetzner console or update `payload["public_net"]` in `workflow_create`.
- **No setup costs shown** — server type list filters by hourly price only.
- **Location is always auto-selected** — never prompted. Change `_pick_best_location()` to adjust priority.
- **SSH hardening via cloud-init** — key-only auth, no passwords, fail2ban, UFW, sysctl kernel params. Based on https://community.hetzner.com/tutorials/basic-cloud-config
- **`json_esc()` is gone** — YAML escaping was the main pain point of the old approach. Scripts in `write_files` sidestep this entirely.
- **`rich` is optional** — `ui.py` falls back gracefully to plain `print()` if not installed.

---

## Environment Variables

| Variable | Purpose |
|---|---|
| `HETZNER_API_TOKEN` | Hetzner Cloud API token — prompted interactively if not set |
| `HW_STATE_DIR` | Override state directory (default: `~/.hetzner-workspace`) |

---

## Running

```bash
uv run main.py                  # interactive menu
uv run main.py create
uv run main.py archive
uv run main.py restore
uv run main.py delete
uv run main.py list

uv run main.py -v create        # INFO logging to logs/hw_YYYYMMDD.log
uv run main.py -vv create       # DEBUG logging (full API payloads/responses)
uv run main.py --dry-run create # Preview all actions without executing them
```

Use `uv run main.py` — no install step needed. For a shell alias add `alias hw='uv run /path/to/hetzner-workspace/main.py'` to your shell rc.

`.env` is loaded automatically from the project root by `main.py` before any other imports.

---

## Git Workflow

Use **conventional commits** — lowercase, no trailing period:

```
feat: add rclone install script
fix: handle missing SSH key gracefully
chore: update pyproject.toml dependencies
refactor: extract server polling into helper
docs: update README with uv instructions
```

Commit at meaningful checkpoints (completed feature, working fix, clean refactor) — not per file or per line. Never commit broken or half-finished code.