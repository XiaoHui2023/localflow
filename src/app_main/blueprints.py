from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from plugin_loader import repo_root

_FILENAME_SAFE = re.compile(r"[^0-9a-zA-Z._-]+")


def _blueprints_dir() -> Path:
    path = (repo_root() / ".localflow" / "blueprints").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _blueprint_path(blueprint_id: str) -> Path:
    safe = _FILENAME_SAFE.sub("_", blueprint_id.strip())
    if not safe:
        raise ValueError("无效的蓝图 ID")
    return _blueprints_dir() / f"{safe}.json"


def list_blueprints(*, script_id: str | None = None) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for file in sorted(_blueprints_dir().glob("*.json")):
        try:
            data = json.loads(file.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        if not isinstance(data, dict) or "id" not in data:
            continue
        if script_id is not None and data.get("script_id") != script_id:
            continue
        items.append(
            {
                "id": data["id"],
                "name": data.get("name", ""),
                "script_id": data.get("script_id", ""),
                "script_name": data.get("script_name", ""),
                "is_batch": bool(data.get("is_batch")),
                "updated_at": data.get("updated_at"),
            },
        )
    items.sort(key=lambda item: item.get("updated_at") or "", reverse=True)
    return items


def get_blueprint(blueprint_id: str) -> dict[str, Any] | None:
    path = _blueprint_path(blueprint_id)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    return data


def save_blueprint(body: dict[str, Any]) -> dict[str, Any]:
    name = str(body.get("name", "")).strip()
    script_id = str(body.get("script_id", "")).strip()
    if not name:
        raise ValueError("蓝图名称不能为空")
    if not script_id:
        raise ValueError("script_id 不能为空")

    blueprint_id = str(body.get("id") or uuid.uuid4())
    is_batch = bool(body.get("is_batch"))
    now = _now_iso()
    existing = get_blueprint(blueprint_id) if body.get("id") else None

    record: dict[str, Any] = {
        "id": blueprint_id,
        "name": name,
        "script_id": script_id,
        "script_name": str(body.get("script_name", "")),
        "is_batch": is_batch,
        "variables": body.get("variables") if not is_batch else None,
        "batch_params": body.get("batch_params") if is_batch else None,
        "created_at": existing.get("created_at") if existing else now,
        "updated_at": now,
    }
    path = _blueprint_path(blueprint_id)
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def delete_blueprint(blueprint_id: str) -> bool:
    path = _blueprint_path(blueprint_id)
    if not path.is_file():
        return False
    path.unlink()
    return True


def clear_blueprints() -> None:
    for file in _blueprints_dir().glob("*.json"):
        file.unlink(missing_ok=True)
