# 停机日志目录恢复闭环

## 自然失败

默认 `keep_free_mb=512` 时，服务初始化日志处理器后删除 `logs/service`，再写入最终 `LocalFlow stopped`。旧实现先在自定义 `emit()` 中调用 `shutil.disk_usage()`，异常发生在 CPython `RotatingFileHandler.emit()` 的保护边界之外，因此稳定得到 `FileNotFoundError`，并能跳过控制器 `finally` 中后续的端口/PID 文件清理。

## 成熟方案比较

| 方法 | 结果 |
| --- | --- |
| 只在启动时创建目录 | 拒绝；不能处理运行期删除、挂载变化或竞态 |
| 只在停机 API 前创建目录 | 拒绝；复制所有权且其它日志入口仍可失败 |
| 改用 systemd journal 且删除文件日志 | 拒绝；改变既有离线文件日志合同 |
| 日志 handler 自恢复并让失败局限于观测通道 | 采用；错误边界、重试与目录所有权集中 |

CPython 的 `BaseRotatingHandler.emit()` 把 rollover/open 放在 `try/except` 内并调用 `handleError()`；LocalFlow 的容量探测必须处于同等或更窄的边界。systemd/journald 把日志视为服务输出与诊断通道，而不是进程停止完成条件。LocalFlow 因此保留控制台作为独立降级通道，并在下次记录重新探测文件目的地。

## 覆盖集合

- 缺失目录：重新创建、重新打开并保存最终停止记录。
- 路径被普通文件占用：两条记录不抛异常，只出现一次有界告警。
- 磁盘空间探测瞬时 `FileNotFoundError`：第一条降级，第二条自动恢复。
- 原轮转、脱敏、空间保留、任务日志上限测试保持通过。
- 最终 Linux staticx 程序：顽固父子任务运行时删除 `logs/service`，通过网页管理员 API 退出；断言任务 PID 消失、控制器退出、PID 文件消失、服务日志恢复且输出不存在 logging traceback。

## 研究来源

核对日期：2026-09-11。

- CPython `logging.handlers`：https://github.com/python/cpython/blob/main/Lib/logging/handlers.py
- CPython logging cookbook：https://docs.python.org/3/howto/logging-cookbook.html
- systemd service stop semantics：https://www.freedesktop.org/software/systemd/man/latest/systemd.service.html
- systemd journal：https://www.freedesktop.org/software/systemd/man/latest/systemd-journald.service.html

Find Skills 查询 `systemd graceful shutdown process cleanup`、`Python service log directory shutdown`、`FastAPI lifespan shutdown cleanup`。候选多为通用提示或引入新的运维栈；本项目已有更严格的 systemd/cgroup owner 和冻结程序门，因此未安装第三方 Skill。
