from __future__ import annotations

from typing import Any

from automation import all_instances


def _script_brief(script: Any) -> dict[str, Any]:
    return {
        "id": script.instance_id,
        "name": script.name,
        "type": script.__class__.__name__,
        "status": script.status.value,
    }


def automation_descriptors() -> list[dict[str, Any]]:
    """汇总 Automation 实例、已注册事件与挂接的 Script。"""
    items: list[dict[str, Any]] = []
    for automation in all_instances():
        scripts = [_script_brief(script) for script in automation.scripts()]
        handlers = [
            {
                "name": handler_desc.name,
                "qualname": handler_desc.qualname,
                "module": handler_desc.module,
            }
            for handler_desc in automation.handler_descriptors()
        ]
        items.append(
            {
                "name": automation.name,
                "type": type(automation).__name__,
                "mode": automation.mode,
                "interval": automation.interval,
                "is_running": automation.is_running,
                "scripts": scripts,
                "handlers": handlers,
            },
        )
    return items
