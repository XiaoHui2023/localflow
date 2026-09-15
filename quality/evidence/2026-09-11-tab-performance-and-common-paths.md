# 页面切换、列表几何与常用路径证据

## 自然故障与根因

任务页原先由 `page === "tasks"` 条件挂载。离开任务页会销毁资源树、Monaco、运行检查和全部局部状态；从终端返回时这些重型组件重新初始化，因此一次导航会出现空白/迟滞。列表宽度故障来自更具体的组合冲突：通用 `.copy-field` 是 `70px + 1fr` 的两列网格，`code-list` 内没有标签的唯一子元素被自动放入第一列，所以每个编译/运行日志复制面只剩约 70 px，而不是填满值列。

## 方案取舍

- 保留所有页面：返回最快，但会让 xterm、ResizeObserver 和 WebSocket 在隐藏页继续存活，拒绝。
- 每次卸载所有页面：资源释放直接，但重复创建编辑器/树造成可感知停顿，拒绝。
- 稳定挂载耐久任务工作台、离开时只卸载连接型终端页：保留配置上下文和返回速度，同时延续零隐藏终端连接合同，采用。
- 列表使用单一复制面或字符串拼接：破坏数组边界，拒绝。
- `code-list` 的 owner/row/shell/value 全部 `width:100%; min-width:0`，嵌套 row 显式 `display:block`：采用，并以实际 bounding box 验收。
- 常用条目以名称为主、路径为副：重名时仍需二次辨认且两行信息冗余，拒绝。
- 完整 `config/` 相对路径作为唯一可见及 accessible name，收藏/最近分组和 MRU 排序负责其余语义；长路径在条目内换行：采用。

## 门禁

- Edge 从点击“任务”到连续两个 `requestAnimationFrame` 的实测值必须不超过 `quality/resource-budgets.json` 的 250 ms，并写入浏览器收据；同一个 `.config-explorer` DOM 标记必须仍存在，`.terminal-page` 必须已经卸载。
- Chrome/Firefox 兼容旅程在真实 xterm 任务之后证明同一工作台标记保持且终端页卸载。
- 两个编译日志条目各自的 row 与 copy surface 宽度至少为 `code-list` owner 宽度减 1 px。
- 收藏条目的文本和 accessible name 都必须精确等于完整路径，不得包含 `strong/small/em` 元数据，且 `scrollWidth <= clientWidth`、`scrollHeight <= clientHeight`。
- 网页内移动使用明确 source/target 迁移收藏；外部移动没有可靠文件身份时不按重名或内容猜测。工作区刷新会剔除消失路径，浏览器门还在收藏条目已渲染后故意让读取返回 404，证明条目和 localStorage 收藏被清理、没有“打开失败”噪声、当前工作台仍可使用。该竞态是正常失效处理，不得成为未处理 Promise 或页面级错误。
- `tools/check_quality.py` 缺少交互指标或超预算即拒绝收据；静态操作契约拒绝重新出现 `quick-config-labels`、缺失路径 accessible name、缺失任务页稳定挂载或丢失列表单列覆盖。

## 自主学习与来源

- React state preservation: https://react.dev/learn/preserving-and-resetting-state
- web.dev INP optimization: https://web.dev/articles/optimize-inp
- MDN grid automatic track sizing: https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/grid-auto-columns
- GitHub Primer ActionList: https://primer.style/product/components/action-list/

Find Skills 分别搜索了 SPA 选项卡性能和 CSS grid/path navigation，找到了通用 tabs、可观测性、布局类候选，但没有候选同时覆盖固定旧浏览器、终端资源释放、LocalFlow 配置草稿及几何失败注入，因此没有安装新的第三方 Skill 或运行时依赖；使用已有用户根部网页设计 Skill、官方资料和项目真实浏览器门禁完成闭环。
