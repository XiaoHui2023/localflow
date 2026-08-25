# Round 6：配置、插件、状态与终端研究

## 目标

把配置编辑与使用合一；配置明确所属插件；资源树支持移动、重命名和删除；插件拥有使用说明与显示状态；任务详情原位展开；校时修改即提交；终端保持成熟、可访问且可控。

## 候选与结论

| 能力 | 候选 | 优点 | 缺点/边界 | 决定 |
| --- | --- | --- | --- | --- |
| 资源树 | React Arborist | MIT；树、拖放、行内重命名、虚拟化、键盘、ARIA；外观完全可控 | 增加 react-dnd 依赖；需自己实现服务端文件语义 | 采用 |
| 资源树 | React Spectrum TreeView | 官方可访问拖放覆盖鼠标、触摸、键盘、读屏 | Spectrum 2 视觉与构建体系超出本项目需要 | 原则参考 |
| 资源树 | Syncfusion File Manager | 文件操作完整 | 生产和 CI 需要许可证密钥 | 拒绝 |
| 资源树 | MUI RichTreeView | 标签编辑成熟 | 拖放重排属于 Pro | 拒绝 |
| 终端 | xterm.js + 官方 addons | 当前已运行；Fit/Search/WebLinks 组合清晰 | WebSocket 流控和鉴权仍由应用负责 | 保留并加强 |
| 状态 | 核心任意字符串 | 表面最自由 | 调度无法可靠判断占槽、恢复和终止 | 拒绝 |
| 状态 | 核心生命周期 + 插件显示状态快照 | 兼顾稳定调度与领域状态；历史可复现 | 需要两层状态合同 | 采用 |

## 采用原则

- VS Code：树用于呈现数据，不把每个条目做成单动作按钮；项目动作不超过三项，更多动作进入上下文菜单。
- React Spectrum：拖放必须有键盘和读屏等价路径；本项目以行内重命名和菜单“移动到…”作为拖放替代路径。
- Airflow/Kestra：调度生命周期和领域结果不是同一维度；终态可以有 warning、skipped、killed 等多种语义。
- xterm.js：只采用官方仓库 addons；ResizeObserver 有界触发 Fit，链接需要修饰键；终端 WebSocket 保持独立鉴权和消息协议。
- 即时设置：完整有效的 datetime 值变化后防抖提交，界面显示“正在设置/已设置/失败”，不保留第二个“应用”动作。

## Find Skills

检索了 `react file explorer tree rename move delete accessibility`、`operator console plugin management ui`、`xterm terminal react websocket accessibility`、`plugin extensible task status state machine`。发现 Syncfusion File Manager 与若干 xterm skill，但未安装：前者有许可证密钥约束，后者安装量低且不优于 xterm 官方文档；现有用户根网页设计 skill 更符合离线和质量门要求。

## 反例

- 树行同时常驻“打开、运行、重命名、移动、删除”五个按钮，视觉噪声大且窄屏失效。
- 文件已经选择插件，运行页仍先让用户选择一次插件。
- UI 直接把任意插件状态当调度状态，导致未知状态永久占用并发槽。
- datetime 输入后再要求点击“应用”，增加一次没有额外确认价值的动作。
- 只在 window resize 时调用 FitAddon，任务详情展开或侧栏变化时终端尺寸不同步。

## 自主学习失败披露

- 学习目标：检查 React Aria/Tailwind 的 Tree Storybook 交互样例。
- 失败环节与错误：Storybook 动态模块请求失败，浏览器报 `Failed to fetch dynamically imported module: Tree.stories-C8f3EZ5Z.js`；有界重试后仍失败。
- 实际影响：无法把该单个 Storybook 动画样例作为视觉证据，不影响 React Spectrum TreeView 的官方可访问性合同。
- 替代方案：采用可读取的 React Spectrum TreeView 文档、VS Code Views 指南和 React Arborist 源码/README，并用 Edge 对本项目树完成键盘、重命名、删除和拖放组件验收。
- 恢复条件：目标 Storybook 恢复静态模块服务后，可追加触摸拖放的对照录像；当前交付不依赖该服务。
