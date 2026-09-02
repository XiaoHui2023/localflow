# 终态终端历史与成熟查找方案（2026-09-02）

## 方案选择

现有 xterm.js 已加载官方 Fit、Search 与 WebLinks addon，服务端日志接口和 WebSocket 支持从字节偏移 0 进行有背压回放。因此终态历史继续使用同一组件和同一日志事实源，不复制为 DOM 文本、不引入第二套 ANSI 解析器，也不把终态任务重新变为可交互。

成熟产品共同采用浮动查找条、键盘打开、方向查找和匹配条件：

- xterm.js SearchAddon 原生提供 `findNext`、`findPrevious` 和大小写/全词/正则选项。当前版本的全部匹配装饰依赖 xterm proposed API，因此 LocalFlow 不开启实验能力：SearchAddon 负责定位，稳定的公开 buffer API 负责结果计数。
- VS Code 集成终端使用 Ctrl/Cmd+F 和全匹配高亮，其通用查找交互使用 Enter/Shift+Enter、大小写、全词和正则切换。
- Windows Terminal 使用 Ctrl+Shift+F、方向按钮与大小写匹配；LocalFlow 采用更接近现有网页应用的 Ctrl/Cmd+F，同时保留显式按钮供发现和触摸操作。

来源：

- https://github.com/xtermjs/xterm.js/blob/master/addons/addon-search/typings/addon-search.d.ts
- https://xtermjs.org/docs/guides/using-addons/
- https://code.visualstudio.com/docs/terminal/basics
- https://code.visualstudio.com/docs/reference/default-keybindings
- https://learn.microsoft.com/windows/terminal/search

## 安全和生命周期

- 终端页列出活跃任务与保留期内终态任务；queued 尚无进程终端，不进入列表。
- 终态标题明确显示“只读历史”，网页不渲染输入、Ctrl+C、Ctrl+D；核心服务仍按状态拒绝写入和 resize，防止只依赖前端。
- 历史仍通过 64 KiB 分块和 xterm 完成回调 ACK，离页释放 socket、ResizeObserver、动画帧和 xterm。
- 5000 行浏览器回滚上限保持不变；磁盘历史遵循统一任务保留期和容量回收规则。

## 质量门

- Python API 测试证明终态日志仍可读取且终态输入返回 409。
- Edge 完整流程证明终态任务仍在列表、历史内容可见、写控件消失，并验证 Ctrl+F、计数、大小写、前后定位和首尾按钮。
- 当前 Chromium/Firefox 兼容流程复验终态列表、只读标记和历史内容。
- 固定 Chrome 84/Firefox 78、Ubuntu 最终制品和资源证据由完整浏览器/发布门禁复验。

## 本轮结果与边界

- `tests_v2` 全量通过；4 个 POSIX/平台专属用例按既有条件跳过。Ruff 与质量追踪门通过（42 个指标、134 条需求）。
- 2026-09-02 16:29（Asia/Shanghai）重新执行完整 Edge 流程以及当前 Chromium、Firefox 兼容流程，三者均通过；严格 boot/console error 门保持启用。浏览器 receipt 的最终源码哈希、资源预算和截图已刷新。
- 第一轮 Edge 在资源管理器移动/删除测试后观察到一次已删除 `plugins/qa-agent.py` 的迟到读取 404；有上限重试后未复现，最终完整流程通过。没有忽略 404，也没有降低控制台错误门。
- xterm.js 全匹配装饰试验触发可验证错误 `You must set the allowProposedApi option to true to use proposed API`。这说明装饰 API 在当前版本不是稳定合同；实现改为 SearchAddon 定位加公开 buffer API 计数，没有开启 proposed API，后续完整浏览器流程通过。
- Docker 中 Chrome 84 的交互流程曾通过，但清理容器连续两次失败：`could not kill container: tried to kill container, but did not receive an exit event`。随后 `docker desktop restart --timeout 120` 报 `context deadline exceeded`，再次启动也无法恢复；最终状态查询无响应并被有界中止。因此终版源码没有完成固定 Chrome 84、Firefox 78、Ubuntu systemd/cgroup 与 Linux 冻结制品复验，旧固定浏览器证据不得作为终版源码证明。

恢复这些门禁需要 Docker Desktop/WSL 后端恢复健康，或提供可用的 Ubuntu 质量机；恢复后须从最终源码重跑固定浏览器、systemd、cgroup 和冻结制品流程，再决定是否发布。
