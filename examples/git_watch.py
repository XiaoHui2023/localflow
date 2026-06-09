from __future__ import annotations

from pathlib import Path

from plugins.git_update import GitRepoUpdatePayload, GitUpdateAutomation

_repo = Path(__file__).resolve().parents[1]

git_watch = GitUpdateAutomation(
    name="git_watch",
    repo_path=_repo,
    interval=30.0,
)


@git_watch.register
async def on_git_update(payload: GitRepoUpdatePayload) -> None:
    commit = payload.update.commit
    print(
        "git 更新:",
        f"{payload.previous_hash[:7]} -> {commit.short_hash}",
        commit.subject,
    )
