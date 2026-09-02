# 交互终端

独立“终端”页是网页中唯一的终端入口。任务展开区只显示命令、工作目录和输出文件路径，不挂载只读或交互终端。

## 网页操作

终端使用 xterm.js 与官方 Fit、Search、WebLinks addon，连接任务 PTY。管理员可以直接键入，也可以发送 Ctrl+C、Ctrl+D 或一行指令。Ctrl+C 只是向程序发送字节 `0x03`，不自动把任务标记为取消；程序进入自己的控制台后，仍可输入 `status`、`resume`、`quit` 等程序支持的命令。

任务进入终态后不会从终端任务列表消失。同一个 xterm 实例从日志偏移 0 只读回放保留期内的终端历史，标题区显示“只读历史”，输入框、Ctrl+C 与 Ctrl+D 全部移除；即使绕过网页，服务端也因任务状态拒绝写入和 resize。任务详情与终端输出共用保留和容量合同，历史日志被空间保护回收后不能宣称仍完整可用。

## 历史浏览与查找方案

不另建文本查看器，继续使用 xterm.js 官方 Search addon，使实时终端和历史终端保持相同 ANSI 渲染、选区、链接与滚动语义。查找条采用 VS Code/Windows Terminal 已验证的模式：Ctrl/Cmd+F 打开，输入时增量高亮全部结果，Enter/Shift+Enter 或上下按钮循环定位，显示当前位置与总匹配数；区分大小写、全词和正则为显式可切换条件，Esc 关闭。独立首尾按钮用于快速返回日志开头或追到末尾。所有控件有可访问名称和按下状态，窄屏时查找条覆盖在终端内部而不扩大页面宽度。

Ubuntu systemd 执行器把 Fit 产生的行列同步给任务 PTY。仅用于开发/测试的管道子进程后端没有可调整的 PTY；它接受合法尺寸作为无操作，使浏览器本地终端仍能正确排版，同时不把“resize rejected”伪错误混入真实任务输出。

输出按不可信终端文本处理；链接只有按住 Ctrl/Command 点击才打开。回滚固定为 5000 行，防止长任务让浏览器内存无界增长。WebSocket 每次最多发送 64 KiB，xterm 完成本块渲染后才回送 ACK，服务收到 ACK 才读取下一块，避免高速输出在浏览器缓冲区无界堆积。离开终端页时先清除全部 socket 回调，再关闭 WebSocket、ResizeObserver、动画帧和 xterm 实例，不在隐藏页面保留连接。

Fit 监听实际终端容器，不监听窗口猜测宽度。1440px、760px 和 390px 浏览器门禁要求页面级横向溢出为零，终端列数随容器变窄而下降。服务端支持 PTY 时同步 rows/cols；开发用普通 subprocess 不具备 PTY 调整能力，但本地显示仍会重排。

未启用 WebGL addon。当前上游版本在反复销毁终端时存在 WebGL 上下文未完全释放的问题；默认渲染器与有界回滚更适合频繁切页的长期控制台。上游修复后，只有通过上下文与内存泄漏门禁才可启用。

## 自动化接口

- `GET /api/v1/tasks/{id}`：任务详情和输出路径。
- `GET /api/v1/tasks/{id}/logs?offset=0&limit=65536`：按字节偏移增量读取，响应返回 Base64 `data` 与下一次 `next_offset`。
- `POST /api/v1/tasks/{id}/terminal/input`：发送 `{"data":"status\n","encoding":"utf8"}`。
- `POST /api/v1/tasks/{id}/terminal/controls`：发送 `{"key":"ctrl_c"}` 或 `ctrl_d`。
- `POST /api/v1/tasks/{id}/terminal/resize`：发送 `{"rows":40,"cols":120}`。
- `WebSocket /api/v1/tasks/{id}/terminal`：复用同一输出和输入通道。

程序 API 使用 HMAC；浏览器写入使用管理员会话、Origin 与 CSRF 校验。匿名或只读身份不能发送输入、控制键或尺寸。

## 中止与清理

任务展开区的停止图标触发任务快照中的有界停止协议，而不是简单杀主 PID。协议可以依次发送信号、PTY 输入或专用停止命令，并等待该动作之后的新输出；重复点击同一图标只推进当前等待阶段。

默认协议为 SIGINT、SIGTERM、SIGKILL。生产执行器以 systemd transient unit 持有完整 cgroup；主程序退出且 cgroup 为空后任务才进入终态。所有柔和动作耗尽仍存活时，核心清理整个 cgroup，避免后台子进程残留。开发执行器只用于 Windows 与普通 Linux 测试，不能替代 Ubuntu systemd 验收。

质检夹具中的交互任务会持续打印，`echo <内容>` 会回显，Ctrl+C 后可输入 `status`、`resume` 或 `quit`，Ctrl+D 关闭标准输入并直接退出；停止图标则按插件协议等待提示、发送 quit、等待保存并最终确认无残留进程。该夹具不进入首启目录或发布包。管道开发后端把单独的 `0x04` 转换为关闭 stdin，Ubuntu PTY 后端保留真实终端 Ctrl+D 语义。
