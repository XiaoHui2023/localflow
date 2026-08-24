# LocalFlow HTTP 接口

## 通用规则

接口前缀为 `/api/v1`，FastAPI 在 `/docs` 和 `/openapi.json` 提供与当前程序同步的接口描述。JSON 时间使用带时区的 RFC 3339 字符串。

任务和批次提交接受 `Idempotency-Key`。相同身份、路径与键在保存期内返回首次响应。任务列表使用不透明游标；调用方原样传回 `next_cursor`，不要解析其中内容。

## 身份与浏览器写保护

- `summary`：名称、标签、状态和时间的去敏摘要。
- `readonly`：管理员显式启用的完整只读投影，仍不能执行任何操作。
- `admin`：一次性本地码交换得到的短时浏览器会话。
- `signed-client`：使用磁盘 API 密钥签名的程序调用方。

管理员登录响应包含 CSRF 令牌；会话本体仅在 `HttpOnly; SameSite=Strict` cookie 中。网页只在内存保存 CSRF 令牌。所有 cookie 写请求必须同时携带精确同源 `Origin` 和 `X-CSRF-Token`，WebSocket 管理权限也要求同源握手。

## 任务与批次

| 方法 | 路径 | 用途 | 最低身份 |
| --- | --- | --- | --- |
| `POST` | `/tasks` | 创建单个任务 | signed-client 或 admin |
| `POST` | `/batches` | 从模板展开并原子记录批次 | signed-client 或 admin |
| `GET` | `/batches/{batch_id}` | 读取批次与有序任务 ID | 按匿名读取设置 |
| `GET` | `/tasks` | 筛选与游标分页 | 按匿名读取设置 |
| `GET` | `/tasks/{task_id}` | 读取身份对应的详情投影 | 按匿名读取设置 |
| `POST` | `/tasks/{task_id}/acknowledgements` | 确认新完成标记 | admin |
| `POST` | `/tasks/{task_id}/interrupt` | 请求幂等温和中断 | admin |
| `GET` | `/tasks/{task_id}/logs` | 按字节偏移读取日志 | readonly 或 admin |
| `GET` | `/events` | 从事件 ID 之后订阅 SSE | 按匿名读取设置 |
| `WS` | `/tasks/{task_id}/terminal` | 终端输出；管理员可输入和调尺寸 | readonly 或 admin |

创建任务示例：

```json
{
  "name": "smoke-case-a",
  "working_directory": "/srv/project-a",
  "command": ["bash", "run.sh", "--case", "case_a"],
  "labels": ["smoke", "project-a"],
  "mutex_keys": ["license:sim-a"],
  "custom": {"report_path": "/srv/reports/case_a/index.html"}
}
```

成功返回 `202 Accepted`，正文含 `task_id`、`state` 和 `created_at`。

列表参数包括可重复的 `state` 与 `label`、`name`，以及 `created_from/to`、`started_from/to`、`ended_from/to`、`cursor` 和 `limit`。重复标签表示必须全部命中。返回值：

```json
{"items": [], "next_cursor": null}
```

排序键固定为创建时间和任务 ID 倒序。后续页使用上一页游标，因此翻页期间新提交的任务不会插入到旧页面窗口中。

## 模板、变量与配置

| 方法 | 路径 | 用途 | 最低身份 |
| --- | --- | --- | --- |
| `GET` | `/templates` | 模板参数模式和管理员诊断 | readonly 或 admin |
| `POST` | `/templates/{name}/discover` | 调用插件发现 case | admin |
| `POST` | `/templates/{name}/runs` | 展开并提交模板（兼容入口） | admin |
| `POST` | `/variables/resolve` | 四层变量解析预览 | admin |
| `GET` | `/config/files` | 配置文件清单 | admin |
| `GET` | `/config/files/{path}` | 内容和版本 | admin |
| `PUT` | `/config/files/{path}` | `If-Match` 条件保存 | admin |

配置保存先验证语法；`server.yaml` 还会完整执行设置模型语义验证。随后同目录写临时文件、`fsync` 并原子替换。版本不符返回 `412`，无效配置返回 `422`。

## 登录、签名与系统

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/auth/challenges` | 获取 30 秒、一次性、绑定密钥代次的随机数 |
| `POST` | `/auth/local-sessions` | 用一次性本地码换浏览器会话和 CSRF 令牌 |
| `GET` | `/auth/session` | 页面刷新后用有效 cookie 恢复内存 CSRF 令牌 |
| `GET` | `/system/status` | 身份、执行后端和时钟状态 |
| `POST` | `/system/time-adjustments` | 管理员请求手工校时 |

程序签名的规范串逐行覆盖：方法、含查询的路径、正文 SHA-256、密钥代次、Unix 秒和随机数。对应请求头为 `X-LocalFlow-Signature`、`X-LocalFlow-Generation`、`X-LocalFlow-Created` 和 `X-LocalFlow-Nonce`。

任务进入终态后，磁盘密钥原子轮换到下一代。轮换前已经签发的随机数可在自身 30 秒有效期内继续使用旧代密钥；新随机数只能使用新代密钥，且任何随机数都只能消费一次。

## 实时通道

SSE 使用 `after` 查询参数从指定事件 ID 后续传，并在空闲时发送 keepalive。摘要访问者的事件数据同样经过字段投影。

终端 WebSocket 输出消息为 `output`，包含 Base64 数据和下一字节偏移；输入与尺寸消息为 `input`、`resize`，拒绝结果为 `error`。单次块上限 64 KiB，发送端等待 WebSocket 背压，输入也执行大小、Base64 和尺寸范围校验。断线后的完整回放使用日志接口的字节偏移完成。
