from __future__ import annotations

from dataclasses import dataclass

from pydantic import BaseModel, ConfigDict, Field, model_validator


@dataclass(frozen=True)
class MailSendResult:
    """一次发信的结果摘要。"""

    recipients: tuple[str, ...]
    message_id: str | None


class MailProfile(BaseModel):
    """SMTP 发信所需的个人与服务器参数。"""

    model_config = ConfigDict(extra="forbid")

    smtp_host: str = Field(..., description="SMTP 服务器主机名或 IP")
    smtp_port: int = Field(default=587, ge=1, le=65535, description="SMTP 端口")
    username: str = Field(default="", description="SMTP 登录名；留空表示不认证")
    password: str = Field(default="", description="SMTP 登录密码或应用专用密码")
    from_addr: str = Field(..., description="发件人邮箱地址")
    from_name: str = Field(default="", description="发件人显示名；留空则仅写邮箱地址")
    reply_to: str = Field(default="", description="回复地址；留空则不设置 Reply-To")
    to_addrs: list[str] = Field(default_factory=list, description="默认收件人列表")
    cc_addrs: list[str] = Field(default_factory=list, description="默认抄送列表")
    bcc_addrs: list[str] = Field(default_factory=list, description="默认密送列表")
    use_ssl: bool = Field(default=False, description="为 true 时使用 SMTP_SSL（常见于 465 端口）")
    use_starttls: bool = Field(
        default=True,
        description="非 SSL 连接时是否在 EHLO 后执行 STARTTLS（常见于 587 端口）",
    )
    timeout: float = Field(default=30.0, gt=0, description="连接与收发超时（秒）")
    local_hostname: str = Field(
        default="",
        description="EHLO 时声明的主机名；留空由系统推断（Ubuntu 上一般为机器名）",
    )
    charset: str = Field(default="utf-8", description="邮件正文编码")

    @model_validator(mode="after")
    def _check_tls_mode(self) -> MailProfile:
        if self.use_ssl and self.use_starttls:
            raise ValueError("use_ssl 与 use_starttls 不能同时为 true")
        return self
