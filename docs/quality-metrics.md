# LocalFlow 质量指标

机器清单位于 `quality/traceability.json`，逐项记录需求、负责人、自动测试、判定依据、故障样本、证据、状态和准确的表述范围。`tools/check_quality.py` 检查 66 条需求无遗漏、指标不重复、状态合法，并要求测试与证据路径真实存在；对应故障测试删除一项指标后必须失败。

## 当前状态

| 指标 | 范围 | 状态 | 主要证据 |
| --- | --- | --- | --- |
| QM-001 | 任务输入、详情、状态、快照 | passed | HTTP 与 SQLite |
| QM-002 | 筛选、稳定游标 | passed | 插页分页与非法游标测试 |
| QM-003 | 工作区、确认、日志续读 | passed | Edge 任务分组、焦点确认、xterm 输出 |
| QM-004 | systemd、恢复、三级中断 | passed | Ubuntu PID 1 / 用户瞬态单元 |
| QM-005 | 互斥队列、批次、seed | passed | 阻塞 ID、时间线、批次关系 |
| QM-006 | 配置、原子写、变量 | passed | 版本冲突、替换故障、循环变量 |
| QM-007 | 插件、发现、声明式模板 | passed | 代次、诊断和任务快照 |
| QM-008 | 网页视觉、键盘、窄屏 | passed | Edge/Playwright、axe、390px 几何与截图 |
| QM-009 | API、OpenAPI、事件、幂等 | passed | 集成测试与生成描述 |
| QM-010 | 会话、CSRF、HMAC、权限 | passed | HTTP/WS 拒绝与 Ubuntu 模式位 |
| QM-011 | 离线校时、单调时长 | passed | 固定 helper、审计、墙钟故障样本 |
| QM-012 | 保留期、SQLite WAL | passed | 精确行和日志目录清单 |
| QM-013 | 发布闭环 | passed | Windows、Edge 与 Ubuntu systemd 分层证据 |

完整命令、环境、目标探针、浏览器截图、故障样本和工具兼容性说明见 `quality/evidence/2026-08-25-final.md`。

## 发布判定

当前核心服务、Ubuntu systemd 执行、权限、生产前端构建与 Edge 浏览器交互均有直接证据。浏览器门禁每轮先构建当前源码，再运行匿名/管理员、任务状态、xterm、模板、Monaco、axe 与 390px 检查；本机浏览器桥接工具仍受管理员 Hook 限制，但独立 Playwright 通道已完成同一验收范围。

任何自主学习或工具接入失败都必须在最终报告和证据文件中写明学习目标、可验证错误、影响、替代方案与恢复条件。
