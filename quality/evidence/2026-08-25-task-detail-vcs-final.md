# 任务详情、退出、仿真与三天保留闭环

## 已验证结果

- Python 全量：`64 passed`；Ruff：`All checks passed`；质量追踪：23 个指标覆盖 107 条要求。
- Edge：2/2 旅程通过。展开详情最后一个内容到容器底部不超过 12 px；开始时间不是复制按钮；`variable_sources`、`source` 和内部键不可见；中止响应先返回 `stopping`。
- 资源：零活动用户任务；服务 RSS 61.34 MiB、CPU 0.252% 单核；渲染 JS 堆 18.357 MiB、CPU 0.336%；DOM 2025、监听器 349、空闲请求 7、隐藏 WebSocket 0，全部低于 `quality/resource-budgets.json`。
- 交互实测：`echo hello-localflow` 回显；Ctrl+C 打印控制提示；`status` 打印等待状态；Ctrl+D 以退出码 0 结束。
- 停止实测：接口立即返回 `stopping`；插件等待 Ctrl+C 提示后发送 `quit`；输出包含“保存完成，正常退出”；执行器取得退出码 0 后任务成为 `cancelled`，最终阶段 `stop:1:input`。
- 仿真实测：三任务批次观察到 1 个运行、2 个排队且 2 个均有 blocker；三条命令都包含 case/seed，三条都具有 `tag:verification` 互斥键；结果冻结为 ERROR、编译错误、ERROR，独立 seed=0 样本冻结为 PASS 并只显示存在的运行日志。
- 保存：一个 `task_days` 同时控制任务信息、事件、运行描述和终端输出，默认三天；集成夹具证明年轻任务保留两者、过期任务同时移除、非终态不清理。
- 运行实例：`http://127.0.0.1:29049/` 正在监听，SQLite 活动状态集合为空，服务使用当前构建资源。

## 判定边界

环境探测返回 `VCS_NOT_FOUND`、`os.name=nt`、`platform=Windows`，因此本机无法运行真实 Synopsys VCS 或本轮 Ubuntu systemd/cgroup 目标测试。VCS/UVM 判定改用 Accellera 最终报告格式和 Synopsys 消息形态夹具，退出链路改用真实 Windows 子进程组与端到端任务测试；实际影响是解析器、网页和通用状态机已经验证，但最新 systemd 强制清理改动仍需在持有 VCS 许可证的 Ubuntu 目标服务器重跑 `tests_target/test_localflow_systemd_executor.py` 和真实回归日志。Windows subprocess 只作为开发后端，生产所有权仍由 systemd transient unit、`KillMode=control-group` 和最终 cgroup SIGKILL 提供。

## 反例

- 扫描全文任意 `UVM_ERROR` 会把最终零计数误判为失败；解析器只读取最后 UVM 汇总。
- 在无运行日志时显示配置中的不存在路径会制造假证据；投影只保留实际存在的编译日志。
- 中止请求后直接写 `cancelled` 会释放互斥键并掩盖残留进程；状态机保持 `stopping`，直到退出被确认。
- 元数据与输出使用不同默认期限会制造“详情存在但输出消失”；当前只保留一个三天任务期限。
