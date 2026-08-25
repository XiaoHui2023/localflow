# 网页设计学习来源

检索日期：2026-08-25。

## 已阅读并采用

- GitHub Primer [Navigation](https://primer.style/product/ui-patterns/navigation/)：同页内容面板优先 UnderlinePanels；分段控件更适合改变同一内容的格式或筛选。本项目采用下划线 tabs。
- GitHub Primer [SegmentedControl](https://primer.style/product/components/segmented-control/guidelines/)：2–5 个紧密相关即时选择；窄屏不能换行。本项目拒绝把四个页面做成凸起按钮组。
- Atlassian Design [Tabs](https://atlassian.design/components/tabs)：tabs 用于组织同页相关信息。本项目用它校核页面切换语义。
- MDN [Using the Web Storage API](https://developer.mozilla.org/en-US/docs/Web/API/Web_Storage_API/Using_the_Web_Storage_API)：`localStorage` 跨浏览器会话保存同源偏好。本项目只保存非敏感主题字符串。
- MDN [`color-scheme`](https://developer.mozilla.org/en-US/docs/Web/CSS/Reference/Properties/color-scheme)：同步浏览器原生控件的明暗外观。
- FastAPI [Metadata and Docs URLs](https://fastapi.tiangolo.com/tutorial/metadata/)：可关闭默认 `/docs`、`/redoc` 与 `/openapi.json`，再由受保护路由提供 schema。
- Swagger UI [Installation](https://swagger.io/docs/open-source-tools/swagger-ui/usage/installation/) 与 Redoc CE [Deployment](https://redocly.com/docs/redoc/v3.x/deployment/intro)：两者均可离线打包，但会增加明显前端体积。本项目当前只需要查阅而非在线试调，采用现有 OpenAPI 数据的轻量折叠视图。
- static localhost 安全反例：Jupyter 等本地服务仍使用文件 token；loopback 是暴露面缩减，不是用户身份。该轮原决定拒绝 `127.0.0.1 = admin`，后按明确产品需求在 Round 6 改为回环自动管理员，并在 `docs/security.md` 保留多用户风险告警。

## Skill 发现轨

执行了 `npx skills find` 三组查询。发现 `creating-dashboards`、`dashboard-design`、`ui-ux-design-system`、`agent-docs-api-openapi` 等候选。它们仅处于“搜索到”状态，未安装、未执行：当前已有的 `modern-web-interface-design`、`concise-no-fluff-interface`、`frontend-color-theme` 提供更明确的本项目质量门；第三方 skill 尚未完成源码与许可证审计。

## 纵向导航、自动发现与运行页补充研究

- Microsoft Fluent 2 [React Nav](https://fluent2.microsoft.design/components/web/react/core/nav/usage)：一级导航应简短、易扫描、面向用户目标并保持明确选中态；简单导航只需一级，图标必须配文字。本项目采用窄型左侧 rail、图标+短标签、左侧选中条和上下方向键。
- Fluent 2 [Navigation bar](https://fluent2.microsoft.design/components/ios/core/navigationbar/usage)：页面标题若不能增加上下文可以留空。本项目删除与当前导航完全同义的“任务”“配置”“API”“运行模板”标题。
- GitHub Actions [Workflows](https://docs.github.com/en/actions/concepts/workflows-and-actions/workflows)：仓库根目录的固定 `.github/workflows` 由系统自动检索。本项目适配为固定 `config/tasks`，运行页进入后自动发现。
- Atlassian Design [Components](https://atlassian.design/components/)：使用 token、焦点环、日期时间、表单和导航构件保持一致交互；本项目不引入其运行时，吸收其克制边界、表单分组和状态反馈原则。
- Rundeck [Creating jobs](https://docs.rundeck.com/docs/manual/jobs/creating-jobs.html) 与 Kestra [Task runners](https://kestra.io/docs/task-runners)：证明成熟系统普遍提供任务定义、参数化运行、日志与执行器抽象；本项目拒绝它们的大型层级、导入工作流和集群概念，保留单机文件优先边界。
- 社区交叉证据：r/selfhosted、r/devops、r/sysadmin 对 Rundeck、Kestra、Prefect、Dkron 的讨论反复强调易运行、实时日志、低依赖和避免复杂编排；社区观点只用于发现痛点，不覆盖官方接口事实。

参考截图位于 `references/fluent-nav.png`、`references/atlassian-components.png`、`references/github-workflows.png`，均为 2026-08-25、1440×1000、官方页面首视口。Edge 成功写出三张截图，但自动化进程在关闭阶段未退出且无错误输出，达到等待上限后被终止；文件已逐张读取验证。影响只限采集进程的自动退出，未影响截图内容或项目浏览器门禁。

本轮 Find Skills 查询：`operator console ui navigation settings`、`react form auto discovery configuration ux`、`dashboard information architecture no redundant headings`、`task runner web ui design`。发现 `operational-expert-tool-ui`、`information-architecture`、`s4h-information-redundancy` 等候选，状态均为“仅搜索到”；未安装或执行，原因是第三方说明与脚本尚未完成安全/许可证审计，且现有用户根技能已有更严格的项目闭环。

## 工具状态

- 已实际运行：本地技能、官方网页资料、项目 Edge/Playwright 入口。
- 接入失败：Codex 内置浏览器桥在连接前被 fail-closed Hook 拒绝，具体错误记录于迭代文档；替代入口不扩大权限且覆盖同一应用。
