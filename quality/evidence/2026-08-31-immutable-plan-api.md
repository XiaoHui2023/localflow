# 不可变任务计划与机器 API 合同

## 失败基线

- 自动 seed 曾在任务进入 `starting` 后以秒级墙钟生成；同秒串行、并发启动和时间回拨可能重复，旧测试只检查赋值时机。
- 已保存配置的运行入口逐任务提交，没有批次 ID、原子幂等回执或无副作用预演。
- 插件描述只有配置 Schema 和网页字段；AI 调用方缺少独立的运行输入 JSON Schema。

## 当前合同

- 插件返回 `TaskCreate`，或返回声明宿主自动值的 `TaskDraft`。存储层在同一个 `BEGIN IMMEDIATE` 事务中分配自动值、替换任务字段、写入任务/批次/事件/幂等回执；提交后调度器不修改任务参数。
- `monotonic_unix` 使用持久化命名空间和 `max(Unix 秒, 上次值+1)`。旧版排队记录在存储初始化时迁移，调度器不保留参数改写入口。
- 插件发布分离的 `configuration_schema`、`input_schema`、UI 字段和可运行示例。内联配置与已保存配置都提供无副作用 `/plan` 和原子 `/runs`。

## 直接门禁

- `tests_v2/test_scheduler.py`：同秒多次 seed 递增、重开 Store 且墙钟回拨后仍继续递增，最终命令在入队时已冻结。
- `tests_v2/test_batches.py`：自动字段冲突使整批和序列一起回滚、并发同幂等键只产生一个批次、旧排队记录迁移。
- `tests_v2/test_plugins.py`：配置/输入 Schema 分离，输入模型与运行字段必须完全相等，验证插件只声明宿主 seed。
- `tests_v2/test_tasks.py`：内联与已有配置预演、预演零任务副作用、已有配置原子批次与幂等重试、最终命令不含 `${seed}`。
- `tests_v2/test_security.py`：受保护 OpenAPI 包含单插件、内联预演和配置预演路径。
- `tools/run_browser_quality.py`：Edge 主流程、当前 Chromium/Firefox 及固定 Chrome 84/Firefox 78 全部通过；门禁曾捕获回退插件 Schema 使用不存在字段导致 `/plugins` 500，修复后从干净隔离根完整重跑通过。

## 学习与边界

- 官方依据：SQLite 事务和隔离、OpenAPI 3.1、Terraform 保存计划。Find Skills 检索到后台任务、队列、幂等和插件生命周期候选，但未安装；现有项目技能与官方资料已覆盖本次窄合同，第三方技能不作为运行依赖。
- 当前开发机没有 VCS 许可证；seed 进入 VCS 命令的真实仿真仍由 Ubuntu 发布门验证。本轮门禁证明 LocalFlow 的分配、冻结、排队和 API 合同，不外推为具体仿真器接受任意整数范围。
