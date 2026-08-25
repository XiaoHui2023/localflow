# 队列、运行时种子与 Agent Skills 验收

## 结论

- 等待任务同名且完整标签集相同时始终压缩为一行 `×N`；等待总数超过 20 后，相同非空完整标签集折叠，空标签不折叠，多标签任务只属于一个排序后的完整标签组。
- 验证插件的空 seed 在排队时不存在，任务进入 `starting` 后才以 Unix 时间戳原子写入命令和任务详情；任务名只保留 case。显式 seed 仍在创建时冻结。
- 普通任务不显示行首状态点；新完成任务只显示一个红点，并且仅真实指针悬浮任务行后确认。任务详情在 1440、760、390 像素宽度下均无响应式最小高度或尾部空白。
- 根目录 `skills/` 提供项目结构、API、配置、插件开发和 Ubuntu 运维五个独立入口；内容只使用项目相对链接和通用占位符。发布脚本复制整个目录，Release workflow 在解压后逐项断言。
- 本轮保持测试阶段约束：没有推送、创建 tag 或上传 Release。

## 自动门禁

| 门禁 | 结果 |
| --- | --- |
| `python -m pytest -q` | 67/67 通过；仅有 Starlette TestClient 已知弃用警告 |
| 交付范围 Ruff | 通过 |
| `tools/check_quality.py` | 24 项指标、110 条需求，全部结构有效 |
| Microsoft Edge 端到端 | 2/2 通过，35.4 秒；包含真实空 seed 仿真及详情值对照 |
| 五个 `SKILL.md` quick validation | 5/5 `Skill is valid!` |
| `npm audit --omit=dev` | 0 vulnerabilities |
| `actionlint` | 退出码 0，无诊断 |
| skills 隐私扫描 | 用户名、本机盘符、测试端口和演示实例名均为零命中 |

浏览器门禁直接创建并清理等待任务，先在阈值内验证同名 `×2`，再把总数推到 21 验证标签折叠、展开和组内同名压缩。详情几何门禁分别在 1440、760、390 像素测量展开内容的尾部间隙不超过 12 像素，且卡片不存在未归属内容的额外高度。随后用空 seed 实际提交一个验证仿真任务，对照任务 API 中执行时冻结的整数 seed，在网页展开详情直接断言“随机种子”标签及完全相同的值。

后端门禁冻结了 `time.time()`，证明 queued 快照不含 seed，真正启动时才写入预期时间戳、替换命令占位符并保存详情；VCS 结果覆盖编译日志、运行日志、最后 UVM 汇总和无 UVM 的行首 VCS 错误兜底，状态与计算信息均不携带错误数量。

## 防遗漏复盘

本轮用户复核揭示了 `oracle_escape` 与 `lineage_escape`：RQ-128、运行时存储和 React 投影都已存在，但旧 Edge 收据只断言 seed 输入默认留空，没有直接证明仿真任务详情能看到运行时 seed；仓库顶层 `plugins/verification.py` 仍保留创建时随机数和带序号名称的旧实现。旧的“全部完成”声明因此对 seed 网页可见性无效。

修复不是再加提醒，而是把 RQ-128 同时映射到后端 QM-005/QM-007 和网页 QM-008；`tools/check_quality.py` 强制要求 `verification-seed-task-detail` 收据，移除该断言的故障样例必须令质量门失败；顶层插件副本新增独立契约测试。用户根 `concrete-requirement-expression` 新增按需 reference，规定每条跨面要求必须枚举模型、生命周期、API、网页、配置、插件/示例、打包和运行实例，并为每个适用面提供直接 Oracle。

自主学习使用了 NASA 要求验证矩阵、NASA SWE-052 双向追踪和 Playwright 官方测试实践。Skills CLI 分别搜索 `requirements traceability`、`acceptance criteria testing`、`quality gate regression`、`prevent requirement omission`，发现 `requirements-traceability`、`traceability-auditor`、`deliver-acceptance-criteria` 等候选；这些只完成发现，没有安装或采用，因为现有用户根质量与具体要求 skill 已覆盖相同职责，扩充唯一 owner 的路由成本更低。

## 运行实例

重启前通过任务 API 确认活动任务为 0，随后停止旧控制进程并以隐藏窗口重新启动同一实例。`http://127.0.0.1:29049/api/v1/system/status` 返回 `status=ok`、`role=admin`；活动任务仍为 0。页面引用本轮构建的 `index-DBEUDeo3.js` 与 `index-l3d3CR8A.css`，UI revision 为 `18cf14b710e44d50-1c6`。

防遗漏门禁完成后又在当前 29049 实例通过 `verification-demo.yaml` 运行一次空 seed 的 `case-a`：任务成功，运行时 marker 已移除，详情快照存在整数 seed，执行命令包含完全相同的值。该历史任务保留在任务页，供当前页面直接展开检查。

## 自主学习与工具失败披露

学习目标是使用 Codex 内置浏览器对用户当前打开的本地页面做最终只读几何复核。浏览器 Node REPL 在连接前被本机管理员 PreToolUse Hook 拒绝，可验证错误为：`未知写能力未提供可解析的本地目标；管理员 Hook 按 fail-closed 拒绝`。本轮重启复合 PowerShell 命令也被本机执行策略拒绝，但拒绝发生在进程创建前，未改变服务状态；拆分成停止、确认端口释放、隐藏启动和健康检查四个明确步骤后成功。

实际影响是无法自动操作用户当前 Codex 标签页，不影响页面构建、独立 Edge 浏览器验收、HTTP 健康检查或服务重启。替代方案是项目自带的独立 Microsoft Edge/Playwright 门禁，并以 HTTP 返回、资源指纹和活动任务清单复核正在运行的实例。恢复内置浏览器复核需要管理员 Hook 为浏览器工具提供可解析的本地只读目标契约；恢复复合启动命令不需要额外条件，因为当前已采用更易审计的拆分步骤。
