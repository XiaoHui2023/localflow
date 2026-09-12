# LocalFlow

LocalFlow 是面向 Ubuntu 离线服务器的任务调度与执行平台。调用方提交名称、工作目录、命令、标签和互斥键，服务返回任务 ID；网页显示队列、运行中和历史任务，并提供日志终端、任务运行和配置编辑。

当前版本已替换旧 `automation` 运行核心。生产执行器使用 systemd 用户瞬态服务持有任务，网页服务重启不应终止任务；开发环境可选 POSIX 子进程执行器。

## 快速试用

```bash
python3.11 -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
cd frontend
npm ci
npm run build
cd ..
mkdir demo-root
cd demo-root
localflow
```

`localflow` 没有子命令。默认从当前工作区读取 `config.yaml`、`config/`、`plugins/`、`scripts/` 和 `secrets/`，并把数据库、日志、端口、缓存等实例数据写入当前目录的 `.localflow/`。Case 不是 LocalFlow 核心目录：候选项由所属插件根据自己的配置动态生成或发现。首次运行只补齐两个生产插件和各一份配置：`command/hello-world.yaml` 用四个字段执行任意命令，`verification/demo.yaml` 选择 Case、次数与 seed。测试插件只存在于质检流程，不进入发布包。

多个服务器可复用同一工作区，同时选择互不相同的数据目录：

```bash
localflow --workspace /srv/shared/localflow --data /var/lib/localflow/site-a
```

保持 `--data` 不变会恢复该实例历史，改用空目录就是新实例。旧版单根目录需要继续读取原有 `runtime/`、`logs/` 时，可在该目录运行 `localflow --data .`。数据目录必须是实例本地独占目录，不能让多台主机共享同一个 SQLite 数据库。`--config-root` 与 `--state-dir` 仅作为旧脚本的兼容别名保留。

试用环境可在首次启动后，把根目录 `config.yaml` 中的执行器改为：

```yaml
execution:
  backend: subprocess
  # auto uses every CPU available to the LocalFlow service/cgroup.
  max_concurrency: auto
```

再次直接启动：

```bash
localflow
```

默认监听所有 IPv4 网卡，端口由系统随机选择；启动后只打印首选局域网 IP 对应的可复制地址，并在运行期间写入数据目录的 `runtime/port`。来源地址和随机端口都不是身份验证；未登录网页默认只能读取去敏摘要。`secrets/web-admin-key` 只在工作区首次缺失时生成；首次管理操作在设置页输入一次后，同一浏览器在刷新、端口变化或服务重启后保持登录，修改该文件才会注销旧会话。多台同一信任域的服务器可按安全文档配置 HTTPS 父域共享会话。程序客户端使用独立的 `secrets/api-key` 逐请求 HMAC 签名。

## Ubuntu 安装要点

GitHub Release 提供 `localflow` 静态单文件、完整目录压缩包和 `SHA256SUMS`。压缩包根目录包含 `config`、`scripts`、`plugins` 和配置骨架；解压后在该目录执行 `./localflow`，首次运行生成共享密钥、缺失设置和 `.localflow/` 实例状态，不覆盖示例或用户文件。管理员从网页“设置”页确认退出；普通 Ctrl+C、SIGTERM 与终端断开不会误关控制器。`main` 每次 push 只有在解压目录示例、静态包真实任务与网页退出冒烟，以及最终 StaticX 二进制通过当前 Chrome/Firefox 全旅程和固定 Chrome 84/Firefox 78 启动、登录、Monaco 旅程后才更新滚动 Release；目标 Ubuntu 无需为 LocalFlow 本身安装 Python，示例脚本需要系统 `python3`。

```bash
sudo useradd --system --create-home --home-dir /var/lib/localflow localflow
sudo loginctl enable-linger localflow
sudo install -D -m 0644 deploy/localflow.service /etc/systemd/system/localflow.service
sudo install -D -m 0644 deploy/localflow.tmpfiles.conf /usr/lib/tmpfiles.d/localflow.conf
sudo install -D -m 0755 deploy/localflow-set-time.py /usr/libexec/localflow-set-time.py
sudo visudo -cf deploy/localflow.sudoers
sudo install -D -m 0440 deploy/localflow.sudoers /etc/sudoers.d/localflow
sudo systemd-tmpfiles --create /usr/lib/tmpfiles.d/localflow.conf
sudo systemctl daemon-reload
sudo systemctl enable --now localflow
```

把完整发行目录部署到 `/var/lib/localflow`，并保证 `/var/lib/localflow/localflow` 可执行。systemd 用户管理器必须启用 linger；主服务通过用户 D-Bus 建立任务瞬态单元。

生产使用前必须在目标 Ubuntu 主机运行 systemd 验收。没有 systemd 的容器测试不能证明主服务重启接管、PTY 信号与真实权限行为。

## 质量检查

```bash
ruff check src/localflow tests_v2 tests_target tools/check_quality.py tools/run_browser_quality.py tools/run_linux_browser_quality.py
pytest
python tools/check_quality.py
npm --prefix frontend audit
python tools/run_browser_quality.py
# 仅在 Ubuntu 且已有最终 dist/localflow 时运行：
python tools/run_linux_browser_quality.py --binary dist/localflow
```

设计与使用资料：

- [需求规格](docs/requirements.md)
- [系统设计](docs/architecture.md)
- [HTTP 接口](docs/api.md)
- [配置说明](docs/configuration.md)
- [插件开发](docs/plugins.md)
- [安全设计](docs/security.md)
- [Ubuntu 运维](docs/operations.md)
- [停止与残留进程保证](docs/stopping.md)
- [交互终端与 API](docs/terminal.md)
- [质量指标](docs/quality-metrics.md)

验证仿真插件示例位于 `plugins/verification.py`。每个 case 的每次运行展开为独立任务，seed 写入任务快照，互斥键控制串行队列。
