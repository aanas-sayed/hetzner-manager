# Hetzner Workspace Manager — Project Context

Python CLI tool for provisioning, archiving, restoring, and deleting Hetzner Cloud workspace servers. No frameworks — stdlib + `requests` + `rich`.

---

## Project Layout

```
main.py                     # Entry point — loads .env, calls src/cli.py:main()
pyproject.toml              # Project metadata + dependencies
src/
  cli.py                    # All workflows + interactive menu
  hetzner.py                # Thin REST wrapper around api.hetzner.cloud/v1
  cloud_init.py             # Builds cloud-init #cloud-config YAML
  ssh_config.py             # Reads/writes ~/.ssh/config Host entries
  state.py                  # JSON state in ~/.hetzner-workspace/
  archive.py                # SSH/SCP-based tar+zstd archive logic
  ui.py                     # Rich prompts/tables/spinners (graceful fallback if rich missing)
  log.py                    # Logging setup, DRY_RUN flag, dry_cmd/dry_action helpers
scripts/install/
  meta.json                 # Display labels + apt pre-deps for each tool
  *.sh                      # One script per tool — accepts $1=username, set -euo pipefail
```

---

## Key Design Decisions

- **IPv4 optional** — prompted during create under a "Network" section. IPv6 always assigned. IPv6-only servers can't reach GitHub/Docker Hub/AWS S3.
- **Location auto-selected** — never prompted (priority: hel1 → fsn1 → nbg1). Change `_pick_best_location()` to adjust.
- **Images filtered by arch** — only images matching the chosen server type's architecture are shown.
- **Config reuse** — start of `workflow_create` offers to load a saved config (pre-fills server type, image, username, software, identity_file, enable_ipv4).
- **SSH hardening via cloud-init** — key-only auth, fail2ban, UFW, sysctl. Based on https://community.hetzner.com/tutorials/basic-cloud-config
- **`rich` is optional** — `ui.py` falls back gracefully to plain `print()`.
- **`.env` loading** — `main.py` loads from: project root → cwd → `~/.hetzner-workspace/.env` (first match per key wins). Token is prompted interactively if missing and can be saved to the state dir `.env`.

---

## Adding a New Install Tool

1. Create `scripts/install/<name>.sh` (accepts `$1` as username, `set -euo pipefail`)
2. Add entry to `scripts/install/meta.json` with `label` and `apt_packages`
3. Done — auto-appears in CLI. No Python changes needed.

---

## Running

```bash
uv run main.py [create|archive|restore|delete|list]
uv run main.py -v create        # INFO logging
uv run main.py -vv create       # DEBUG logging (full API payloads)
uv run main.py --dry-run create # Preview without executing
```

Or use the compiled binary: `hetzner-workspace [command]`

---

## Git Workflow

Conventional commits — lowercase, no trailing period:

```
feat: add rclone install script
fix: handle missing SSH key gracefully
chore: update pyproject.toml dependencies
refactor: extract server polling into helper
```

Commit at meaningful checkpoints. Never commit broken or half-finished code.
