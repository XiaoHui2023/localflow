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
    max_bytes: int = 32 * 1024 * 1024,
) -> tuple[SimResultStatus, str]:
    """按 pass / fail 正则判定仿真日志结果。

    Args:
        log_path: 仿真日志文件路径。
        pass_regex: 命中则 PASS（必填）。
        fail_regex: 命中则 FAIL，优先于 pass；留空时仅检查 pass。
        max_bytes: 完整正则读取的字节预算；超限返回 ERROR，不对截断片段判定。

    Returns:
        状态与说明；PASS 时说明为空字符串。
    """
    if not pass_regex.strip():
        return "ERROR", "pass 正则表达式不能为空"
    if max_bytes <= 0:
        return "ERROR", "完整正则解析预算必须大于零"

    if not log_path.is_file():
        return "ERROR", f"日志文件不存在: {log_path}"

    try:
        with log_path.open("rb") as stream:
            raw = stream.read(max_bytes + 1)
        if len(raw) > max_bytes:
            return "ERROR", "日志超过完整正则解析预算，请使用流式日志判定"
        content = raw.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    except OSError as exc:
        return "ERROR", f"无法读取日志: {exc}"

    try:
        passed = re.compile(pass_regex, re.MULTILINE)
    except re.error as exc:
        return "ERROR", f"pass 正则无效: {exc}"

    fail_pattern = fail_regex.strip()
    if fail_pattern:
        try:
            if re.search(fail_pattern, content, re.MULTILINE):
                return "FAIL", "日志匹配 fail 正则表达式"
        except re.error as exc:
            return "ERROR", f"fail 正则无效: {exc}"
    if passed.search(content):
        return "PASS", ""
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
    if max_chars <= 0:
        return ""
    with log_path.open("rb") as stream:
        stream.seek(max(0, log_path.stat().st_size - max_chars * 4 - 4))
        text = stream.read(max_chars * 4 + 4).decode("utf-8", errors="replace")
        text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text[-max_chars:]
