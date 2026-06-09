from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class GitFileChange:
    """单次提交内某个路径的变更统计。"""

    path: str
    status: str
    insertions: int
    deletions: int


@dataclass(frozen=True)
class GitDiffStats:
    """单次提交的整体 diff 统计。"""

    files_changed: int
    insertions: int
    deletions: int


@dataclass(frozen=True)
class GitCommitInfo:
    """一次 Git 提交的关键元数据。"""

    hash: str
    short_hash: str
    subject: str
    body: str
    author_name: str
    author_email: str
    author_timestamp: int
    committer_name: str
    committer_email: str
    committer_timestamp: int
    parents: tuple[str, ...]


@dataclass(frozen=True)
class GitLastUpdate:
    """仓库当前 HEAD 指向的最近一次提交及其 diff。"""

    repo_path: Path
    branch: str | None
    commit: GitCommitInfo
    diff: str
    files: tuple[GitFileChange, ...]
    stats: GitDiffStats


@dataclass(frozen=True)
class GitRepoUpdatePayload:
    """Git 仓库 HEAD 相对上次轮询发生变更时的事件载荷。"""

    previous_hash: str
    update: GitLastUpdate
