# 本体资源质量门禁

`quality/resource-budgets.json` 是预算、测量窗口和采样间隔的唯一来源。浏览器测试与收据校验器共同读取它，禁止在测试与验收代码中复制另一套阈值。

## 测量边界

- 服务：全新运行根目录，SQLite 中 `queued`、`starting`、`running`、`stopping` 等非终态任务总数必须为零；RSS 与 CPU 聚合 Python 控制器及其服务子进程。
- 页面：进入含 Monaco 的完整运行工作台并等待稳定，六秒内取 Edge `TaskDuration` 差值、`JSHeapUsedSize`、DOM 节点/文档/事件监听器、fetch/XHR 数和存活 WebSocket。
- 不计用户任务：前置状态不是零则拒绝采样，而不是从总数中猜测扣除。
- 不计浏览器共享外壳：Edge 的浏览器进程可能服务多个页面，不能可靠归因；只报告该页面渲染上下文的直接指标。

## 闭环

`tools/run_browser_quality.py` 先构建最新前端、启动隔离服务并测服务端，再运行 Edge。`frontend/e2e/localflow.spec.js` 断言每项不超过预算并写入带源码哈希的 `browser-receipt.json`。`tools/check_quality.py` 重新读取预算、核对收据契约和数值；`tests_v2/test_quality.py` 将一个已通过的堆指标改到阈值以上，要求校验器必须失败。

当前 Windows/Edge 样本用于开发闭环；相同 Python 服务采样代码可在 Ubuntu 运行。正式 Release 前仍应在目标 Ubuntu 机器复跑，以捕捉内核、systemd 和硬件差异。
