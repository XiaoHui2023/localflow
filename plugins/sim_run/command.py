from __future__ import annotations

import string
from collections.abc import Mapping
from typing import Any


class _SafeFormatDict(dict[str, str]):
    def __missing__(self, key: str) -> str:
        raise KeyError(key)


def format_command(template: str, variables: Mapping[str, Any]) -> str:
    """用 Script 变量表填充命令模板（``str.format`` 语法）。

    Args:
        template: 含 ``{project}``、``{case}`` 等占位符的命令字符串。
        variables: 变量名到值的映射；值会转为字符串。

    Returns:
        填充后的可执行命令。

    Raises:
        ValueError: 模板引用了不存在的变量。
    """
    data = {key: str(value) for key, value in variables.items()}
    if "case" not in data and "case_name" in data:
        data["case"] = data["case_name"]
    formatter = string.Formatter()
    for _, field_name, _, _ in formatter.parse(template):
        if field_name is None:
            continue
        root = field_name.split(".")[0].split("[")[0]
        if root not in data:
            raise ValueError(f"命令模板引用了未定义变量: {root}")
    try:
        return template.format_map(_SafeFormatDict(data))
    except KeyError as exc:
        raise ValueError(f"命令模板引用了未定义变量: {exc.args[0]}") from exc
