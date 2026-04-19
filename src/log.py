"""
Logging setup and dry-run state for hetzner-workspace.
Call setup() once from main() before anything else.
"""

import logging
import shlex
from datetime import datetime
from pathlib import Path

DRY_RUN: bool = False
_logger: logging.Logger | None = None

_LOGS_DIR = Path(__file__).parent.parent / "logs"


def setup(verbosity: int = 0, dry_run: bool = False) -> None:
    global DRY_RUN, _logger
    DRY_RUN = dry_run

    level = (
        logging.DEBUG if verbosity >= 2
        else logging.INFO if verbosity >= 1
        else logging.WARNING
    )

    _LOGS_DIR.mkdir(exist_ok=True)
    log_file = _LOGS_DIR / f"hw_{datetime.now().strftime('%Y%m%d')}.log"

    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter(
        "%(asctime)s  %(levelname)-8s  %(name)-20s  %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    ))

    root = logging.getLogger()
    root.setLevel(level)
    root.addHandler(handler)
    _logger = logging.getLogger("hw")

    if dry_run:
        _logger.info("DRY-RUN mode active — no changes will be made")


def get() -> logging.Logger:
    global _logger
    if _logger is None:
        _logger = logging.getLogger("hw")
    return _logger


def dry_cmd(cmd: list[str]) -> None:
    """Log and display a shell command skipped by dry-run."""
    pretty = "$ " + " ".join(shlex.quote(c) for c in cmd)
    get().info("DRY-RUN cmd: %s", pretty)
    _ui_dry(pretty)


def dry_action(msg: str) -> None:
    """Log and display an action skipped by dry-run."""
    get().info("DRY-RUN: %s", msg)
    _ui_dry(msg)


def _ui_dry(msg: str) -> None:
    try:
        from src.ui import dim
        dim(f"[yellow]dry-run[/yellow]  {msg}")
    except Exception:
        print(f"dry-run  {msg}")
