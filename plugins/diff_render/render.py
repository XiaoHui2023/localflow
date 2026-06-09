from __future__ import annotations

import sys
from typing import IO, TYPE_CHECKING

from rich.console import Console
from rich.markup import escape
from rich.panel import Panel
from rich.text import Text

from .theme import make_console

if TYPE_CHECKING:
    from plugins.git_update.models import GitLastUpdate


def render_diff(diff: str, *, width: int | None = None) -> str:
    """将 unified diff 文本渲染为带终端颜色的字符串。

    Args:
        diff: ``git show`` / ``git diff`` 风格的 unified diff 原文。
        width: 终端宽度；省略时由 Rich 自动推断。

    Returns:
        含 ANSI 转义序列的渲染结果，可直接写入终端。
    """
    console = make_console(width=width)
    with console.capture() as capture:
        _print_diff_body(console, diff)
    return capture.get()


def print_diff(diff: str, *, file: IO[str] | None = None, width: int | None = None) -> None:
    """将渲染后的 diff 写入输出流（默认标准输出）。

    Args:
        diff: unified diff 原文。
        file: 目标流；默认 ``sys.stdout``。
        width: 终端宽度；省略时由 Rich 自动推断。
    """
    out = file if file is not None else sys.stdout
    text = render_diff(diff, width=width)
    out.write(text)
    if text and not text.endswith("\n"):
        out.write("\n")


def render_git_update(update: GitLastUpdate, *, width: int | None = None) -> str:
    """渲染 ``GitLastUpdate``：提交摘要面板 + 着色 diff。

    Args:
        update: ``plugins.git_update`` 的查询或事件载荷结果。
        width: 终端宽度；省略时由 Rich 自动推断。

    Returns:
        含 ANSI 转义序列的渲染结果。
    """
    commit = update.commit
    stats = update.stats
    branch = update.branch or "HEAD"
    header = (
        f"[diff.title]{escape(commit.short_hash)}[/]  {escape(commit.subject)}\n"
        f"[diff.meta]{escape(branch)} · {escape(commit.author_name)} "
        f"<{escape(commit.author_email)}>[/]\n"
        f"[diff.add]+{stats.insertions}[/] "
        f"[diff.del]-{stats.deletions}[/] "
        f"[diff.meta]({stats.files_changed} files)[/]"
    )
    if commit.body.strip():
        header += f"\n[diff.ctx]{escape(commit.body.strip())}[/]"

    console = make_console(width=width)
    with console.capture() as capture:
        console.print(Panel(header, title="Git 提交", border_style="diff.hunk"))
        _print_diff_body(console, update.diff)
    return capture.get()


def _print_diff_body(console: Console, diff: str) -> None:
    if not diff.strip():
        console.print(Text("（无 diff 内容）", style="diff.meta"))
        return
    for line in diff.splitlines():
        console.print(_style_diff_line(line))


def _style_diff_line(line: str) -> Text:
    if line.startswith(("diff --git", "index ", "rename ", "similarity ")):
        return Text(line, style="diff.file")
    if line.startswith("---") or line.startswith("+++"):
        return Text(line, style="diff.file")
    if line.startswith("@@"):
        return Text(line, style="diff.hunk")
    if line.startswith("+"):
        return Text(line, style="diff.add")
    if line.startswith("-"):
        return Text(line, style="diff.del")
    if line.startswith("\\"):
        return Text(line, style="diff.meta")
    return Text(line, style="diff.ctx")
