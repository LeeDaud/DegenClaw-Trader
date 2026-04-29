"""加载 scoring.yaml 配置"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover
    yaml = None  # type: ignore[assignment]


def _find_config() -> Path:
    """向上查找 config/scoring.yaml"""
    cwd = Path.cwd()
    for parent in [cwd] + list(cwd.parents):
        candidate = parent / "config" / "scoring.yaml"
        if candidate.exists():
            return candidate
    # fallback: 包同级目录
    return Path(__file__).resolve().parent.parent / "config" / "scoring.yaml"


_DEFAULT: dict[str, Any] = {}


def load_config() -> dict[str, Any]:
    if not yaml:
        return _DEFAULT
    path = _find_config()
    if not path.exists():
        return _DEFAULT
    with open(path, encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("scoring", _DEFAULT)
