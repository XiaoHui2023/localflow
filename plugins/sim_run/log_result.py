from __future__ import annotations

import re
from pathlib import Path
from typing import Literal

SimResultStatus = Literal["PASS", "FAIL", "ERROR"]


def resolve_log_path(log_path: str | Path, work_dir: Path) -> Path:
    """把日志路径解析为绝对路径（相对路径相对于工作目录）。

    Args:
        log_path: 用户配置的日志路径。
        work_dir: 仿真工作目录。

    Returns:
        解析后的绝对路径。
    """
    path = Path(str(log_path)).expanduser()
    if path.is_absolute():
        return path.resolve()
    return (work_dir / path).resolve()


def evaluate_log_result(
    log_path: Path,
    *,
    pass_regex: str,
    fail_regex: str = "",
) -> tuple[SimResultStatus, str]:
    """按 pass / fail 正则判定仿真日志结果。

    Args:
        log_path: 仿真日志文件路径。
        pass_regex: 命中则 PASS（必填）。
        fail_regex: 未命中 pass 时再匹配；命中则 FAIL；留空则直接 FAIL。

    Returns:
        状态与说明；PASS 时说明为空字符串。
    """
    if not pass_regex.strip():
        return "ERROR", "pass 正则表达式不能为空"

    if not log_path.is_file():
        return "ERROR", f"日志文件不存在: {log_path}"

    try:
        content = log_path.read_text(encoding="utf-8", errors="replace")
    except OSError as exc:
        return "ERROR", f"无法读取日志: {exc}"

    try:
        if re.search(pass_regex, content, re.MULTILINE):
            return "PASS", ""
    except re.error as exc:
        return "ERROR", f"pass 正则无效: {exc}"

    fail_pattern = fail_regex.strip()
    if fail_pattern:
        try:
            if re.search(fail_pattern, content, re.MULTILINE):
                return "FAIL", "日志匹配 fail 正则表达式"
        except re.error as exc:
            return "ERROR", f"fail 正则无效: {exc}"
        return "FAIL", "未匹配 pass 正则表达式"

    return "FAIL", "未匹配 pass 正则表达式"


def read_log_tail(log_path: Path, *, max_chars: int = 4000) -> str:
    """读取日志末尾片段供界面展示。

    Args:
        log_path: 日志文件路径。
        max_chars: 最多返回的字符数。

    Returns:
        日志尾部文本；文件不存在时返回空字符串。
    """
    if not log_path.is_file():
        return ""
    text = log_path.read_text(encoding="utf-8", errors="replace")
    if len(text) <= max_chars:
        return text
    return text[-max_chars:]
