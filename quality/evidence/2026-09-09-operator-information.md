# 操作信息、终端列表与仿真队列证据

## 合同

- 运行检查只呈现用户决策所需信息：标签为不可复制词缀，Shell 与执行器包装不进入操作员页面，Case/seed 预览保持模板文本。
- Case 整行（减号除外）可单击增加，零值不占视觉表面；按住越过延迟后才连续变化，释放、移出或取消立即停止。
- 终端列表只用名称与标签识别任务，不放通用装饰图标；活动组在历史组之前，不重复状态或“只读历史”；列表、xterm 与检索均保持有界。
- 任务详情使用原始用户命令与语义化短开始时间；未读完成使用信息强调色而不是错误红色。
- 验证插件只在 Case 与完整标签集合都相同时自动互斥。
- 配置资源树保存折叠目录身份，刷新或切换页面后恢复。

## 设计依据

- WAI-ARIA Button Pattern：完整 Case 行和复制表面保留原生按钮/键盘语义。
- Carbon Code Snippet：单值复制使用完整值表面，不在密集信息行重复堆叠图标。
- VS Code Terminal Appearance：条目以名称、图标和确有必要的状态信息建立层级；本项目的活动/历史分组已经承担生命周期表达，因此删除逐项重复文字。
- TanStack Virtual：只处理可见窗口；LocalFlow 通过最新 200 个任务的有界查询、xterm 5000 行回滚、4 MiB 字节窗和服务端分块检索落实同一原则。
- Carbon Status Indicator：未读/新内容属于信息提示，不复用危险红色；失败语义继续由任务状态承担。

## 自动 Oracle 与故障样本

- `tests_v2/test_config.py`：检查项没有 Shell/命令入口，标签为 `tokens`，模板文本不随本次选择结算。
- `tests_v2/test_tasks.py`：执行快照保留 `-ic`，`display_command` 精确等于用户配置命令。
- `tests_v2/test_plugins.py`：同 Case + 同完整标签集（标签顺序无关）得到相同自动互斥键；不同 Case、不同或部分重合标签均不同。
- `frontend/e2e/localflow.spec.js`：整行 Case 点击、长按停止、零值隐藏、非复制标签、无复制图标、无 Shell、原始命令、语义时间、信息色未读点、终端分组/宽度/无冗余文案、资源树折叠记忆。
- `frontend/e2e/compatibility.spec.js`：当前 Chromium/Firefox 终态回放没有“只读历史”。
- `quality/operator-interaction-contract.json`：静态禁止 `.copy-affordance`、`.terminal-entry-state`、`terminal-readonly` 和运行中名称染色，并要求上述生产模式存在。

## 运行记录

- 2026-09-09：定向 Python 测试 32 passed、1 skipped；前端生产构建通过。
- 2026-09-09：首次 Edge 重跑发现 CSS 颜色格式（hex/rgb）比较错误，改为浏览器规范化颜色后重跑。
- 2026-09-09：第二次 Edge 重跑发现 Case 可访问名称加入当前次数后旧正则过窄，修正为稳定动作前缀后重跑。
- 2026-09-09：`tools/run_browser_quality.py` 通过：Edge 全旅程 2/2、当前 Chromium/Firefox 2/2、固定 Chrome 84 与 Firefox 78；浏览器收据 `result=passed`。
- 资源收据：服务 RSS 62.574 MiB、页面 JS 堆 12.15 MiB、DOM 1718、空闲 WebSocket 0、任务进程 0，均低于项目预算。
- 根部 Skill 校验初次受 Windows 默认 GBK 读取 UTF-8 文件影响而失败；设置 `PYTHONUTF8=1` 后两个根部 Skill 均通过。这不影响产品产物，脚本与文档保持 UTF-8，机器门显式使用 UTF-8 模式。

## 声明边界

本文件证明当前 Windows/Edge、Playwright 当前浏览器与本机固定旧浏览器反馈层。Linux systemd/PTY、旧 glibc、最终冻结程序、远端 tag/附件和下载后 smoke 仍由 Rolling Release 的托管生产者与独立消费者门关闭，不能由本文件替代。
