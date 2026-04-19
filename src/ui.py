"""
Terminal UI helpers.
Uses rich for pretty output and simple prompt functions.
"""

import sys
import os
from typing import Optional


# ── Colour / style helpers (graceful fallback if rich not installed) ──────────

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich import print as rprint
    from rich.prompt import Prompt, Confirm
    from rich.columns import Columns
    from rich.rule import Rule
    from rich.syntax import Syntax
    from rich.progress import Progress, SpinnerColumn, TextColumn, TimeElapsedColumn
    import rich.box as box

    _console = Console()
    _err_console = Console(stderr=True)
    RICH = True
except ImportError:
    RICH = False
    _console = None
    _err_console = None


def _strip(text: str) -> str:
    """Strip rich markup for plain-text fallback."""
    import re
    return re.sub(r"\[.*?\]", "", text)


def print_header(title: str, subtitle: str = "") -> None:
    if RICH:
        _console.print()
        _console.print(Panel(
            f"[bold cyan]{title}[/bold cyan]\n[dim]{subtitle}[/dim]" if subtitle else f"[bold cyan]{title}[/bold cyan]",
            border_style="cyan",
            padding=(0, 2),
        ))
        _console.print()
    else:
        print(f"\n{'='*60}")
        print(f"  {title}")
        if subtitle:
            print(f"  {subtitle}")
        print(f"{'='*60}\n")


def print_rule(title: str = "") -> None:
    if RICH:
        _console.print(Rule(title, style="dim cyan"))
    else:
        print(f"\n── {title} " + "─" * max(0, 50 - len(title)))


def info(msg: str) -> None:
    if RICH:
        _console.print(f"[cyan]ℹ[/cyan]  {msg}")
    else:
        print(f"[INFO] {_strip(msg)}")


def success(msg: str) -> None:
    if RICH:
        _console.print(f"[green]✔[/green]  {msg}")
    else:
        print(f"[OK] {_strip(msg)}")


def warn(msg: str) -> None:
    if RICH:
        _console.print(f"[yellow]⚠[/yellow]  {msg}")
    else:
        print(f"[WARN] {_strip(msg)}", file=sys.stderr)


def error(msg: str) -> None:
    if RICH:
        _err_console.print(f"[red]✘[/red]  {msg}")
    else:
        print(f"[ERROR] {_strip(msg)}", file=sys.stderr)


def dim(msg: str) -> None:
    if RICH:
        _console.print(f"[dim]{msg}[/dim]")
    else:
        print(msg)


def blank() -> None:
    print()


# ── Prompts ───────────────────────────────────────────────────────────────────

def prompt_input(label: str, default: str = None, password: bool = False) -> str:
    if RICH:
        kwargs = {}
        if default is not None:
            kwargs["default"] = default
        if password:
            kwargs["password"] = True
        return Prompt.ask(f"[bold]{label}[/bold]", **kwargs)
    else:
        suffix = f" [{default}]" if default else ""
        val = input(f"{_strip(label)}{suffix}: ").strip()
        return val if val else (default or "")


def prompt_confirm(label: str, default: bool = True) -> bool:
    if RICH:
        return Confirm.ask(f"[bold]{label}[/bold]", default=default)
    else:
        suffix = " [Y/n]" if default else " [y/N]"
        val = input(f"{_strip(label)}{suffix}: ").strip().lower()
        if not val:
            return default
        return val in ("y", "yes")


def choose_from_list(items: list, label: str, display_fn=None, min_col_width: int = 0) -> any:
    """
    Present a numbered list and return the chosen item.
    display_fn(item) -> str for custom display.
    """
    if not items:
        error("No items to choose from.")
        return None

    if RICH:
        _console.print(f"\n[bold]{label}[/bold]")
        for i, item in enumerate(items, 1):
            text = display_fn(item) if display_fn else str(item)
            _console.print(f"  [dim]{i:>2}.[/dim] {text}")
        _console.print()
    else:
        print(f"\n{label}")
        for i, item in enumerate(items, 1):
            text = display_fn(item) if display_fn else str(item)
            print(f"  {i:>2}. {_strip(text)}")
        print()

    while True:
        raw = prompt_input("Enter number").strip()
        try:
            idx = int(raw) - 1
            if 0 <= idx < len(items):
                return items[idx]
        except ValueError:
            pass
        error(f"Please enter a number between 1 and {len(items)}.")


def choose_multiple(items: list, label: str, display_fn=None) -> list:
    """Choose multiple items by number (comma-separated or ranges)."""
    if not items:
        return []

    if RICH:
        _console.print(f"\n[bold]{label}[/bold]")
        for i, item in enumerate(items, 1):
            text = display_fn(item) if display_fn else str(item)
            _console.print(f"  [dim]{i:>2}.[/dim] {text}")
        _console.print(f"  [dim](Enter numbers separated by commas, e.g. 1,3,4 or press Enter to skip)[/dim]")
        _console.print()
    else:
        print(f"\n{label}")
        for i, item in enumerate(items, 1):
            text = display_fn(item) if display_fn else str(item)
            print(f"  {i:>2}. {_strip(text)}")
        print("  (Enter numbers separated by commas, or press Enter to skip)")
        print()

    raw = prompt_input("Enter numbers").strip()
    if not raw:
        return []

    selected = []
    for part in raw.split(","):
        part = part.strip()
        try:
            idx = int(part) - 1
            if 0 <= idx < len(items):
                selected.append(items[idx])
        except ValueError:
            pass
    return selected


def print_table(headers: list[str], rows: list[list], title: str = "") -> None:
    if RICH:
        t = Table(title=title or None, box=box.SIMPLE_HEAD, show_edge=False,
                  header_style="bold cyan", border_style="dim")
        for h in headers:
            t.add_column(h)
        for row in rows:
            t.add_row(*[str(c) for c in row])
        _console.print(t)
    else:
        if title:
            print(f"\n{title}")
        widths = [max(len(h), max((len(str(r[i])) for r in rows), default=0))
                  for i, h in enumerate(headers)]
        fmt = "  ".join(f"{{:<{w}}}" for w in widths)
        print(fmt.format(*headers))
        print("  ".join("-" * w for w in widths))
        for row in rows:
            print(fmt.format(*[str(c) for c in row]))


def spinner_context(label: str):
    """Context manager that shows a spinner while work is done."""
    if RICH:
        return Progress(
            SpinnerColumn(),
            TextColumn(f"[cyan]{label}[/cyan]"),
            TimeElapsedColumn(),
            transient=True,
        )
    else:
        class _Dummy:
            def __enter__(self): print(f"{label}..."); return self
            def __exit__(self, *a): pass
            def add_task(self, *a, **kw): return None
        return _Dummy()


def print_code(code: str, language: str = "yaml") -> None:
    if RICH:
        _console.print(Syntax(code, language, theme="monokai", line_numbers=False))
    else:
        print(code)


def print_key_value(pairs: list[tuple], title: str = "") -> None:
    """Print a list of (key, value) pairs nicely."""
    if title:
        print_rule(title)
    for k, v in pairs:
        if RICH:
            _console.print(f"  [dim]{k}:[/dim] [bold]{v}[/bold]")
        else:
            print(f"  {k}: {v}")
