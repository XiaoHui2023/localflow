from __future__ import annotations

from pathlib import Path

from .script import GitMailNotifyScript
from .wire import attach_git_update_watch

_DEFAULT_REPO = Path(__file__).resolve().parents[2]

git_mail_notify = GitMailNotifyScript(
    name="Git 更新邮件",
    repo_path=str(_DEFAULT_REPO),
    subject_prefix="Git 更新",
    smtp_host="",
    smtp_port=587,
    smtp_username="",
    smtp_password="",
    mail_from_addr="",
    mail_from_name="Localflow",
    mail_to_addrs="",
    mail_cc_addrs="",
    smtp_use_ssl=False,
    smtp_use_starttls=True,
    previous_hash="",
    commit_line="—",
    commit_hash="—",
    commit_subject="",
    mail_subject="",
    mail_recipients="",
    mail_message_id="",
    phase="待运行",
    error_message="",
    error_traceback="",
)

__all__ = [
    "GitMailNotifyScript",
    "attach_git_update_watch",
    "git_mail_notify",
]
