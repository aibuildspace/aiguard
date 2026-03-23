from __future__ import annotations

import importlib.util
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from aiguard.shields.models import (
    ActionType,
    PatternDefinition,
    PhaseType,
    SeverityLevel,
    ShieldDefinition,
)

logger = logging.getLogger(__name__)

_VALID_ACTIONS = {"block", "warn", "sanitize", "log", "pass"}
_VALID_PHASES = {"pre_request", "post_response", "both"}
_VALID_SEVERITIES = {"critical", "high", "medium", "low", "info"}
_VALID_TARGETS = {"messages", "tool_results", "system_prompt", "all_text"}


_VALID_TYPES = {"pattern", "logic", "llm"}


def find_shield_file(shield_dir: Path) -> Path | None:
    """Return shield.yaml if it exists (primary format)."""
    for name in ("shield.yaml", "shield.yml"):
        p = shield_dir / name
        if p.exists():
            return p
    return None


def read_shield(file_path: Path) -> tuple[dict, str]:
    """Read a shield.yaml file. Returns (config_dict, description_text)."""
    raw = file_path.read_text(encoding="utf-8")
    data = yaml.safe_load(raw) or {}
    return data, data.get("description", "")


def write_shield(shield_dir: Path, data: dict, description: str) -> Path:
    """Write shield.yaml with the given config."""
    data["description"] = description
    path = shield_dir / "shield.yaml"
    yaml_text = yaml.dump(data, default_flow_style=False, sort_keys=False, allow_unicode=True)
    path.write_text(yaml_text, encoding="utf-8")
    return path


def load_shields(shields_dirs: list[str]) -> dict[str, ShieldDefinition]:
    """Scan directories and load shield definitions (shield.yaml)."""
    shields: dict[str, ShieldDefinition] = {}
    for base_dir in shields_dirs:
        base = Path(base_dir)
        if not base.exists():
            continue
        for shield_dir in sorted(base.iterdir()):
            if not shield_dir.is_dir():
                continue
            shield_file = find_shield_file(shield_dir)
            if not shield_file:
                continue
            try:
                shield = _load_shield(shield_dir, shield_file)
                shields[shield.id] = shield
            except Exception as exc:
                logger.warning("Failed to load shield from %s: %s", shield_dir, exc)
    return shields


def _load_shield(shield_dir: Path, shield_file: Path) -> ShieldDefinition:
    data, description = read_shield(shield_file)
    _validate(data, shield_file)

    patterns = [
        PatternDefinition(
            id=p["id"],
            type=p.get("type", "regex"),
            field=p.get("field", "content"),
            pattern=p.get("pattern", ""),
            keywords=p.get("keywords", []),
            role=p.get("role"),
            severity=p.get("severity", "medium"),
            action=p.get("action", "warn"),
            replacement=p.get("replacement"),
            description=p.get("description", ""),
        )
        for p in data.get("patterns", [])
    ]

    logic_module: str | None = None
    if lm := data.get("logic_module"):
        logic_path = shield_dir / lm
        if logic_path.exists():
            logic_module = str(logic_path)

    return ShieldDefinition(
        id=data["id"],
        name=data["name"],
        version=str(data.get("version", "1.0.0")),
        type=data.get("type", "pattern"),
        description=description or data.get("description", ""),
        author=data.get("author", ""),
        tags=data.get("tags", []),
        targets=data.get("targets", ["messages"]),
        phase=data.get("phase", "pre_request"),
        default_action=data.get("default_action", "warn"),
        severity=data.get("severity", "medium"),
        patterns=patterns,
        logic_module=logic_module,
        params=data.get("params", {}),
        shield_dir=str(shield_dir),
        enabled=data.get("enabled", True),
    )


def _validate(data: dict, path: Path) -> None:
    missing = {"id", "name"} - set(data.keys())
    if missing:
        raise ValueError(f"Missing required fields {missing} in {path}")
    if not re.match(r"^[a-z0-9_]+$", data["id"]):
        raise ValueError(f"Invalid shield id: {data['id']!r}")
    if data.get("phase", "pre_request") not in _VALID_PHASES:
        raise ValueError(f"Invalid phase: {data.get('phase')!r}")
    if data.get("default_action", "warn") not in _VALID_ACTIONS:
        raise ValueError(f"Invalid default_action: {data.get('default_action')!r}")
    if data.get("severity", "medium") not in _VALID_SEVERITIES:
        raise ValueError(f"Invalid severity: {data.get('severity')!r}")


def import_logic_module(module_path: str):
    """Dynamically import a shield's logic.py."""
    spec = importlib.util.spec_from_file_location("_shield_logic", module_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module from {module_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)  # type: ignore[attr-defined]
    return module
