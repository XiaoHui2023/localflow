# 可直接运行的任务例子

这个目录本身就是一个 LocalFlow 根目录：配置在 `config/tasks/`，脚本在 `scripts/`。

- `random-number.yaml`：运行一次，输出 1–100 的随机数，然后结束。
- `interactive-shutdown.yaml`：持续运行；可在终端发送 Ctrl+C 后输入 `status`、`resume` 或 `quit`，停止按钮会自动完成协议。
- `marker-warning.yaml`：一次性质量检查，退出码映射为插件自定义的“需要关注”。
- `verification-demo.yaml`：扫描 `cases/`，可选择 Case、次数和 seed，逐项进入队列。

在仓库根目录执行：

```bash
localflow init --root examples/task-playground
localflow serve --root examples/task-playground
localflow open --root examples/task-playground
```

进入“配置”页选择文件即可使用。配置会自动出现，不需要扫描。四个插件各有且仅有一份任务 YAML；共享变量通过 configlib 的显式 `!include` 导入。
