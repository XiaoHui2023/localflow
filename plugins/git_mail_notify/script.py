from __future__ import annotations

import re
from pathlib import Path

from automation import (
    Script,
    badge,
    col,
    detail,
    div,
    labeled,
    row,
    spacer,
    summary,
    text,
    var_ref,
)
from plugins.diff_render import render_git_update
from plugins.git_update import get_last_update
from plugins.mail_send import MailProfile, send_mail

_ANSI_ESCAPE = re.compile(r"\x1b\[[0-9;]*m")


def _parse_addr_list(raw: str) -> list[str]:
    return [part.strip() for part in raw.split(",") if part.strip()]


def _strip_ansi(text: str) -> str:
    return _ANSI_ESCAPE.sub("", text)


def _mail_profile_from_variables(variables) -> MailProfile:
    to_addrs = _parse_addr_list(str(variables.get("mail_to_addrs", "")))
    cc_addrs = _parse_addr_list(str(variables.get("mail_cc_addrs", "")))
    return MailProfile(
        smtp_host=str(variables.get("smtp_host", "")).strip(),
        smtp_port=int(variables.get("smtp_port", 587)),
        username=str(variables.get("smtp_username", "")),
        password=str(variables.get("smtp_password", "")),
        from_addr=str(variables.get("mail_from_addr", "")).strip(),
        from_name=str(variables.get("mail_from_name", "")),
        to_addrs=to_addrs,
        cc_addrs=cc_addrs,
        use_ssl=bool(variables.get("smtp_use_ssl", False)),
        use_starttls=bool(variables.get("smtp_use_starttls", True)),
    )


class GitMailNotifyScript(Script):
    """Git 更新邮件：查询仓库、渲染 diff、经 SMTP 发送。"""

    def build_view_template(self):
        return div(
            summary(
                row(
                    badge(var_ref("repo_path"), tone="primary"),
                    spacer(size="sm"),
                    badge(var_ref("phase"), tone="warning"),
                ),
                row(
                    text(var_ref("commit_line"), muted=True),
                ),
            ),
            detail(
                col(
                    labeled("仓库", var_ref("repo_path")),
                    labeled("主题前缀", var_ref("subject_prefix")),
                    labeled("收件人", var_ref("mail_to_addrs")),
                    labeled("SMTP", var_ref("smtp_host")),
                    labeled("上次 HEAD", var_ref("previous_hash")),
                    gap="md",
                ),
            ),
        )

    def run(self) -> None:
        self.variables.set("phase", "查询 Git")
        repo = Path(str(self.variables.get("repo_path", ""))).expanduser()
        if not repo.is_dir():
            raise ValueError(f"仓库目录不存在: {repo}")

        update = get_last_update(repo)
        commit = update.commit
        branch = update.branch or "HEAD"
        self.variables.set(
            "commit_line",
            f"{commit.short_hash} {commit.subject} ({branch})",
        )

        rendered = render_git_update(update)
        print(rendered)

        self.variables.set("phase", "发送邮件")
        profile = _mail_profile_from_variables(self.variables)
        if not profile.smtp_host:
            raise ValueError("smtp_host 不能为空")
        if not profile.from_addr:
            raise ValueError("mail_from_addr 不能为空")

        prefix = str(self.variables.get("subject_prefix", "Git 更新")).strip()
        subject = f"{prefix} {commit.short_hash} {commit.subject}".strip()
        body = _strip_ansi(rendered)

        result = send_mail(profile, subject=subject, body=body, html=False)

        self.variables.set("phase", "完成")
        self.variables.set("mail_subject", subject)
        self.variables.set("mail_message_id", result.message_id or "")
        self.variables.set("mail_recipients", ", ".join(result.recipients))
        self.variables.set("commit_hash", commit.short_hash)
        self.variables.set("commit_subject", commit.subject)

    def build_result_template(self):
        return div(
            summary(
                row(
                    badge(var_ref("commit_hash"), tone="primary"),
                    text(" "),
                    text(var_ref("commit_subject")),
                    spacer(size="sm"),
                    badge("已发送", tone="success"),
                ),
            ),
            detail(
                col(
                    labeled("邮件主题", var_ref("mail_subject")),
                    labeled("收件人", var_ref("mail_recipients")),
                    labeled("Message-ID", var_ref("mail_message_id")),
                    labeled("仓库", var_ref("repo_path")),
                    labeled("错误", var_ref("error_message")),
                    gap="md",
                ),
            ),
        )
