#!/usr/bin/env python3
"""
Hetzner Workspace Manager
A CLI tool for provisioning, archiving, and managing Hetzner cloud servers.
"""

import os
import sys
from pathlib import Path

# Load .env before any module-level env reads (e.g. HW_STATE_DIR in state.py).
# Existing env vars take precedence over .env values.
_env_file = Path(__file__).parent / ".env"
if _env_file.exists():
    for _line in _env_file.read_text().splitlines():
        _line = _line.strip()
        if not _line or _line.startswith("#") or "=" not in _line:
            continue
        _k, _, _v = _line.partition("=")
        _k = _k.strip()
        _v = _v.strip().strip('"').strip("'")
        if _k and _k not in os.environ:
            os.environ[_k] = _v

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.cli import main

if __name__ == "__main__":
    main()
