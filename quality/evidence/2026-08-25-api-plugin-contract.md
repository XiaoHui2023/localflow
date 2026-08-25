# 配置式 API 与插件合同复验

## 用户可见合同

- `POST /api/v1/runs` 在写入任务前执行与配置页相同的公共字段、插件存在性和插件字段诊断。
- 一个请求内的配置由顶层 `plugin` 决定展开方式，成功时原子建立一个批次和一个或多个有序任务 ID；幂等重试不重复创建。
- 配置文件 API 覆盖创建、读取、保存、移动/重命名、删除、诊断、发现和运行。
- 每个已加载插件的描述都带 endpoint、配置 schema、运行字段和可直接展开成功的请求示例。需要 Case 等输入的插件使用 `api_inputs` 提供示例输入。
- `configuration_schema` 是公共字段与插件字段合成的完整对象 schema，另保留 `plugin_fields_schema`；插件字段与公共字段重名时隔离插件。Case 组件的逐项次数和默认次数键由 `count_field`/`default_count_field` 声明。
- HMAC signed-client 可使用完整任务查询、日志、HTTP 终端控制、变量、插件合同与配置生命周期接口；每一步使用新 challenge，并从密钥文件重新读取当前代密钥。浏览器 WebSocket、校时和受保护 OpenAPI 不由程序密钥越权。

## 失败样本与修复

独立差集审计发现，旧的验证仿真插件虽然暴露了 API 字段，但生成的示例固定使用空 `inputs`，照抄会被“至少选择一个 Case”拒绝；API 文档表也漏列配置创建、移动、删除、发现和插件合同接口。旧的 `/runs` 还直接进入展开，没有显式执行配置诊断。

修复后，验证插件示例选择实际 starter 中的 `case-a`；所有内置插件示例逐个经过 `expand_config()` 并必须产生至少一个带正确插件快照的任务。另播种错误类型 `working_directory: 42`，HTTP 必须返回 422 且诊断定位该字段。

第二轮差集发现配置接口虽存在，却仅接受浏览器管理员 cookie；HMAC 客户端无法读取配置、插件合同、完整任务详情或日志，也不能通过 HTTP 控制任务。权限依赖现统一允许 `signed-client` 使用程序接口，并保持匿名拒绝、浏览器 CSRF、WebSocket Origin、校时与 OpenAPI 管理员边界不变。回归从匿名 403 开始，随后逐请求重新 challenge/读取密钥/签名，完成插件读取、配置创建—读取—条件保存—重命名、配置式幂等批次、完整任务详情、带查询筛选、日志、终端控制授权、温和中断和删除；故意签错查询字符串返回 403 而非匿名降级。中断导致密钥轮换后，删除请求用重新读取的新密钥成功，直接证明调用方没有缓存旧密钥。

## 本轮回执

```text
pytest tests_v2/test_tasks.py tests_v2/test_plugins.py -q
11 passed

pytest tests_v2/test_config.py -q
10 passed

pytest tests_v2 -q
首次全量 55 项通过；补充配置 API 链路后为 56 项；补充 signed-client 全链路后为 57 项；插件 schema、冲突与输入边界补充后为 58 项；发布目录、starter 文档和单一操作台合同补充后为 60 项

ruff check src/localflow tests_v2
All checks passed
```

这些测试证明应用层 API、插件合同、诊断和持久化行为；不单独证明 Ubuntu 的 systemd/PTY 生命周期，后者由目标环境回执独立覆盖。

新增交叉指标后，旧的质量变异“删除列表最后一个指标”不再必然造成需求缺失，门禁正确暴露为失败。Oracle 已改为按稳定 ID 删除唯一覆盖资源预算的 `QM-016`，并直接断言缺失 `RQ-115`；这证明质量门不依赖指标排列或“最后一项恰好唯一”这一偶然条件。

通用 Case 元数据加入后的第一次 Edge 复验失败：管理员 cookie 已建立，但配置和插件 GET 被误用“管理员写操作”校验而返回 403，资源树为空。修复后读取使用管理员会话/回环读取语义，写入仍要求 Origin+CSRF；第二轮 Edge 2/2 通过。随后质检根目录增加字段名完全不同的 `generic-picker` 插件（`jobs`、`job_repeats`、`default_repeats`），网页点击同一 Job 两次后配置运行接口实际返回 `count: 2`，证明 React 消费插件映射而非碰巧依赖验证插件的字段名。

输入白名单加入后的首轮 Edge 复验又发现一个真实回归：配置页面把整份已解析 YAML 当作运行输入发送，发现接口按设计以 422 拒绝 `command`、`working_directory`、`labels` 等未声明字段，Case 列表因此为空。修复没有放宽后端边界；前端统一从插件 `fields`、`count_field` 与 `default_count_field` 投影发现/运行请求，只提交插件公开允许用户填写的值。相同 Edge 流程随后 2/2 通过，且通用异名插件仍实际展开两个任务；HTTP 负例继续证明客户端不能借 `inputs` 覆盖隐藏命令。
