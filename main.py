#!/usr/bin/env python3
"""
Hetzner Workspace Manager
A CLI tool for provisioning, archiving, and managing Hetzner cloud servers.
"""

import os
import sys
from pathlib import Path

# Load .env before any module-level env reads (e.g. HW_STATE_DIR in state.py).
# Existing env vars always take precedence. Checked in order:
#   1. Project root (source users running from repo)
#   2. Current working directory (binary users)
#   3. ~/.hetzner-workspace/ (global, set via "save token" prompt)
def _load_env(path: Path) -> None:
    if not path.exists():
        return
    for _line in path.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _, _v = _line.partition("=")
        _k = _k.strip()
        _v = _v.strip().strip('"').strip("'")
        if _k and _k not in os.environ:
            os.environ[_k] = _v

_state_dir = Path(os.environ.get("HW_STATE_DIR", Path.home() / ".hetzner-workspace"))
_seen_envs: set = set()
for _candidate in [
    Path(__file__).parent / ".env",
    Path.cwd() / ".env",
    _state_dir / ".env",
]:
    _resolved = _candidate.resolve()
    if _resolved not in _seen_envs:
        _seen_envs.add(_resolved)
        _load_env(_candidate)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.cli import main

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\nAborted.")
        sys.exit(0)
