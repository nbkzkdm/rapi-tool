"""Command modules. Each module exposes register(subparsers)."""

from __future__ import annotations

import importlib
import pkgutil
from pathlib import Path


def load_commands(subparsers) -> None:
    """Discover and register all command modules in this package."""
    package_dir = Path(__file__).parent
    for mod in pkgutil.iter_modules([str(package_dir)]):
        if mod.name.startswith("_"):
            continue
        module = importlib.import_module(f"rapi.commands.{mod.name}")
        reg = getattr(module, "register", None)
        if reg is None:
            continue
        reg(subparsers)
