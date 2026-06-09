from __future__ import annotations

from pathlib import Path

from plugins.git_update import GitRepoUpdatePayload, GitUpdateAutomation

from .script import GitMailNotifyScript


def attach_git_update_watch(
    script: GitMailNotifyScript,
    *,
    name: str = "git_mail_notify",
    repo_path: Path | str,
    interval: float = 60.0,
) -> GitUpdateAutomation:
    """把 Script 挂到 Git HEAD 轮询；有更新时写入触发信息并 ``start()``。

    Args:
        script: 已注册的 Git 邮件 Script 实例。
        name: Automation 实例名。
        repo_path: 监视的本地仓库目录。
        interval: 轮询间隔（秒）。

    Returns:
        已注册监听函数的 ``GitUpdateAutomation`` 实例。
    """
    resolved = Path(repo_path).resolve()
    automation = GitUpdateAutomation(
        name=name,
        repo_path=resolved,
        interval=interval,
    )

    @automation.register
    async def _on_git_update(payload: GitRepoUpdatePayload) -> None:
        if script.status.value == "running":
            print("Git 邮件通知跳过：上次任务仍在运行")
            return
        commit = payload.update.commit
        script.variables.set("repo_path", str(payload.update.repo_path))
        script.variables.set("previous_hash", payload.previous_hash)
        script.variables.set("phase", "由 git 触发")
        print(
            "Git 更新，发送邮件:",
            f"{payload.previous_hash[:7]} -> {commit.short_hash}",
            commit.subject,
        )
        script.start()

    return automation
