from __future__ import annotations

import smtplib
import ssl
from collections.abc import Sequence
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from .models import MailProfile, MailSendResult


def send_mail(
    profile: MailProfile,
    *,
    subject: str,
    body: str,
    html: bool = False,
    to_addrs: Sequence[str] | None = None,
    cc_addrs: Sequence[str] | None = None,
    bcc_addrs: Sequence[str] | None = None,
) -> MailSendResult:
    """按给定 SMTP 参数发送一封邮件。

    Args:
        profile: 服务器、账号与默认收件人等个人配置。
        subject: 邮件主题。
        body: 正文；纯文本或 HTML 由 html 决定。
        html: 为 true 时按 HTML 正文发送，并附带纯文本降级副本。
        to_addrs: 本次收件人；省略时使用 profile 中的默认列表。
        cc_addrs: 本次抄送；省略时使用 profile 中的默认列表。
        bcc_addrs: 本次密送；省略时使用 profile 中的默认列表。

    Returns:
        实际投递的收件人列表与生成的 Message-ID。

    Raises:
        ValueError: 收件人、抄送、密送均为空。
        smtplib.SMTPException: SMTP 连接或投递失败。
    """
    to_list = _merge_addrs(profile.to_addrs, to_addrs)
    cc_list = _merge_addrs(profile.cc_addrs, cc_addrs)
    bcc_list = _merge_addrs(profile.bcc_addrs, bcc_addrs)
    all_recipients = _unique_addrs(to_list + cc_list + bcc_list)
    if not all_recipients:
        raise ValueError("至少需要一个收件人、抄送或密送地址")

    msg = _build_message(
        profile=profile,
        subject=subject,
        body=body,
        html=html,
        to_list=to_list,
        cc_list=cc_list,
    )

    local_hostname = profile.local_hostname or None
    if profile.use_ssl:
        smtp: smtplib.SMTP = smtplib.SMTP_SSL(
            profile.smtp_host,
            profile.smtp_port,
            timeout=profile.timeout,
            local_hostname=local_hostname,
            context=ssl.create_default_context(),
        )
    else:
        smtp = smtplib.SMTP(
            profile.smtp_host,
            profile.smtp_port,
            timeout=profile.timeout,
            local_hostname=local_hostname,
        )
        smtp.ehlo()
        if profile.use_starttls:
            smtp.starttls(context=ssl.create_default_context())
            smtp.ehlo()

    try:
        if profile.username:
            smtp.login(profile.username, profile.password)
        refused = smtp.send_message(msg, to_addrs=all_recipients)
    finally:
        smtp.quit()

    if refused:
        refused_list = ", ".join(sorted(refused))
        raise smtplib.SMTPRecipientsRefused(
            {addr: (code, err) for addr, (code, err) in refused.items()},
        )

    message_id = msg.get("Message-ID")
    return MailSendResult(recipients=tuple(all_recipients), message_id=message_id)


def _merge_addrs(defaults: Sequence[str], override: Sequence[str] | None) -> list[str]:
    if override is not None:
        return list(override)
    return list(defaults)


def _unique_addrs(addrs: Sequence[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for raw in addrs:
        addr = raw.strip()
        if not addr or addr in seen:
            continue
        seen.add(addr)
        result.append(addr)
    return result


def _build_message(
    *,
    profile: MailProfile,
    subject: str,
    body: str,
    html: bool,
    to_list: list[str],
    cc_list: list[str],
) -> EmailMessage:
    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = (
        formataddr((profile.from_name, profile.from_addr))
        if profile.from_name
        else profile.from_addr
    )
    if profile.reply_to:
        msg["Reply-To"] = profile.reply_to
    if to_list:
        msg["To"] = ", ".join(to_list)
    if cc_list:
        msg["Cc"] = ", ".join(cc_list)
    msg["Message-ID"] = make_msgid()

    charset = profile.charset
    if html:
        msg.set_content(_html_to_plain(body), subtype="plain", charset=charset)
        msg.add_alternative(body, subtype="html", charset=charset)
    else:
        msg.set_content(body, subtype="plain", charset=charset)
    return msg


def _html_to_plain(html: str) -> str:
    return html.replace("<br>", "\n").replace("<br/>", "\n").replace("<br />", "\n")
