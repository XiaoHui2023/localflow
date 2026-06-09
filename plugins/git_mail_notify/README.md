# git_mail_notify

Git 有更新时查询提交、着色 diff 并发送邮件通知。Script 组合 `git_update`、`diff_render`、`mail_send`；轮询接线用 `attach_git_update_watch`。

限定名：`plugins.git_mail_notify`。

## 导出

| 符号 | 说明 |
| --- | --- |
| `GitMailNotifyScript` | 可手动运行或挂接自动化的 Script |
| `git_mail_notify` | 默认实例（SMTP 与收件人须在运行页填写） |
| `attach_git_update_watch(script, repo_path, interval)` | 返回 `GitUpdateAutomation`，HEAD 变更时启动 Script |

## Script 参数（运行页可改）

| 字段 | 说明 |
| --- | --- |
| `repo_path` | 本地 Git 仓库目录 |
| `subject_prefix` | 邮件主题前缀 |
| `smtp_host` / `smtp_port` | SMTP 服务器 |
| `smtp_username` / `smtp_password` | 登录凭据；无认证可留空 |
| `mail_from_addr` / `mail_from_name` | 发件人 |
| `mail_to_addrs` | 收件人，逗号分隔 |
| `mail_cc_addrs` | 抄送，逗号分隔 |
| `smtp_use_ssl` / `smtp_use_starttls` | 与 `mail_send` 相同语义 |

## 接线

主配置 `sources` 中 `plugins` 须在 `examples` 之前。示例见 [examples/git_mail_notify.py](../../examples/git_mail_notify.py)：

```python
from pathlib import Path

from plugins.git_mail_notify import attach_git_update_watch, git_mail_notify

git_mail_notify_watch = attach_git_update_watch(
    git_mail_notify,
    repo_path=Path("/path/to/repo"),
    interval=60.0,
)
```

首次轮询只记录 HEAD，不触发；之后本地 HEAD 变化时自动 `start()` 发信。运行前在 Web「运行」页填好 SMTP 与收件人，或事先用蓝图保存配置。
