"""
State management for workspace configs, server registry, and archives.
Everything lives in ~/.hetzner-workspace/ by default.
"""

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import Optional


STATE_DIR = Path(os.environ.get("HW_STATE_DIR", Path.home() / ".hetzner-workspace"))
CONFIGS_FILE = STATE_DIR / "configs.json"
SERVERS_FILE = STATE_DIR / "servers.json"
ARCHIVES_FILE = STATE_DIR / "archives.json"
ARCHIVE_DIR = STATE_DIR / "archives"


def _ensure_dirs():
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ARCHIVE_DIR.mkdir(parents=True, exist_ok=True)


def _load(path: Path) -> dict | list:
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError:
            return {} if path.suffix == ".json" else []
    return {}


def _save(path: Path, data) -> None:
    _ensure_dirs()
    path.write_text(json.dumps(data, indent=2, default=str))


# ── Build Configs ──────────────────────────────────────────────────────────────

def save_config(name: str, config: dict) -> None:
    """Save a named build configuration."""
    configs = _load(CONFIGS_FILE)
    if not isinstance(configs, dict):
        configs = {}
    config["saved_at"] = datetime.utcnow().isoformat()
    configs[name] = config
    _save(CONFIGS_FILE, configs)


def load_config(name: str) -> Optional[dict]:
    configs = _load(CONFIGS_FILE)
    return configs.get(name) if isinstance(configs, dict) else None


def list_configs() -> dict:
    data = _load(CONFIGS_FILE)
    return data if isinstance(data, dict) else {}


def delete_config(name: str) -> bool:
    configs = _load(CONFIGS_FILE)
    if isinstance(configs, dict) and name in configs:
        del configs[name]
        _save(CONFIGS_FILE, configs)
        return True
    return False


# ── Server Registry ────────────────────────────────────────────────────────────

def register_server(server_info: dict) -> None:
    """Track a running server."""
    servers = _load(SERVERS_FILE)
    if not isinstance(servers, dict):
        servers = {}
    servers[str(server_info["server_id"])] = {
        **server_info,
        "registered_at": datetime.utcnow().isoformat(),
    }
    _save(SERVERS_FILE, servers)


def unregister_server(server_id: int) -> Optional[dict]:
    servers = _load(SERVERS_FILE)
    if not isinstance(servers, dict):
        return None
    entry = servers.pop(str(server_id), None)
    _save(SERVERS_FILE, servers)
    return entry


def list_servers() -> dict:
    data = _load(SERVERS_FILE)
    return data if isinstance(data, dict) else {}


def get_server_info(server_id: int) -> Optional[dict]:
    servers = _load(SERVERS_FILE)
    return servers.get(str(server_id)) if isinstance(servers, dict) else None


def get_server_by_name(name: str) -> Optional[dict]:
    for info in list_servers().values():
        if info.get("name") == name:
            return info
    return None


# ── Archive Registry ───────────────────────────────────────────────────────────

def register_archive(archive_info: dict) -> None:
    archives = _load(ARCHIVES_FILE)
    if not isinstance(archives, dict):
        archives = {}
    key = archive_info["archive_name"]
    archives[key] = {
        **archive_info,
        "archived_at": datetime.utcnow().isoformat(),
    }
    _save(ARCHIVES_FILE, archives)


def list_archives() -> dict:
    data = _load(ARCHIVES_FILE)
    return data if isinstance(data, dict) else {}


def get_archive(name: str) -> Optional[dict]:
    return list_archives().get(name)


def delete_archive_record(name: str) -> bool:
    archives = _load(ARCHIVES_FILE)
    if isinstance(archives, dict) and name in archives:
        del archives[name]
        _save(ARCHIVES_FILE, archives)
        return True
    return False


# ── Helpers ───────────────────────────────────────────────────────────────────

def state_dir() -> Path:
    _ensure_dirs()
    return STATE_DIR


def archive_dir() -> Path:
    _ensure_dirs()
    return ARCHIVE_DIR
