# LocalFlow HTTP 接口

## 通用规则

接口前缀为 `/api/v1`。与当前程序同步的接口描述由管理员专用 `/api/v1/openapi` 提供；FastAPI 默认 `/docs`、`/redoc` 和 `/openapi.json` 关闭。JSON 时间使用带时区的 RFC 3339 字符串。

任务和批次提交接受 `Idempotency-Key`。相同身份、路径与键在保存期内返回首次响应。任务列表使用不透明游标；调用方原样传回 `next_cursor`，不要解析其中内容。

## 身份与浏览器写保护

- `summary`：名称、标签、状态和时间的去敏摘要。
- `readonly`：管理员显式启用的完整只读投影，仍不能执行任何操作。
- `admin`：用 `secrets/web-admin-key` 登录后得到的持久浏览器会话。
- `signed-client`：使用磁盘 API 密钥签名的程序调用方。

管理员登录响应包含 CSRF 令牌；会话本体仅在 `HttpOnly; SameSite=Strict` cookie 中。网页只在内存保存 CSRF 令牌。所有 cookie 写请求必须同时携带精确同源 `Origin` 和 `X-CSRF-Token`，WebSocket 管理权限也要求同源握手。

## 任务与批次

| 方法 | 路径 | 用途 | 最低身份 |
| --- | --- | --- | --- |
| `POST` | `/tasks` | 创建单个任务 | signed-client 或 admin |
| `POST` | `/runs` | 携带一份配置，按其中插件展开并原子创建一个或多个任务 | signed-client 或 admin |
| `POST` | `/runs/plan` | 无副作用校验并预演内联配置的任务草稿 | signed-client 或 admin |
| `POST` | `/batches` | 从模板展开并原子记录批次 | signed-client 或 admin |
| `GET` | `/batches/{batch_id}` | 读取批次与有序任务 ID | signed-client、admin 或按匿名设置 |
| `GET` | `/tasks` | 筛选与游标分页；签名客户端获得完整投影 | signed-client、admin 或按匿名设置 |
| `GET` | `/tasks/{task_id}` | 读取身份对应的详情投影 | signed-client、admin 或按匿名设置 |
| `POST` | `/tasks/{task_id}/acknowledgements` | 确认新完成标记 | signed-client 或 admin |
| `POST` | `/tasks/{task_id}/interrupt` | 请求幂等温和中断 | signed-client 或 admin |
| `GET` | `/tasks/{task_id}/logs` | 按字节偏移读取日志 | signed-client、readonly 或 admin |
| `POST` | `/tasks/{task_id}/terminal/input` | 写 UTF-8 或 Base64 终端字节 | signed-client 或 admin |
| `POST` | `/tasks/{task_id}/terminal/controls` | 写 Ctrl+C、Ctrl+D、Enter、Escape 或 Tab | signed-client 或 admin |
| `POST` | `/tasks/{task_id}/terminal/resize` | 调整 PTY 行列 | signed-client 或 admin |
| `GET` | `/tasks/{task_id}/logs/search` | 流式检索完整保留日志 | readonly、signed-client 或 admin |
| `GET` | `/events` | 从事件 ID 之后订阅 SSE | signed-client、admin 或按匿名设置 |
| `WS` | `/tasks/{task_id}/terminal` | 终端输出；管理员可输入和调尺寸 | readonly 或 admin |

`GET /events` 默认从建立连接时的最新事件开始，只推送随后发生的事件，避免新页面重放全部历史。需要补读时显式传 `after=<event_id>`；浏览器断线重连可使用标准 `Last-Event-ID`。显式 `after` 的优先级最高。

创建任务示例：

```json
{
  "name": "smoke-case-a",
  "working_directory": "/srv/project-a",
  "command": "bash run.sh --case case_a",
  "labels": ["smoke", "project-a"],
  "mutex_keys": ["license:sim-a"],
  "custom": {"report_path": "/srv/reports/case_a/index.html"},
  "stop": {"actions": [
    {"type": "signal", "signal": "SIGINT", "output_contains": "请输入 quit", "timeout_seconds": 5},
    {"type": "input", "data": "quit\n", "timeout_seconds": 120,
     "extend_timeout_on_output": true, "max_timeout_seconds": 1800}
  ]}
}
```

成功返回 `202 Accepted`，正文含 `task_id`、可直接跟随的 `task.href`、`state` 和 `created_at`；`Location` 指向任务状态资源，`Retry-After: 1` 给出初始轮询提示。配置式批量运行同样返回兼容的 `task_ids`，并额外返回有序 `tasks[{id,href}]`、`batch.href` 和指向批次资源的 `Location`。这些链接都是站内相对路径，Agent 不需要猜 URL。

任务详情中的 `command` 是不可变执行快照，可能包含 LocalFlow 为交互 Shell 与工作目录生成的 argv；`display_command` 是面向操作员的原始用户命令。网页必须显示 `display_command`，Agent 在复现执行时使用 `command`，不得把二者互相覆盖。完整权限下的任务详情与列表还返回同一次文件元数据快照中的 `log_size` 与 `log_updated_at`；后者是 UTC ISO 8601 日志最后写入时间，日志尚不存在时为 `null`，可用于判断终端多久没有产生新内容。

停止动作的 `timeout_seconds` 默认是固定等待。对会持续输出可信清理进度的程序，可设置 `extend_timeout_on_output: true`；每次新增输出会重置静默窗口，但必须同时给出不小于它的 `max_timeout_seconds` 硬上限。这样慢速正常退出可以继续，静默卡死或无限刷输出仍会被完整 cgroup 强杀。调用 `/interrupt` 返回 `stopping` 只代表请求已进入状态机；继续读取任务，直到执行器确认进程树消失后才会出现终态。

字符串命令自动使用服务账号的 `$SHELL`，缺失时使用 passwd 登录 Shell，并以 `<shell> -ic` 读取 `.bashrc`、`.cshrc`、`.zshrc`、`config.fish` 等该 Shell 的交互启动文件，从而支持函数和别名；公共字段 `"shell": "/bin/bash"` 可显式覆盖自动选择。执行用户命令前核心会恢复请求中冻结的工作目录。参数数组禁止同时提供 `shell`，始终按精确 argv 执行且不读取启动文件。

配置式提交是程序调用的首选入口。请求体与 `config/tasks` 文件使用同一合同：`configuration` 顶层必须有 `plugin`，`inputs` 只包含本次运行要改变的插件字段。插件校验、变量解析、任务展开和网页运行表面共用同一实现；一个 Case 多次运行或多个 Case 会在一次请求中返回多个任务 ID。

```json
{
  "configuration": {
    "plugin": "verification",
    "name": "smoke",
    "case_names": ["case-a", "case-b"],
    "working_directory": ".",
    "command": "python3 scripts/simulate.py --case ${case}"
  },
  "inputs": {
    "cases": ["case-a", "case-b"],
    "case_runs": {"case-a": 2, "case-b": 1},
    "seed": null
  }
}
```

正式提交返回 `batch_id`、`batch.href`、有序 `task_ids`、`tasks[{id,href}]` 和 `count`，响应 `Location` 指向批次状态资源。自动值分配、任务、批次、事件和幂等回执在同一个 SQLite 写事务中提交；同一身份、路径与 `Idempotency-Key` 的并发或重试请求只会创建一个批次。缺少插件、未知插件、配置/输入字段错误、自动值冲突或展开结果不是有效任务时，整个请求失败且不消耗自动值、不写入部分任务。

`POST /runs/plan` 使用相同请求体，返回 `plugin`、`count`、`immutable_after_submit` 和有序 `items`。每项包含名称、目录、规范化命令、标签、互斥键、自定义信息及 `deferred_values`。它不写数据库、不分配 seed；正式提交时核心在入队事务中分配并替换自动值，提交后的任务参数不可修改。

列表参数包括可重复的 `state` 与 `label`、`name`，以及 `created_from/to`、`started_from/to`、`ended_from/to`、`cursor` 和 `limit`。重复标签表示必须全部命中。返回值：

```json
{"items": [], "next_cursor": null}
```

排序键固定为创建时间和任务 ID 倒序。后续页使用上一页游标，因此翻页期间新提交的任务不会插入到旧页面窗口中。

## 模板、变量与配置

| 方法 | 路径 | 用途 | 最低身份 |
| --- | --- | --- | --- |
| `GET` | `/templates` | 模板参数模式和诊断 | signed-client、readonly 或 admin |
| `POST` | `/templates/{name}/discover` | 调用插件发现 case | signed-client 或 admin |
| `POST` | `/templates/{name}/runs` | 展开并提交模板（兼容入口） | signed-client 或 admin |
| `POST` | `/variables/resolve` | 四层变量解析预览 | signed-client 或 admin |
| `GET` | `/plugins` | 全部插件的配置/输入 schema、网页字段与可运行示例 | signed-client 或 admin |
| `GET` | `/plugins/{name}` | 单个插件的完整机器合同 | signed-client 或 admin |
| `GET` | `/config/files` | 配置文件清单 | signed-client 或 admin |
| `GET` | `/config/recent` | 最近成功提交过且仍存在的配置，按时间倒序返回名称、标签、路径与最后使用时间 | signed-client 或 admin |
| `POST` | `/config/files` | 创建配置文件 | signed-client 或 admin |
| `GET` | `/config/files/{path}` | 内容、合并结果、版本和分层诊断 | signed-client 或 admin |
| `PUT` | `/config/files/{path}` | `If-Match` 条件保存 | signed-client 或 admin |
| `POST` | `/config/files/{path}/move` | 按版本移动或重命名配置 | signed-client 或 admin |
| `DELETE` | `/config/files/{path}` | 按 `If-Match` 删除配置 | signed-client 或 admin |
| `POST` | `/config/files/{path}/discover` | 用该配置调用插件发现钩子 | signed-client 或 admin |
| `POST` | `/config/files/{path}/inspection` | 解析目录、命令和插件只读检查项 | signed-client 或 admin |
| `POST` | `/config/files/{path}/diagnosis` | 对尚未保存的内容做语法与导入诊断 | signed-client 或 admin |
| `POST` | `/config/files/{path}/plan` | 无副作用预演该配置将创建的任务 | signed-client 或 admin |
| `POST` | `/config/files/{path}/runs` | 运行诊断通过的配置 | signed-client 或 admin |

资源工作区接口只投影网页资源管理器可见的 `config/` 内容。文件内容使用 `If-Match` 版本条件保存；复制、移动和删除在会破坏现有配置导入时整体回滚。软链接本身是显式授权：读取和保存跟随目标，复制/移动/删除保留并操作链接本体，不把外部目标复制成普通文件或误删目标。

| 方法 | 路径 | 用途 | 最低身份 |
| --- | --- | --- | --- |
| `GET` | `/workspace` | `config/` 内容的目录、文件、软链接和语法诊断清单 | signed-client 或 admin |
| `GET` | `/workspace/files/{path}` | 读取普通配置文件 | signed-client 或 admin |
| `PUT` | `/workspace/files/{path}` | 条件创建或原子保存文件 | signed-client 或 admin |
| `POST` | `/workspace/directories` | 新建目录 | signed-client 或 admin |
| `POST` | `/workspace/moves` | 移动或重命名文件、目录、软链接 | signed-client 或 admin |
| `POST` | `/workspace/copies` | 复制文件、目录或软链接 | signed-client 或 admin |
| `DELETE` | `/workspace/entries/{path}` | 删除文件、目录或软链接 | signed-client 或 admin |

配置读取的 `diagnosis` 只描述 YAML/TOML/JSON 语法和受限导入是否可解析；`run_diagnosis` 才描述插件运行合同。保存不受两类诊断阻断，始终按 `If-Match` 做同目录临时文件、`fsync` 与原子替换；版本不符返回 `412`。外部写入和编辑中的无效文件均可保留原文并在编辑区内联显示错误。`POST /api/v1/config/files/{path}/inspection` 接受与运行相同的 `inputs`，由插件返回只读审查项 `{name,label,value,kind,check,severity,message}`；`kind: tokens` 时 `value` 是字符串数组并由宿主渲染为不可复制词缀，其余类型的 `value` 是字符串；`check` 为 `none` 或 `availability`。它与发现钩子一样有五秒上限，不创建任务。

这些接口覆盖配置的创建、读取、保存、移动、重命名、删除、诊断、发现、检查、预演与运行。AI Agent 的最短可靠链路是：读取 `/plugins/{name}` 的两个 JSON Schema → 列出并读取配置 → 调用 `discover` 取得动态 Case → 用目标 `inputs` 调用 `plan` → 使用新的 `Idempotency-Key` 正式提交。无需保存文件时使用 `/runs`；需要长期复用时调用配置文件的 `/runs`。两条正式路径都原子创建批次并返回相同响应形状。

## 登录、签名与系统

| 方法 | 路径 | 用途 |
| --- | --- | --- |
| `POST` | `/auth/challenges` | 获取 30 秒、一次性、绑定密钥代次的随机数 |
| `POST` | `/auth/local-sessions` | 用网页管理员秘钥建立持久浏览器会话并取得 CSRF 令牌 |
| `GET` | `/auth/session` | 用有效 cookie 恢复 CSRF 令牌并续期会话 |
| `GET` | `/system/status` | 实例 ID、身份、执行后端和时钟状态 |
| `POST` | `/system/time-adjustments` | 管理员请求手工校时 |
| `POST` | `/system/shutdown` | 管理员请求干净退出；响应 202 后停止接收新工作并清理任务 |
| `GET` | `/openapi` | 管理员读取网页 API 文档使用的 OpenAPI schema |

程序签名的规范串逐行覆盖：方法、含查询的路径、正文 SHA-256、密钥代次、Unix 秒和随机数。对应请求头为 `X-LocalFlow-Signature`、`X-LocalFlow-Generation`、`X-LocalFlow-Created` 和 `X-LocalFlow-Nonce`。

任务进入终态后，磁盘密钥原子轮换到下一代。轮换前已经签发的随机数可在自身 30 秒有效期内继续使用旧代密钥；新随机数只能使用新代密钥，且任何随机数都只能消费一次。

### 程序调用步骤

1. 精确序列化请求正文，并在每次请求时重新读取工作区的 `secrets/api-key`。不要缓存密钥，也不要把它写入网页、URL、日志或环境变量。
2. `POST /api/v1/auth/challenges`，取得 30 秒有效的 `nonce` 和 `generation`。
3. 对 `METHOD\nPATH_WITH_QUERY\nBODY_SHA256\nGENERATION\nCREATED\nNONCE` 做 HMAC-SHA256，把十六进制摘要放入签名头。
4. 提交业务请求。`403` 表示签名、方法、含查询路径、正文、时钟、代次或 nonce 无效；带有任一签名头的失败读取请求也会拒绝，不会静默降级为匿名摘要。丢弃本次材料，从重新读取密钥开始完整重试。`422` 是业务输入错误，不应盲目重试。

最小 Python 示例只使用标准库：

```python
import hashlib
import hmac
import json
import time
import urllib.request

base = "http://127.0.0.1:29049/api/v1"  # 以状态目录 runtime/port 的实际端口为准
path = "/runs"
body = json.dumps(
    {
        "configuration": {
            "plugin": "command",
            "name": "example",
            "working_directory": "/srv/project",
            "command": "python3 -u run.py",
        },
        "inputs": {},
    },
    separators=(",", ":"),
    ensure_ascii=False,
).encode()

with open("/path/to/localflow-root/secrets/api-key", "rb") as stream:
    key = stream.read().strip()
challenge_request = urllib.request.Request(
    base + "/auth/challenges", data=b"", method="POST"
)
with urllib.request.urlopen(challenge_request) as response:
    challenge = json.load(response)

created = str(int(time.time()))
canonical = "\n".join(
    [
        "POST",
        "/api/v1" + path,
        hashlib.sha256(body).hexdigest(),
        str(challenge["generation"]),
        created,
        challenge["nonce"],
    ]
)
headers = {
    "Content-Type": "application/json",
    "X-LocalFlow-Nonce": challenge["nonce"],
    "X-LocalFlow-Created": created,
    "X-LocalFlow-Generation": str(challenge["generation"]),
    "X-LocalFlow-Signature": hmac.new(
        key, canonical.encode(), hashlib.sha256
    ).hexdigest(),
}
request = urllib.request.Request(
    base + path, data=body, headers=headers, method="POST"
)
with urllib.request.urlopen(request) as response:
    print(json.load(response))
```

密钥目录与文件在 Ubuntu 上分别必须为 `0700`、`0600`，且归运行 LocalFlow 的用户所有。程序只需读密钥；不要自行改写或轮换。服务器会在任务终态后完成原子替换。共享密钥的调用程序必须与服务用户处于同一授权边界；跨主机调用应另行建立 TLS 和密钥分发边界。

## 实时通道

SSE 使用 `after` 查询参数从指定事件 ID 后续传，并在空闲时发送 keepalive。摘要访问者的事件数据同样经过字段投影。

终端 WebSocket 输出消息为 `output`，包含 Base64 数据和下一字节偏移；浏览器必须在 xterm 完成该块写入后回复 `{type:"ack",offset}`，服务器才读取下一块。可用 `offset` 与可选 `end` 查询参数限定回放字节窗，服务到达当前窗口后发送 `caught_up`。输入与尺寸消息为 `input`、`resize`，拒绝结果为 `error`。单次块上限 64 KiB；这个应用层确认弥补浏览器 WebSocket API 缺少可靠背压的问题。

HTTP 日志响应的 `next_offset` 是下一次读取起点；正文 `data` 为 Base64。输出文件由监督程序以无缓冲二进制追加写入，因此接口不等待任务结束。HTTP 终端接口适合脚本控制，WebSocket/xterm 适合人在环；两者使用同一 PTY，调用方必须避免同时发送相互冲突的输入。

完整日志检索接口接受 `query`、`case_sensitive`、`whole_word` 和 `regex`，返回最多 200 个 `{offset,line,preview}`。实现按固定 1 MiB 块读取并保留小型边界重叠区，不把整份日志载入内存；浏览器点击结果后只装载命中附近至多 4 MiB 的 xterm 窗口。

签名客户端可以使用完整任务查询、日志、HTTP 终端控制、配置、变量和插件合同接口；每个请求都必须重新取 challenge、重新读取密钥并按实际方法、含查询字符串的路径和精确正文重签。浏览器 WebSocket、时间校准和受保护 OpenAPI 仍使用管理员会话，不接受程序密钥替代网页登录。
