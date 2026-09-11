# 实例状态隔离研究与决策证据

## 目标与现有失效

旧实现把 `config/`、`plugins/`、`secrets/`、SQLite、任务日志、端口文件和 systemd
任务描述全部绑定到一个 `root`。因此无法表达“多个服务读取一份配置，但分别恢复自己的
任务历史”，冻结程序还会把动态文件写进发行或源码目录。

## 官方基准

- XDG Base Directory 0.8 将配置、持久状态、缓存和短生命周期运行文件按所有权与寿命分开：
  <https://specifications.freedesktop.org/basedir/0.8/>
- systemd 分别提供 `ConfigurationDirectory=`、`StateDirectory=`、`CacheDirectory=`、
  `LogsDirectory=` 和 `RuntimeDirectory=`：
  <https://man7.org/linux/man-pages/man5/systemd.exec.5.html>
- Prometheus 分别公开 `--config.file` 与 `--storage.tsdb.path`：
  <https://prometheus.io/docs/prometheus/latest/command-line/prometheus/>
- Grafana 分离 config、data、logs 和 provisioning，并为多实例共享 provisioning 提供版本语义：
  <https://grafana.com/docs/grafana/latest/setup-grafana/configure-docker/>
  <https://grafana.com/docs/grafana/latest/administration/provisioning/>
- SQLite 官方说明网络文件系统的锁与同步语义可能不可靠；实例数据库不能作为跨主机共享配置的一部分：
  <https://www.sqlite.org/useovernet.html>
  <https://www.sqlite.org/howtocorrupt.html>

## 候选比较

1. 继续使用一个根目录：部署简单，但无法共享配置与隔离历史，拒绝。
2. 暴露 config/state/cache/runtime/log 五个路径：所有权精确，但操作面过重。
3. 配置根 + 实例状态根：配置、插件、脚本、密钥可共享；数据库、日志、缓存、端口和任务描述独占，采用。
4. 共享目录内用实例名字给 SQLite 分表或加前缀：仍共享文件系统锁、日志与清理边界，拒绝。

## 最终合同

- `localflow --config-root PATH --state-dir PATH`；相对路径以启动当前目录解析。
- 配置根默认当前目录；状态根默认当前目录的 `.localflow/`。
- 配置根拥有 `config.yaml`、`config/`、`plugins/`、`scripts/`、`cases/` 与 `secrets/`。
- 状态根拥有 `runtime/`、`logs/`、`cache/`、`exports/`、端口、PID 和格式标记。
- 相对任务目录始终相对配置根；状态目录不得改变命令语义。
- 一个运行中的状态根只能有一个控制器；同主机 systemd 单元名包含状态根摘要。
- 共享配置的网页写仍使用版本条件与原子替换，但这不是跨主机分布式锁，管理员应避免同时编辑同一文件。
- 状态格式损坏或过旧时只隔离动态目录到 `recovery/`；更高版本格式拒绝降级启动。配置和密钥永不参与恢复。
- 旧单根部署可用 `--state-dir .` 读取旧历史；默认布局不擅自移动仍可能被旧监督程序使用的文件。

## 检索异常

`npx skills find` 的四个相关检索在 60 秒内持续无输出，已按有界等待策略中止。影响仅为没有引入新的第三方 Skill；设计改用上述官方资料和本地系统设计、质量、运维 Skill。恢复条件是 skills CLI/注册表可正常响应。

## 验证结果

- Windows 源码门：`179 passed, 5 skipped`；质量追踪 65 项指标、171 项需求有效。
- 浏览器门：Edge 完整流程 9 项、Chromium/Firefox 兼容流程 2 项、固定 Chrome 84 与 Firefox 78 均通过。
- Ubuntu 24.04 systemd 容器：源码测试、用户级瞬态服务、PTY、cgroup、退出清理和密钥权限测试全部通过。
- glibc 2.23 基线完成静态构建；最终二进制通过原生、qemu64、Core 2 Duo、Opteron G1 启动探针。
- 最终二进制和重新解压的发行包均完成真实任务与退出清理 smoke；发行包确认不包含 `runtime/`、`logs/`、`exports/`。
- 并发引导故障注入曾在 Windows 捕获插件文件替换竞态；改为唯一临时文件、原子首次创建和有界重试后，配置与密钥并发用例连续重复通过。
