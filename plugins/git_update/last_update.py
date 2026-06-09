from __future__ import annotations

import subprocess
from pathlib import Path

from .models import GitCommitInfo, GitDiffStats, GitFileChange, GitLastUpdate

_GIT = "git"
_FIELD_SEP = "\x1e"
_RECORD_SEP = "\x1f"


def get_head_hash(repo_path: str | Path) -> str:
    """读取仓库当前 HEAD 完整提交哈希。

    Args:
        repo_path: 本地 Git 仓库目录。

    Returns:
        HEAD 指向的提交哈希。

    Raises:
        ValueError: 路径无效、不是 Git 仓库，或尚无提交。
        RuntimeError: ``git`` 命令执行失败。
    """
    repo = Path(repo_path).expanduser().resolve()
    if not repo.is_dir():
        raise ValueError(f"仓库路径不存在或不是目录: {repo}")

    _ensure_git_repo(repo)
    head = _git_output(repo, "rev-parse", "HEAD").strip()
    if not head:
        raise ValueError(f"仓库尚无提交: {repo}")
    return head


def get_last_update(repo_path: str | Path) -> GitLastUpdate:
    """读取仓库 HEAD 最近一次提交的元数据与 unified diff。

    Args:
        repo_path: 本地 Git 仓库目录。

    Returns:
        含提交信息、逐文件统计与完整 diff 文本的结构体。

    Raises:
        ValueError: 路径不存在、不是 Git 仓库，或尚无提交。
        RuntimeError: ``git`` 命令执行失败。
    """
    repo = Path(repo_path).expanduser().resolve()
    if not repo.is_dir():
        raise ValueError(f"仓库路径不存在或不是目录: {repo}")

    _ensure_git_repo(repo)
    head = _git_output(repo, "rev-parse", "HEAD").strip()
    if not head:
        raise ValueError(f"仓库尚无提交: {repo}")

    branch = _read_branch(repo)
    commit = _read_commit(repo, head)
    files, stats = _read_file_changes(repo, head)
    diff = _read_diff(repo, head)

    return GitLastUpdate(
        repo_path=repo,
        branch=branch,
        commit=commit,
        diff=diff,
        files=files,
        stats=stats,
    )


def _ensure_git_repo(repo: Path) -> None:
    try:
        _git_output(repo, "rev-parse", "--git-dir")
    except RuntimeError as exc:
        raise ValueError(f"不是 Git 仓库: {repo}") from exc


def _read_branch(repo: Path) -> str | None:
    try:
        name = _git_output(repo, "rev-parse", "--abbrev-ref", "HEAD").strip()
    except RuntimeError:
        return None
    if name == "HEAD":
        return None
    return name


def _read_commit(repo: Path, commit_hash: str) -> GitCommitInfo:
    fmt = (
        f"%H{_FIELD_SEP}%h{_FIELD_SEP}%an{_FIELD_SEP}%ae{_FIELD_SEP}%at"
        f"{_FIELD_SEP}%cn{_FIELD_SEP}%ce{_FIELD_SEP}%ct{_FIELD_SEP}%P"
        f"{_FIELD_SEP}%s{_FIELD_SEP}%b{_RECORD_SEP}"
    )
    raw = _git_output(repo, "log", "-1", commit_hash, f"--format={fmt}")
    record = raw.split(_RECORD_SEP, 1)[0]
    parts = record.split(_FIELD_SEP)
    if len(parts) != 11:
        raise RuntimeError(f"无法解析提交元数据: {commit_hash}")

    parents_raw = parts[8].strip()
    parents = tuple(parents_raw.split()) if parents_raw else ()

    return GitCommitInfo(
        hash=parts[0],
        short_hash=parts[1],
        author_name=parts[2],
        author_email=parts[3],
        author_timestamp=int(parts[4]),
        committer_name=parts[5],
        committer_email=parts[6],
        committer_timestamp=int(parts[7]),
        parents=parents,
        subject=parts[9],
        body=parts[10].rstrip("\n"),
    )


def _read_file_changes(
    repo: Path,
    commit_hash: str,
) -> tuple[tuple[GitFileChange, ...], GitDiffStats]:
    status_lines = _git_output(
        repo,
        "diff-tree",
        "--no-commit-id",
        "--name-status",
        "-r",
        commit_hash,
    ).splitlines()

    numstat_lines = _git_output(
        repo,
        "diff-tree",
        "--no-commit-id",
        "--numstat",
        "-r",
        commit_hash,
    ).splitlines()

    status_by_path = _parse_name_status(status_lines)
    numstat_by_path = _parse_numstat(numstat_lines)

    paths = sorted(set(status_by_path) | set(numstat_by_path))
    files: list[GitFileChange] = []
    total_insertions = 0
    total_deletions = 0

    for path in paths:
        insertions, deletions = numstat_by_path.get(path, (0, 0))
        total_insertions += insertions
        total_deletions += deletions
        files.append(
            GitFileChange(
                path=path,
                status=status_by_path.get(path, "M"),
                insertions=insertions,
                deletions=deletions,
            )
        )

    stats = GitDiffStats(
        files_changed=len(files),
        insertions=total_insertions,
        deletions=total_deletions,
    )
    return tuple(files), stats


def _parse_name_status(lines: list[str]) -> dict[str, str]:
    result: dict[str, str] = {}
    for line in lines:
        if not line.strip():
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        status = parts[0]
        if status.startswith("R") or status.startswith("C"):
            result[parts[2]] = status[0]
        else:
            result[parts[1]] = status
    return result


def _parse_numstat(lines: list[str]) -> dict[str, tuple[int, int]]:
    result: dict[str, tuple[int, int]] = {}
    for line in lines:
        if not line.strip():
            continue
        insertions_raw, deletions_raw, path = line.split("\t", 2)
        insertions = 0 if insertions_raw == "-" else int(insertions_raw)
        deletions = 0 if deletions_raw == "-" else int(deletions_raw)
        result[path] = (insertions, deletions)
    return result


def _read_diff(repo: Path, commit_hash: str) -> str:
    return _git_output(
        repo,
        "show",
        commit_hash,
        "--format=",
        "--no-color",
        "--patch",
        "--no-ext-diff",
    )


def _git_output(repo: Path, *args: str) -> str:
    try:
        completed = subprocess.run(
            [_GIT, "-C", str(repo), *args],
            capture_output=True,
            text=True,
            check=True,
        )
    except FileNotFoundError as exc:
        raise RuntimeError("未找到 git 命令，请确认已安装并在 PATH 中") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "").strip()
        raise RuntimeError(detail or f"git {' '.join(args)} 失败") from exc
    return completed.stdout
