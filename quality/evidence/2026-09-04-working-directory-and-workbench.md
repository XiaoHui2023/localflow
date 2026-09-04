# 2026-09-04 工作目录逃逸与配置工作台

## 用户可观察合同

- 任务页开关简化为“配置”，从左侧导航触发后在宽屏左侧展开配置工作台。
- 当前配置文件名旁直接显示“编辑 / 运行”，不经过菜单，也不把操作推到工作台远端。
- 终端缓冲区只接收任务日志字节，连接和只读回放状态留在页面标题层。
- 验证命令可完全不含 Case/seed/run 占位符，但可运行验证配置必须明确给出工作目录。
- 相对工作目录在预演和入队前按运行根解析为同一绝对快照；Make 的依赖读取、`CURDIR` 和文件副作用都必须落在该目录。

## 成熟方案调研与选择

采用 W3C disclosure 的按钮语义，VS Code 主侧栏/Views 的短名称、左侧工作区和 view-title contextual actions，以及 xterm.js 的终端渲染边界。Material persistent drawer/side-sheet 用作宽窄布局对照。保留现有 React、react-arborist、Monaco、Radix Tooltip/Alert Dialog、xterm Fit/Search/WebLinks，不增加运行时依赖。

候选方案中，右侧补充面板与左侧触发器空间方向相反；模态抽屉会遮挡频繁对照的任务；独立配置页增加往返。最终选择左侧持久工作台，1100px 以下在任务前堆叠。浏览器 Oracle 直接测量面板顺序、上下文动作间距、文本、状态保持和三档横向溢出。

官方资料（核验日期 2026-09-04）：

- https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/examples/disclosure-navigation/
- https://code.visualstudio.com/api/ux-guidelines/sidebars
- https://code.visualstudio.com/api/ux-guidelines/views
- https://code.visualstudio.com/docs/editing/userinterface
- https://code.visualstudio.com/docs/configure/custom-layout
- https://m3.material.io/components/navigation-drawer/overview
- https://xtermjs.org/
- https://www.gnu.org/software/make/manual/make.html

社区面同时检索了 Stack Overflow、Reddit、UX StackExchange、Medium 和运维控制台讨论。它们没有给出比上述官方契约更适合 LocalFlow 的新组件，因此没有安装候选 Skill 或依赖。

## 自然复现与根因

冻结提交 `cef4941041b6b3161d59dd2e34b6125fd713186c`，通过正常 `/api/v1/runs/plan`、`/api/v1/runs`、任务详情、日志和文件系统副作用在 hosted Ubuntu + GNU Make 重放。完整收据：

- https://github.com/XiaoHui2023/localflow/actions/runs/33848596095
- 重放提交：`69c8423103183d333e2b9dc82ecb95051e333369`
- 下载的不可变基线 artifact 名：`localflow-cwd-failure-baseline-69c8423`

验证配置省略 `working_directory`、执行 `make -f /tmp/.../external-project/External.mk all` 时，预演和任务快照均为 LocalFlow 根；真实 Make `CURDIR`、相对依赖读取、`mkdir` 和输出都在 LocalFlow 根。显式外部工作目录的对照只读取 `PROJECT` 并只在外部项目产生输出。命令插件相对工作目录则在预演中保留字面 `project`，最终由后端相对控制器环境解析并失败。

根因有三层：验证插件把缺失目录静默默认成 `.`；插件草稿没有在宿主边界统一绝对化；初始化只安装不存在的内置插件，使旧运行根不会自然获得已发布的合同修复。GNU Make `-f` 不改变目录，因此不能把命令文本解析成 cwd。

## 修复与覆盖

- `PluginRegistry` 在插件草稿离开边界时冻结绝对 cwd，保证预演即显示最终值。
- `TaskService` 为直接任务 API 和批次重复执行同一根相对规范化，避免绕过插件入口。
- verification v3 要求显式 `working_directory`，仍覆盖完全不用 Case/seed/run 的任意命令。
- 初始化器只升级内容摘要等于已知正式内置版本的普通插件文件；用户修改和软链接保持不变。
- `tests_v2` 覆盖缺失拒绝、相对预演/快照相等、直接任务入口、任意命令和升级/保留边界。
- `tests_target` 使用真实 systemd + GNU Make 检查 `CURDIR`、依赖读取以及项目正副作用/LocalFlow 根负副作用。
- 冻结 smoke 通过公开运行 API 和相对工作目录再跑同一 Make 契约，且同时对单文件和解压包执行。
- Edge/Chrome/Firefox 门覆盖左侧几何、就近显式操作、状态保留、字节纯净终端、查找和 1440/760/390px。

## 自主学习与工具异常披露

| 学习/测试目标 | 失败环节与可验证错误 | 实际影响 | 替代方案 | 恢复条件 |
| --- | --- | --- | --- | --- |
| 本机真实 GNU Make 复现 | PowerShell 报 `make is not recognized` | Windows 本机不能产生 GNU Make 语义证据 | hosted Ubuntu Actions 真实 Make | 安装 GNU Make 才能增加本机同类证据，但不是 Linux 发布门前提 |
| 本机 Linux 容器复现 | Docker Desktop named pipe `dockerDesktopLinuxEngine` 不存在；WSL 仅列出 `docker-desktop` | 不能在本机启动目标 Linux 容器 | 一次性 worktree/branch + hosted Ubuntu，下载收据后删除临时分支/worktree | Docker Linux backend 可用或存在正常 WSL 发行版 |
| GNU Make 分页官方文档 | 三个 GNU per-node URL 的网页读取均返回 `(400) Timeout fetching` | 无法逐页抓取，不影响语义核对 | 有界重试后使用 GNU Make 完整官方手册 | GNU 文档节点服务恢复 |
| Find Skills 多查询 | 首个三查询批次在 30 秒截止；第三项未返回 | 初次候选列表不完整 | 把 xterm 和 Make 查询拆开后分别成功 | 技能搜索服务在批次时限内响应 |
| Carbon/Primer 组件候选 | 搜索结果没有与本问题直接相关的官方组件页 | 未采用这两个候选作为依据 | 使用 W3C、VS Code、Material、xterm 官方资料及现有用户根专题 | 获得可验证且更贴近该交互的官方页面 |
| 本地文件/文本定位 | 读取不存在的 `styles.css`、`round5.css`、错误的 redundancy reference 路径及 `tests_v2/test_api_contract.py`；一次 PowerShell `rg` 因 `--` 引号报 `Missing expression after unary operator` | 只延迟定位，没有跳过材料 | 枚举真实文件后读取 `index.css`/`round*.css`、正确 subskill reference 与 `test_tasks.py`，并改用单引号搜索 | 无需恢复；路径已纠正 |
| 用户根 Skill 校验 | 首次校验按 Windows GBK 解码，报 `UnicodeDecodeError: 'gbk' codec can't decode byte` | 首次结果无效，不影响 Skill 内容 | 设置 `PYTHONUTF8=1` 后对同一目录重跑并通过 | 工具默认采用 UTF-8，或继续显式启用 UTF-8 |
| 浏览器脚本解释器 | 系统 `python` 启动时报 `ModuleNotFoundError: No module named 'localflow'` | 该次浏览器门未启动 | 固定改用项目 `.venv` 解释器，随后 Edge 与当前 Chromium/Firefox 通过 | 在系统解释器安装项目，或继续使用项目虚拟环境 |
| 本地固定浏览器 | Chrome 84 镜像拉取三次均报 Docker Linux named pipe 不存在 | 本机无法关闭 Chrome 84/Firefox 78 兼容声明，也不生成完整固定浏览器收据 | 保留 Edge/当前 Chromium/Firefox 通过结果；由 hosted Ubuntu 发行门对最终二进制执行两款固定浏览器 | 启动 Docker Desktop Linux backend；本轮最终声明以 hosted 门为准 |
| npm 安全审计 | 首次调用长时间无响应后终止；第二次设置 20 秒超时和 2 次重试，返回 `audit endpoint returned an error` | 本机没有取得最新漏洞数据库结论；锁文件和构建未受影响 | 保留锁文件、构建、静态测试及 hosted 安装门；不声称 npm audit 通过 | npm registry audit endpoint 恢复 |
| 本地门禁并行编排 | 浏览器构建清空 `frontend/dist` 时并发 API 测试报 `Directory ... frontend\\dist\\assets does not exist` | 该次全量 Python 结果无效，不是产品回归 | 等浏览器构建结束后串行重跑，全量通过；规则写入 release quality 专题 | 无需外部恢复，按新顺序执行 |

## 发布收据

本节只接受本轮精确提交的 Rolling Release workflow、tag、Release API、资产 SHA-256、全新下载与解压后 smoke。发布完成前不得从本地测试外推公网制品。
