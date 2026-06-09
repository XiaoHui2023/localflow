from __future__ import annotations

from rich.console import Console
from rich.theme import Theme

THEME = Theme(
    {
        "diff.title": "bold #e5c07b",
        "diff.file": "bold #d19a66",
        "diff.hunk": "#61afef",
        "diff.add": "#98c379",
        "diff.del": "#e06c75",
        "diff.ctx": "#abb2bf",
        "diff.meta": "#5c6370",
    }
)


def make_console(*, width: int | None = None) -> Console:
    return Console(
        theme=THEME,
        color_system="truecolor",
        force_terminal=True,
        legacy_windows=False,
        width=width,
    )
