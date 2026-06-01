from __future__ import annotations

import mimetypes
import sys
from pathlib import Path


def repo_root() -> Path:
    """开发态仓库根目录（含 frontend/）。"""
    return Path(__file__).resolve().parents[2]


def dist_dir() -> Path:
    """React 构建产物目录。"""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path.cwd()))
        bundled = base / "frontend" / "dist"
        if bundled.is_dir():
            return bundled
    local = repo_root() / "frontend" / "dist"
    return local


def resolve_static(path: str) -> Path | None:
    """将 URL 路径映射到 dist 内文件；目录或未知扩展名回退 index.html。"""
    root = dist_dir()
    if not root.is_dir():
        return None

    rel = path.lstrip("/")
    if rel == "" or rel.endswith("/"):
        candidate = root / "index.html"
        return candidate if candidate.is_file() else None

    candidate = (root / rel).resolve()
    try:
        candidate.relative_to(root.resolve())
    except ValueError:
        return None

    if candidate.is_file():
        return candidate

    if "." not in Path(rel).name:
        index = root / "index.html"
        if index.is_file():
            return index
    return None


def guess_content_type(path: Path) -> str:
    ctype, _ = mimetypes.guess_type(str(path))
    return ctype or "application/octet-stream"
