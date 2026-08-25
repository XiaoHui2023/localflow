# 停止与残留进程保证

“停止”不是某个固定按键，而是配置或插件知道的退出协议。LocalFlow 保存任务时同时保存该协议，运行中修改配置不会改变已有任务。

## 动作模型

```yaml
stop:
  actions:
    - type: signal
      signal: SIGINT
      output_contains: "请输入 status、resume 或 quit"
      timeout_seconds: 5
    - type: input
      data: "quit\n"
      timeout_seconds: 120
```

- `signal` 先把 `SIGINT` 或 `SIGTERM` 送到 systemd 单元的监督进程，由监督进程转发给前台进程组；最终保底才对整个 control group 使用 `SIGKILL`，避免温和阶段重复向子进程发送同一信号。
- `input` 原样写入任务 PTY，适合 `quit\n`、`save\n` 等协议输入。
- `exec` 在工作目录执行专用停止 CLI。命令时间计入动作上限；超时会杀掉该命令的整个进程组。
- `output_contains` 只观察动作开始后新增的原始字节，避免旧提示误触发；不接受正则表达式。
- `timeout_seconds` 每步独立有界，最长 86400 秒。再次点击停止会跳过当前等待。

动作必须可重复：控制服务可能在发送动作后、记录下一步前重启，恢复时会重发当前动作。推荐停止 CLI、保存和 quit 命令天然幂等。

## 干净终态

第一次停止请求会把任务原子地改为 `stopping`，网页显示“退出中”；此状态仍占用并发位和互斥键。Ubuntu 生产执行器使用 systemd 瞬态服务并设置 `KillMode=control-group`、`SendSIGKILL=yes`。动作耗尽后向完整 cgroup 发送 SIGKILL，并以 2 至 10 秒的低频退避循环重新确认、必要时重发。只有执行器同时确认单元 inactive 且取得退出结果，任务才会成为 `cancelled`；未确认时保持“退出中”并记录重试事件，不伪报结束。

控制服务重启后会恢复 `starting`、`running` 和 `stopping` 三类任务。已经结束的进程按真实退出记录收敛；仍在运行的任务恢复等待器和停止协议。极端的 Linux 不可中断睡眠（D 状态）无法被任何信号立即终止，此时 LocalFlow 会继续显示“退出中”并低频重试，而不会欺骗性地释放队列。

开发用子进程执行器只能近似进程组语义，不能替代 Ubuntu/systemd 验收。`tests_target/test_localflow_systemd_executor.py` 会让主程序创建后台 `sleep`，走“Ctrl+C → 提示 → quit”正常退出，再证明后台 PID 不存在、单元清单为空。

不要对未知程序自动输入 `quit`，它可能成为业务数据或 shell 指令。无法声明协议时使用默认 SIGINT → SIGTERM → cgroup SIGKILL；需要长期保存的程序应由插件声明更长的等待时间。服务停止时清理观察协程但不杀用户任务，下一次启动继续接管，避免网页服务重启中断长任务。
