from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from automation import Automation

ActionHandler = Callable[..., Awaitable[Any]]

_actions: dict[str, ActionHandler] = {}


def action(name: str | None = None) -> Callable[[ActionHandler], ActionHandler]:
    """注册可在运行时按名称调用的异步动作。

    Args:
        name: 动作名；省略时使用被装饰函数名。
    """

    def decorator(func: ActionHandler) -> ActionHandler:
        key = name if name is not None else func.__name__
        _actions[key] = func
        return func

    return decorator


def get_action(name: str) -> ActionHandler | None:
    return _actions.get(name)


def all_actions() -> dict[str, ActionHandler]:
    return dict(_actions)


def clear_actions() -> None:
    _actions.clear()


__all__ = [
    "ActionHandler",
    "Automation",
    "action",
    "all_actions",
    "clear_actions",
    "get_action",
]
