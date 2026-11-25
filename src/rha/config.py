"""Project configuration: repo root and ``config/settings.yaml`` access."""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
SETTINGS_PATH = REPO_ROOT / "config" / "settings.yaml"


@lru_cache(maxsize=4)
def load_settings(path: str | Path = SETTINGS_PATH) -> dict[str, Any]:
    """Load the settings YAML file."""
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def data_path(key: str, settings: dict[str, Any] | None = None) -> Path:
    """Resolve ``settings['paths'][key]`` to an absolute path under the repo root."""
    s = settings or load_settings()
    p = Path(s["paths"][key])
    return p if p.is_absolute() else REPO_ROOT / p
