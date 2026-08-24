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

HTTP Message Signatures 的组件覆盖、随机数和创建时间模型用于设计程序 HMAC 请求。LocalFlow 使用共享密钥 HMAC，不声称完整实现公钥签名协议。浏览器使用独立短时会话，避免长期密钥进入网页。

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

## 前端选择

任务页采用信息密度适中的三段状态视图，详情抽屉承载命令、目录、自定义字段和终端。Monaco 用于原始配置编辑与模式提示，常用设置仍提供表单。组件只从本地构建产物加载。

参考资料：

- [Monaco Editor JSON schema options](https://microsoft.github.io/monaco-editor/typedoc/interfaces/languages.json.DiagnosticsOptions.html)
- [Monaco Editor ESM/Vite 集成](https://github.com/microsoft/monaco-editor/blob/main/docs/integrate-esm.md)
- [Playwright Microsoft Edge 通道](https://playwright.dev/docs/browsers)
- [Playwright 可访问性测试](https://playwright.dev/docs/accessibility-testing)
- [Vite 8 发布与 Node.js 要求](https://vite.dev/blog/announcing-vite8)
- [WAI-ARIA Authoring Practices](https://www.w3.org/WAI/ARIA/apg/)
