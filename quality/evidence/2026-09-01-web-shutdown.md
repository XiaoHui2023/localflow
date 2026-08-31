# 管理员网页退出收据

## 合同

- 只有带同源 CSRF 的管理员会话可以请求退出；匿名和无控制器所有者场景失败关闭。
- HTTP 202 完整返回后才触发 Uvicorn 退出；同一实例重复请求只触发一次。
- 设置页使用 Radix Alert Dialog：Portal 模态层、取消初始焦点、Esc 取消、触发焦点恢复、底层几何不变、确认期间禁止重复提交。
- 最终 Linux 制品仍由既有 lifespan 清理队列与运行任务，确认完整进程树消失后才退出；发布包不含 `stop-localflow.sh`。

## 当前证据

- `tests_v2/test_shutdown.py`：匿名 403、管理员 202、重复请求单回调、无控制器所有者 503。
- `frontend/e2e/localflow.spec.js`：当前 Edge 完整旅程通过，检查取消初始焦点、Esc 与焦点恢复、设置面板零布局位移、单次确认请求和禁用中的“正在退出”。截图为 `quality/evidence/browser/admin-shutdown-confirmation.png`。
- `frontend/e2e/compatibility.spec.js`：当前 Chromium 与 Firefox 的登录、任务、终端和退出确认取消旅程通过。
- `frontend/e2e/legacy-browser.mjs`：固定 Chrome 84 与 Firefox 78 均能登录、打开退出确认、取消并继续打开 Monaco；无启动或控制台错误。
- `tools/run_frozen_smoke.py` 已改为管理员 `POST /api/v1/system/shutdown`，并继续断言抗 INT/TERM/HUP、202 返回、顽固子进程消失、控制器 PID 与 PID 文件消失。该项由 Ubuntu Release 工作流对最终 StaticX 制品执行，本地 Windows 不冒充最终制品证据。

## 失败、修复与边界

- 首轮 Edge 运行在删除配置后捕获到一次 404 控制台错误。根因是 SSE 删除事件可在删除请求返回前重开当前文件；修复为先中止检查并清空当前文件所有权，再调用删除 API，失败时才恢复。完整 Edge 旅程重跑后通过，未放宽控制台门。
- 第一次本地测试误用未安装项目的系统 Python，`ModuleNotFoundError: No module named 'localflow'`；第一次构建又在仓库根执行 npm，返回缺少根 `package.json`。改用 `.venv\Scripts\python.exe` 与 `npm --prefix frontend` 后分别通过。实际影响仅为首轮验证未成立，产品代码未执行失败路径。
- 固定浏览器均完成并生成证据，但 Docker Desktop 在清理 `localflow-chrome-84-61584` 与 `localflow-firefox-78-61584` 时返回 `tried to kill container, but did not receive an exit event`。这与之前遗留的 `localflow-firefox-78-26984` 相同，说明本机 Docker 守护进程无法回收这些已完成容器。它不改变浏览器旅程结果，但资源清理门在本机为失败；未擅自重启 Docker Desktop，以免影响其它用户容器。恢复条件是用户在合适窗口重启 Docker Desktop 后删除三个精确容器；Ubuntu GitHub Runner 使用新鲜 Docker 守护进程，仍需作为正式发布清理门。浏览器 runner 已升级为清理非零即失败，后续不再静默接受此状态。

## 自主学习

官方资料与技能检索结论见 `docs/research.md`。通用规则已回写用户根部 `modern-web-interface-design/references/local-operator-console.md`；项目规则同步到 `skills/localflow-operations/SKILL.md`。
