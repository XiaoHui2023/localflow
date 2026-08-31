# LocalFlow 设计依据

## 进程承载

systemd 瞬态服务支持运行期建立服务单元并设置工作目录、杀死方式和服务属性，适合把长任务所有权从网页进程分离。systemd 的 `--pty` 与 `--pipe` 会让调用端等待，因此交互终端采用任务监督程序持有伪终端，systemd 只持有监督程序及其控制组。

参考资料：

- [systemd-run 手册源文件](https://github.com/systemd/systemd/blob/main/man/systemd-run.xml)
- [systemd.exec 手册源文件](https://github.com/systemd/systemd/blob/main/man/systemd.exec.xml)
- [systemd.kill 手册源文件](https://github.com/systemd/systemd/blob/main/man/systemd.kill.xml)
- [systemd-run PTY 分离限制讨论](https://github.com/systemd/systemd/issues/32725)
- [Python 进程组与会话接口](https://docs.python.org/3/library/os.html#os.setsid)

## 接口与实时更新

FastAPI 提供 OpenAPI、依赖式身份检查、SSE 与 WebSocket 支持。后台任务工具不承担长任务所有权；长任务由执行器承接。xterm.js 提供成熟终端呈现，但需要应用自己处理流量控制、重连和 WebSocket 权限。

参考资料：

- [FastAPI WebSocket](https://fastapi.tiangolo.com/advanced/websockets/)
- [FastAPI 服务器发送事件](https://fastapi.tiangolo.com/tutorial/server-sent-events/)
- [FastAPI 后台任务限制](https://fastapi.tiangolo.com/tutorial/background-tasks/)
- [xterm.js 安全文档](https://xtermjs.org/docs/guides/security/)
- [xterm.js 流量控制](https://xtermjs.org/docs/guides/flowcontrol/)

## 请求认证

HTTP Message Signatures 的组件覆盖、随机数和创建时间模型用于设计程序 HMAC 请求。LocalFlow 使用共享密钥 HMAC，不声称完整实现公钥签名协议。浏览器使用独立、可撤销的签名会话；网页管理员秘钥只在登录请求中短暂出现，不进入浏览器持久存储。

参考资料：

- [RFC 9421 HTTP Message Signatures](https://www.rfc-editor.org/rfc/rfc9421)
- [OWASP WebSocket Security](https://cheatsheetseries.owasp.org/cheatsheets/WebSocket_Security_Cheat_Sheet.html)
- [OWASP Cross-Site Request Forgery Prevention](https://cheatsheetseries.owasp.org/cheatsheets/Cross-Site_Request_Forgery_Prevention_Cheat_Sheet.html)

## 队列、配置与插件

互斥键借鉴独占资源队列做法，但与显示标签分开。配置使用版本条件写入和文件监视，语义类似资源版本与 watch。插件装载借鉴声明式注册表，但保留面向模板的一对一接口，避免通用钩子系统增加理解成本。

参考资料：

- [GitLab resource groups](https://docs.gitlab.com/ci/resource_groups/)
- [Kubernetes 标签](https://kubernetes.io/docs/concepts/overview/working-with-objects/labels/)
- [Kubernetes API 资源版本](https://kubernetes.io/docs/reference/using-api/api-concepts/#resource-versions)
- [watchfiles 文档](https://watchfiles.helpmanual.io/)
- [pluggy 文档](https://pluggy.readthedocs.io/)
- [SQLite WAL](https://www.sqlite.org/wal.html)
- [Python RotatingFileHandler](https://docs.python.org/3/library/logging.handlers.html#rotatingfilehandler)
- [SQLite PRAGMA journal_size_limit 与 max_page_count](https://www.sqlite.org/pragma.html)
- [systemd-journald 空间限制](https://www.freedesktop.org/software/systemd/man/latest/journald.conf.html)

## 前端选择

任务页采用信息密度适中的三段状态视图，详情在所选任务行下原位展开并可再次点击收起。配置以 React Arborist 资源树呈现，Monaco 负责原始文件编辑，“使用”与编辑共享同一文件上下文。终端使用 xterm.js、Fit/Search/WebLinks 官方附加组件，并由 `ResizeObserver` 跟随容器。组件只从本地构建产物加载。

参考资料：

- [Monaco Editor JSON schema options](https://microsoft.github.io/monaco-editor/typedoc/interfaces/languages.json.DiagnosticsOptions.html)
- [Monaco Editor ESM/Vite 集成](https://github.com/microsoft/monaco-editor/blob/main/docs/integrate-esm.md)
- [Playwright Microsoft Edge 通道](https://playwright.dev/docs/browsers)
- [Playwright 可访问性测试](https://playwright.dev/docs/accessibility-testing)
- [Vite 8 发布与 Node.js 要求](https://vite.dev/blog/announcing-vite8)
- [WAI-ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/)

### 资源树、软链接与终端流控（2026-08-28）

- React Arborist 官方把虚拟化、拖放、内联重命名、键盘导航、多选、过滤和 ARIA 作为核心能力，并明确以 VS Code sidebar/Finder/Explorer 为目标。LocalFlow 继续使用受控树，直接实现对象工具栏与标准剪贴板快捷键；大目录只渲染可视行并保留 8 行 overscan。
- VS Code API 文档明确说明文件 watcher 不会自动跟随符号链接，事件会保留所提供的链接路径。LocalFlow 因此不把单一 watcher 当作充分同步证明，而是使用原生事件加每秒一次的有界内容校对；校对基于逻辑路径，保持链接身份。
- Python `pathlib`/`os` 区分解析目标与目录项操作。资源仓库据此分开词法路径和解析路径：编辑链接写目标，rename/unlink 作用于链接目录项，copy 用 `readlink` 重建链接。
- xterm.js 官方流控指南指出 `Terminal.write()` 非阻塞、WebSocket 没有天然背压且缓冲可能耗尽内存。LocalFlow 使用 `write` 完成回调 ACK 与服务端单块窗口，不以更快轮询冒充流控。
- systemd 的 `KillSignal`、`TimeoutStopSec`、`Restart=on-failure` 适合长期控制器。误操作信号与显式停机信号分离；显式停机仍必须由应用层先收敛任务进程树，不能只杀 HTTP 主进程。

参考资料：

- [React Arborist 官方 README](https://github.com/jameskerr/react-arborist/blob/main/README.md)
- [VS Code API 文件监听与符号链接说明](https://code.visualstudio.com/api/references/vscode-api)
- [Python pathlib 文档](https://docs.python.org/3/library/pathlib.html)
- [Linux inotify 手册](https://man7.org/linux/man-pages/man7/inotify.7.html)
- [xterm.js Flow Control](https://xtermjs.org/docs/guides/flowcontrol/)
- [xterm.js Addons](https://xtermjs.org/docs/guides/using-addons/)
- [systemd.service 手册](https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html)

### Case 单列、焦点与性能（2026-08-28）

Case 的点击语义是增加运行次数，框选只建立临时批量作用域，因此不冒充标准 ListBox selection。W3C APG 与 React Aria 的垂直堆叠、focus/hover/selected 分离用于状态设计；React Aria Virtualizer 的可见行复用适合数千项，但会与当前依赖完整行几何的框选冲突。本轮采用原生按钮、单列全宽 flex、单个委托 wheel listener 和局部 CSS containment：不增加依赖，同时把列数、占宽、≤100ms 状态反馈、焦点不改次数与资源预算交给真实浏览器门。

详细检索、候选比较与失败基线见 [Round 15 研究记录](../quality/evidence/web-design-2026-08-25/round-15-case-list-sources.md)，反例见 [用户要求顺序扫描后仍保留多列](ui-counterexamples/multi-column-case-picker-after-rejection.md)。

## VCS 与 UVM 结果判定

Accellera UVM 1.2 用户指南给出的终局格式包含 `--- UVM Report Summary ---`、按严重级别统计以及 `UVM_ERROR : N`、`UVM_FATAL : N`。UVM 参考实现的 report server 负责汇总，`run_test` 在结束阶段调用报告汇总。因此验证插件从最后一份摘要读取计数，不扫描全文中的任意 `UVM_ERROR` 字样；这能排除被后续摘要纠正的早期消息。没有 UVM 摘要时，才按 Synopsys 资料中编译/运行诊断的行首消息形态识别 VCS error/fatal。

参考资料：

- [Accellera UVM 1.2 User’s Guide](https://www.accellera.org/images/downloads/standards/uvm/uvm_users_guide_1.2.pdf)
- [Accellera 官方 UVM 参考实现](https://github.com/accellera-official/uvm-core)
- [Synopsys Advanced Verification Bulletin](https://www.synopsys.com/content/dam/synopsys/company/publications/advanced-verification-bulletin/advanced-verification-bulletin-issue1.pdf)
- [Synopsys VCS 产品页](https://www.synopsys.com/verification/simulation/vcs.html)

当前开发机没有 VCS 许可证和 Linux 仿真环境，因此判定器使用来自正式格式的 PASS、ERROR、FATAL、仅编译、非 UVM VCS 错误和多日志夹具验证；真实 VCS 回归仍属于 Ubuntu 目标机验收范围。

## 不可变任务计划与自动值（2026-08-31）

LocalFlow 比较了三条路线：调度器在 `starting` 修改任务、插件自行分配值、宿主在入队事务中完成计划。前两条分别造成排队快照不完整和插件重复实现并发/重启一致性，因此采用第三条。插件返回普通 `TaskCreate` 或声明宿主自动值的 `TaskDraft`；SQLite 的单写者串行化和 `BEGIN IMMEDIATE` 让自动序列、任务、批次、事件与幂等回执成为一个提交。自动 Unix 值取 `max(now, previous+1)`，避免同秒并发、重启和墙钟回拨重复。

Terraform 的保存计划说明“预演”和“执行已冻结内容”应是不同动作；LocalFlow 因此提供无副作用 `/plan`，但不会把包含路径或潜在敏感信息的计划文件另存到可分享目录。OpenAPI 3.1/JSON Schema 用于把稳定配置和本次输入拆成两个可独立校验的机器合同。第三方技能检索发现了后台任务、队列、幂等和插件生命周期候选，但没有安装：项目已有更窄的本地技能与直接官方依据，引入外部技能不会成为运行时依赖或提高本次实现证据等级。

参考资料：

- [SQLite 事务与 `BEGIN IMMEDIATE`](https://www.sqlite.org/lang_transaction.html)
- [SQLite 隔离与单写者串行化](https://www.sqlite.org/isolation.html)
- [SQLite `RETURNING` 与 ACID 说明](https://www.sqlite.org/lang_returning.html)
- [OpenAPI Specification 3.1.1](https://spec.openapis.org/oas/v3.1.1.html)
- [Terraform 保存执行计划](https://developer.hashicorp.com/terraform/tutorials/cli/plan)

## 任意命令与任务内运行工作区（2026-08-31）

GNU Make 把 `name=value` 作为命令行变量覆盖，`--case` 不是 Make 的通用选项；因此验证插件不能从领域字段猜测目标程序参数语法。LocalFlow 采用显式模板合同：配置必须自己放置 `${case}` 与 `${seed}`，字符串由 Ubuntu shell 执行，列表保持精确 argv，插件只负责逐任务替换和冻结。终端输出在进程启动前记录最终命令与工作目录，使 Make、脚本或原生程序的实际参数可直接核对。

界面比较了独立运行页、永久双栏和可折叠工作区。独立页增加任务与运行之间往返；永久双栏在日常只看任务时浪费空间。最终采用任务为主、运行为按需辅助面板：1440px 并排，阈值以下将运行置于任务上方，初始折叠并保存当前标签页内状态。开关遵循 WAI-ARIA disclosure button 的 `aria-expanded`/`aria-controls`，布局使用 Grid/Flex 与宽度断点降级；不引入仅为分栏存在的新运行时依赖。

参考资料：

- [GNU Make：Overriding Variables](https://www.gnu.org/software/make/manual/html_node/Overriding.html)
- [VS Code：Custom Layout](https://code.visualstudio.com/docs/configure/custom-layout)
- [WAI-ARIA APG：Disclosure Pattern](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/)
- [MDN：CSS Container Queries](https://developer.mozilla.org/en-US/docs/Web/CSS/CSS_containment/Container_queries)

## 管理员网页退出与危险操作确认（2026-09-01）

W3C APG 将需要用户明确响应的高影响确认定义为 `alertdialog`：模态层必须真实阻止底层交互，并具备可关联的标题与后果说明。Radix Alert Dialog 在 React 中提供 Portal、焦点圈定、取消按钮初始焦点、Esc 关闭和触发焦点恢复，覆盖了现有手写弹窗缺失的行为；其约 12 kB 组件规模相对 Monaco、xterm 与资源树可控，且项目已经使用同系列 Tooltip。LocalFlow 因此复用现有设计令牌为 Radix 原语着色，不再自写焦点管理。

退出事务分为两个所有者：HTTP 端点只验证管理员、幂等登记退出并返回 202；响应发送完成后的后台回调才设置 Uvicorn `should_exit`。随后原有 lifespan 负责停止新调度、取消队列、按协议清理运行任务并确认进程树消失。这样既不会在响应前断连制造假失败，也不会新增一套直接杀进程路径。设置入口到完成为“直接按钮 + 必要确认”两次点击，界面税为零。

Find Skills 分别检索了 `accessible alert dialog react`、`destructive confirmation ux` 与 `react accessibility e2e dialog testing`。结果以 Syncfusion、shadcn、移动端 HIG 与通用 E2E 技能为主；当前用户根部的现代网页、交互步数和质量闭环技能更贴合本项目，故未安装外部技能。第一次组合检索的第三条在 30 秒总上限内没有返回，单独重试 10.3 秒后成功，不影响资料覆盖或实现。

参考资料：

- [W3C APG：Alert and Message Dialogs](https://www.w3.org/WAI/ARIA/apg/patterns/alertdialog/)
- [W3C APG：Button focus behavior](https://www.w3.org/WAI/ARIA/apg/patterns/button/)
- [Radix Primitives：Alert Dialog](https://www.radix-ui.com/primitives/docs/components/alert-dialog)
- [Radix Primitives：Accessibility](https://www.radix-ui.com/primitives/docs/overview/accessibility)
- [Atlassian Design System：Modal dialog](https://atlassian.design/components/modal-dialog/examples)
