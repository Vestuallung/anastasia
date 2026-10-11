"""Application defaults plus an optional user TOML file."""

from __future__ import annotations

import copy
import os
import shutil
import sys
import tomllib
from functools import lru_cache
from pathlib import Path
from typing import Any

PACKAGE_DIR = Path(__file__).resolve().parent


def config_path() -> Path | None:
    explicit = os.environ.get("KARAOKE_CONFIG")
    if explicit:
        return Path(explicit).expanduser().resolve()
    root = Path(os.environ.get("KARAOKE_HOME", Path.cwd()))
    candidate = root / "config.toml"
    return candidate.resolve() if candidate.is_file() else None


def config_directory() -> Path:
    path = config_path()
    return path.parent if path else Path(os.environ.get("KARAOKE_HOME", Path.cwd())).resolve()


def _merge(base: dict, updates: dict) -> dict:
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _merge(base[key], value)
        else:
            base[key] = value
    return base


@lru_cache(maxsize=1)
def load_config() -> dict[str, Any]:
    with (PACKAGE_DIR / "config/defaults.toml").open("rb") as handle:
        defaults = tomllib.load(handle)
    path = config_path()
    if path:
        with path.open("rb") as handle:
            _merge(defaults, tomllib.load(handle))
    return defaults


def section(name: str) -> dict[str, Any]:
    return copy.deepcopy(load_config()[name])


def configured_path(value: str) -> Path:
    if value.startswith("bundle:"):
        return PACKAGE_DIR / value.removeprefix("bundle:")
    path = Path(value).expanduser()
    return path if path.is_absolute() else config_directory() / path


def tool_path(name: str) -> str:
    value = os.environ.get(f"KARAOKE_{name.upper()}", section("tools")[name])
    found = shutil.which(value)
    if "/" in value or "\\" in value:
        return found or str(configured_path(value))
    return found or value


def yohane_python() -> Path:
    value = os.environ.get("KARAOKE_YOHANE_PYTHON") or section("runtime")["yohane_python"]
    if value:
        return configured_path(value)
    root = Path(os.environ.get("KARAOKE_HOME", config_directory())) / ".runtime/align"
    candidate = root / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    return candidate if candidate.is_file() else Path(sys.executable)
