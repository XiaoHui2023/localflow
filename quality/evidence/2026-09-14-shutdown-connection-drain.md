# 网页退出长连接排空

## 复现与根因

在没有运行任务的真实 Uvicorn 服务上保持 `/api/v1/events` SSE 响应打开，再从另一连接请求管理员退出。旧实现只设置 `server.should_exit`；SSE 生成器只在客户端断开时返回。Uvicorn 会先等待活动连接完成、再进入 lifespan 清理，因此服务停在 `Waiting for connections to close`。刷新网页会关闭旧 EventSource，恰好解除环路；Ctrl+C 又是控制器按既有安全合同保护的信号，不能作为退出修复。

后续真实 Edge 复核发现第二个覆盖逃逸：原浏览器测试拦截退出接口并伪造 202，原 TCP 测试也没有浏览器的 EventSource 自动重连和周期轮询。当前后端在页面保持打开时约 0.15 秒退出，但旧页面在 202 后仍反复请求 `ui-revision`、`status`、`tasks` 与 `events`。这不会让当前后端继续存活，却证明客户端生命周期没有闭合，也解释了为何代理、旧版本或不同连接窗口下仍可能表现为“刷新才退出”。

## 采用方案

202 响应对应的退出事务先设置应用级 `asyncio.Event`，再由响应后的回调设置 Uvicorn 退出标志。SSE 在等待下一轮时同时等待该事件，终端 WebSocket 每个短接收周期检查同一事件并以 1001 关闭。Uvicorn 的 10 秒 graceful-shutdown 超时作为未知 ASGI 连接缺陷的外层保险；它不替代 lifespan 中任务协议、systemd cgroup 清理及残留确认。

网页在收到真实 202 后提升一个 App 级 `shutdownAccepted` 状态：停止全局状态/任务轮询和 UI 版本轮询，并使配置工作台拥有的 EventSource effect 立即清理。页面继续保持打开，不依赖刷新或关闭窗口。

## 机器证据

- `tests_v2/test_shutdown.py::test_web_shutdown_closes_open_event_stream_without_browser_refresh` 启动真实 TCP Uvicorn、登录、保持 SSE 打开、取得 202，并在不关闭客户端流的前提下要求服务线程 5 秒内结束。
- `tests_v2/test_shutdown.py::test_web_shutdown_closes_open_terminal_socket` 保持已建立终端 WebSocket 打开，退出后必须收到标准 1001 关闭而不是无限等待。
- 同文件继续覆盖匿名拒绝、幂等单次回调和无控制器所有者时失败关闭。
- `src/localflow/api.py` 的 SSE 与 WebSocket 共用 `app.state.shutdown_event`；`src/localflow/cli.py` 明确设置有限的 ASGI graceful-shutdown 外层期限。
- `tests_target/test_browser_shutdown.py` 启动独立真实控制器和 Edge，保持文档打开并跨过六秒重连窗口，要求 202 后零请求、进程退出、端口文件和 PID 文件消失。
- `frontend/e2e/shutdown-live.spec.js` 不拦截 API；旧实现在同一 Oracle 下稳定记录多轮重连，修复后为零。

## 研究依据

核对日期：2026-09-14。

- Uvicorn Server Behavior：https://www.uvicorn.org/server-behavior/
- Uvicorn Settings：https://www.uvicorn.org/settings/
- Starlette StreamingResponse：https://www.starlette.io/responses/
- WHATWG Server-sent events：https://html.spec.whatwg.org/dev/server-sent-events.html
- MDN EventSource.close()：https://developer.mozilla.org/en-US/docs/Web/API/EventSource/close

Uvicorn 官方说明确认 graceful shutdown 会等待连接、响应与后台任务完成；因此应用拥有的无限流必须由应用退出事件主动终止，不能把客户端刷新当成生命周期协议。
WHATWG/MDN 同时确认连接丢失后浏览器默认重连，只有客户端 `close()`（或端点返回 204）才终止 EventSource 重连状态。因此仅证明服务端生成器返回不能代表浏览器退出生命周期完整。
