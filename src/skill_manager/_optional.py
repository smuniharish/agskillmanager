"""Lazy imports for optional extras."""

from __future__ import annotations

from importlib import import_module
from typing import Any

from skill_manager.errors import OptionalDependencyError


def optional_import(module: str, extra: str) -> Any:
    """Import an optional dependency, naming the extra to install when it is missing."""
    try:
        return import_module(module)
    except ImportError as error:
        raise OptionalDependencyError(
            f"this integration requires the {extra!r} extra: pip install 'agskillmanager[{extra}]'"
        ) from error
