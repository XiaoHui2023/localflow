from __future__ import annotations

import json
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

from plugin_loader import repo_root

if TYPE_CHECKING:
    from automation.script.base import Script

_FILENAME_SAFE = re.compile(r"[^0-9a-zA-Z._-]+")
_DEFAULT_LIMIT = 100


def _history_dir() -> Path:
    path = (repo_root() / ".localflow" / "run_history").resolve()
    path.mkdir(parents=True, exist_ok=True)
    return path


def _history_path(history_id: str) -> Path:
    safe = _FILENAME_SAFE.sub("_", history_id.strip())
    if not safe:
        raise ValueError("无效的历史记录 ID")
    return _history_dir() / f"{safe}.json"


def _read_terminal(path_str: str | None) -> str:
    if not path_str:
        return ""
    path = Path(path_str)
    if not path.is_file():
        return ""
    try:
        return path.read_text(encoding="utf-8")
    except OSError:
        return ""


def record_from_script(script: Script) -> dict[str, Any] | None:
    desc = script.describe()
    status = desc.get("status")
    if status not in ("succeeded", "failed", "cancelled"):
        return None

    is_batch = bool(desc.get("is_batch"))
    record: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "script_id": desc["id"],
        "script_name": desc.get("name", ""),
        "script_type": desc.get("type", ""),
        "is_batch": is_batch,
        "status": status,
        "variables": desc.get("user_variables") if not is_batch else None,
        "batch_params": desc.get("batch_params") if is_batch else None,
        "started_at": desc.get("started_at"),
        "finished_at": desc.get("finished_at") or datetime.now(timezone.utc).isoformat(),
        "error": desc.get("error"),
        "error_traceback": desc.get("error_traceback"),
        "terminal_log_path": desc.get("terminal_log_path"),
        "result": desc.get("result"),
    }
    path = _history_path(record["id"])
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def list_run_history(
    *,
    script_id: str | None = None,
    limit: int = _DEFAULT_LIMIT,
) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for file in sorted(_history_dir().glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True):
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
                "script_id": data.get("script_id", ""),
                "script_name": data.get("script_name", ""),
                "status": data.get("status", ""),
                "is_batch": bool(data.get("is_batch")),
                "finished_at": data.get("finished_at"),
                "error": data.get("error"),
            },
        )
        if len(items) >= limit:
            break
    return items


def get_run_history(history_id: str) -> dict[str, Any] | None:
    path = _history_path(history_id)
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        return None
    data = dict(data)
    data["terminal"] = _read_terminal(data.get("terminal_log_path"))
    return data


def clear_run_history() -> None:
    for file in _history_dir().glob("*.json"):
        file.unlink(missing_ok=True)
