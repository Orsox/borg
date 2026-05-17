import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)


def _extract_tags(data: dict[str, Any]) -> list[str]:
    tags = data.get("tags", [])
    if isinstance(tags, list):
        return [str(t) for t in tags]
    if isinstance(tags, str):
        return [t.strip() for t in tags.split(",") if t.strip()]
    return []


def _infer_type(data: dict[str, Any], file_path: Path) -> str:
    t = data.get("type", "")
    if isinstance(t, str) and t:
        return t.lower()
    name = file_path.stem.lower()
    if "workflow" in name:
        return "workflow"
    if "skill" in name:
        return "skill"
    if "agent" in name:
        return "agent"
    return "unknown"


def parse_asset_file(file_path: Path) -> dict[str, Any] | None:
    """Parse a YAML or JSON file and extract asset fields. Returns None on parse failure."""
    try:
        content = file_path.read_text(encoding="utf-8", errors="replace")
    except Exception as e:
        logger.warning(f"Cannot read {file_path}: {e}")
        return None

    data: dict[str, Any] = {}
    suffix = file_path.suffix.lower()

    if suffix in (".yaml", ".yml"):
        try:
            parsed = yaml.safe_load(content)
            if isinstance(parsed, dict):
                data = parsed
        except yaml.YAMLError as e:
            logger.warning(f"YAML parse error in {file_path}: {e}")
            # Use empty data — name will fall back to filename
    elif suffix == ".json":
        try:
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                data = parsed
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error in {file_path}: {e}")
            return None
    else:
        return None

    name = data.get("name")
    if not isinstance(name, str) or not name.strip():
        name = file_path.stem

    description = data.get("description")
    if not isinstance(description, str):
        description = None

    return {
        "name": name.strip(),
        "type": _infer_type(data, file_path),
        "description": description,
        "tags": json.dumps(_extract_tags(data)),
        "file_path": str(file_path.resolve()),
        "raw_content": content,
        "last_scanned": datetime.now(timezone.utc),
    }


EXCLUDED_DIRS = {"borgos_copies", ".git", "__pycache__", "node_modules", ".venv", "venv"}


def scan_directory(archon_path: str) -> list[dict[str, Any]]:
    """Recursively scan archon_path for YAML/JSON asset files."""
    path = Path(archon_path)

    if not path.exists():
        raise FileNotFoundError(f"ARCHON_PATH does not exist: {archon_path}")

    if not path.is_dir():
        raise NotADirectoryError(f"ARCHON_PATH is not a directory: {archon_path}")

    assets = []
    for ext in ("*.yaml", "*.yml", "*.json"):
        for file_path in path.rglob(ext):
            if not file_path.is_file():
                continue
            # Skip excluded directories
            if any(part in EXCLUDED_DIRS for part in file_path.parts):
                continue
            asset = parse_asset_file(file_path)
            if asset is not None:
                assets.append(asset)

    return assets
