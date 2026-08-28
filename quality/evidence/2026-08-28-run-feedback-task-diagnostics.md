# 运行反馈、悬浮层与任务诊断闭环

## 失败基线

- 运行按钮只在请求完成后产生短暂文字，提交期间没有可观察状态，也没有重复提交锁。
- 任务行用 `:has(.fresh-dot)` 改变网格列；固定旧版浏览器合同不应依赖该选择器，状态切换时存在子项与列数不匹配的风险。
- 日志由执行器在校验工作目录之后创建。工作目录、命令或 systemd 启动失败时，API 返回理论路径但文件不存在；`started_at` 也只在进入 RUNNING 后填写，导致启动失败没有开始时间。
- 配置检查说明原先位于 `overflow:hidden` 的检查网格内，局部 `z-index` 无法逃出裁剪。旧测试只检查元素存在，属于 oracle escape。

## 修复与所有权

- 配置运行按钮拥有 `idle → submitting → accepted` 事务状态：submitting 立即禁用，202 后同位勾选反馈，固定通知不参与布局。
- 任务行以显式 `has-fresh` class 选择四列或五列，不使用 `:has()`；浏览器逐项核对可见直接子项从左到右不重叠。
- `TaskService.submit/submit_batch` 在数据库提交后立即建立有界任务日志，写入任务 ID、名称、工作目录和 JSON 参数；调度器取得执行位时固定开始墙钟与单调时钟。subprocess、systemd launcher 和 PTY supervisor 分别记录启动、PID/单元、输出、退出或具体异常。
- 新根默认后端改为 `auto`。用户 systemd 管理器可达时保留 transient-unit 持久性；不可达时服务日志明确告警并回退 subprocess。显式 systemd 仍 fail closed，不隐藏部署错误。
- 检查提示迁移到 Radix Tooltip Portal，命名层级由 CSS token 拥有。共享 `frontend/e2e/ui-quality.js` 检查视口边界、裁剪祖先、五点像素顶层、注入遮挡物、hover/focus/Escape、ARIA、可交互子项和几何稳定性。

## 正反验收

- Python 全量门包含真实 subprocess 成功输出与缺失工作目录故障；故障任务断言非空日志、开始/结束/时长、日志大小与两层启动异常记录。
- Edge 以延迟 300ms 的真实 Hello World 请求证明 pending 状态可见且按钮不可重复点击；随后等待本次 API 返回的任务完成，核对任务行几何、`started_at`、真实 `log_path`、生命周期、`hello world` 输出和实际文件。
- Edge 悬浮层门对验证插件 Case 目录提示执行真实 Portal 与故障遮挡验收；当前 Chrome、Firefox 兼容旅程及固定 Chrome 84、Firefox 78 启动旅程重新通过。
- 旧浏览器回执和当前构建哈希均由质量入口重新生成，未手工放宽旧回执。

## 自主学习

采用 Radix Tooltip 的 Portal/collision 合同、Floating UI 的 flip/shift 定位模型和 MDN stacking-context 模型。三种路线比较后，LocalFlow 选择 Radix 作为 React 交互所有者，并保留项目级像素 Oracle；低层定位需求才使用 Floating UI，自写定位因碰撞、焦点和维护成本被拒绝。

资料访问成功，没有网络、权限、登录、下载或依赖失败。`npm install @radix-ui/react-tooltip` 完成且 audit 报告 0 个已知漏洞。

## Release gate correction

The first pushed revision was correctly rejected by the Release source-quality step because Ruff found two import-order violations. Local pytest and browser gates did not cover that workflow command. The imports were fixed, the full Ruff target list passed, and the project skill now requires mirroring every Release source-quality command before a release commit. This failure did not reach the publish job and did not replace the existing Release assets.

The next clean-Linux reproduction exposed an oracle escape in the pre-existing terminal test: it searched the entire log for the substring `ready`, but the new queue record intentionally contains the complete command, including that source-code literal. The test now waits for an exact `ready` output line before sending Ctrl+C. This distinguishes process output from lifecycle metadata and prevents a premature signal from masquerading as a terminal-control regression.
