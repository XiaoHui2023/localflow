# mail_send

通过 SMTP 发送邮件。服务器、账号、发件人与默认收件人等**个人参数**由调用方构造 `MailProfile` 传入，插件内不读环境变量、不写死密钥。适用于 Ubuntu 上对接 QQ/163/Gmail 或本机 Postfix。

限定名：`plugins.mail_send`。

## 导出

| 符号 | 说明 |
| --- | --- |
| `MailProfile` | SMTP 与个人参数（主机、端口、账号、发件人、默认收件人等） |
| `send_mail(profile, subject, body, ...)` | 发送一封邮件，返回 `MailSendResult` |
| `MailSendResult` | `recipients`、`message_id` |

## MailProfile 字段

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `smtp_host` | 必填 | SMTP 主机 |
| `smtp_port` | `587` | 端口 |
| `username` | 空 | 登录名；空表示不认证（本机中继常见） |
| `password` | 空 | 密码或应用专用密码 |
| `from_addr` | 必填 | 发件人邮箱 |
| `from_name` | 空 | 显示名 |
| `reply_to` | 空 | 回复地址 |
| `to_addrs` / `cc_addrs` / `bcc_addrs` | `[]` | 默认收件人；单次调用可覆盖 |
| `use_ssl` | `false` | `true` 时用 SMTP_SSL（如 465） |
| `use_starttls` | `true` | 非 SSL 时是否 STARTTLS（如 587）；与 `use_ssl` 互斥 |
| `timeout` | `30` | 超时（秒） |
| `local_hostname` | 空 | EHLO 主机名；空由系统推断 |
| `charset` | `utf-8` | 正文编码 |

## 用法

```python
from plugins.mail_send import MailProfile, send_mail

profile = MailProfile(
    smtp_host="smtp.example.com",
    smtp_port=587,
    username="user@example.com",
    password="app-password",
    from_addr="user@example.com",
    from_name="Localflow",
    to_addrs=["ops@example.com"],
    use_starttls=True,
    use_ssl=False,
)

result = send_mail(
    profile,
    subject="任务完成",
    body="命令已执行成功。",
)
print(result.message_id, result.recipients)
```

HTML 正文：

```python
send_mail(
    profile,
    subject="Git 更新",
    body="<p>仓库有<strong>新提交</strong></p>",
    html=True,
)
```

单次覆盖收件人：

```python
send_mail(profile, subject="告警", body="...", to_addrs=["oncall@example.com"])
```

与 `git_update`、`diff_render` 组合时，可将 `render_git_update(update)` 的字符串作为 `body` 传入（终端色在部分客户端可能不保留，HTML 场景请自行转成 HTML）。

## 常见 SMTP（Ubuntu）

| 场景 | `smtp_port` | `use_ssl` | `use_starttls` |
| --- | --- | --- | --- |
| STARTTLS（587） | `587` | `false` | `true` |
| SSL（465） | `465` | `true` | `false` |
| 本机 Postfix（25，无 TLS） | `25` | `false` | `false` |

认证、发件人地址与服务商控制台中的配置须一致。
