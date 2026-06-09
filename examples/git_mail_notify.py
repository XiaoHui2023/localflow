from __future__ import annotations

from pathlib import Path

from plugins.git_mail_notify import attach_git_update_watch, git_mail_notify

_repo = Path(__file__).resolve().parents[1]

git_mail_notify_watch = attach_git_update_watch(
    git_mail_notify,
    repo_path=_repo,
    interval=60.0,
)
