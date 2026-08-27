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

`localflow` 没有参数和子命令。它把可执行文件所在目录作为完整运行目录；源码安装时使用启动命令时的当前目录。首次运行自动补齐缺失目录、设置和示例，随后启动服务。四个内置插件各有一份任务 YAML：一次性随机数、验证仿真、结果标记和交互退出。交互示例持续运行，可在 Ctrl+C 后输入 `status`、`resume` 或 `quit`。脚本位于 `scripts/`；网页“运行”页自动显示这些任务配置，不需要导入或扫描。

试用环境可在首次启动后，把 `config/server.yaml` 中的执行器改为：

```yaml
execution:
  backend: subprocess
  max_concurrency: 4
```

再次直接启动：

```bash
localflow
```

默认监听所有 IPv4 网卡，端口由系统随机选择；启动后只打印首选局域网 IP 对应的可复制地址，并在运行期间写入 `runtime/port`。来源地址和随机端口都不是身份验证；未登录网页默认只能读取去敏摘要。首次管理操作在设置页输入 `secrets/web-admin-key`，成功后浏览器保持登录，刷新或服务重启无需重输；修改该文件会注销旧会话。程序客户端使用独立的 `secrets/api-key` 逐请求 HMAC 签名。

## Ubuntu 安装要点

GitHub Release 提供 `localflow` 静态单文件、完整目录压缩包和 `SHA256SUMS`。压缩包根目录已包含 `config/tasks`、`scripts`、`plugins` 及运行目录骨架；解压后只需在该目录执行 `./localflow`，首次运行生成本机密钥和缺失设置，不覆盖示例或用户文件。`main` 每次 push 只有在解压目录示例、静态包真实任务冒烟，以及最终 StaticX 二进制在 Ubuntu Google Chrome 与 Firefox 中完成登录、配置、任务、复制和交互终端旅程后才更新滚动 Release；目标 Ubuntu 无需为 LocalFlow 本身安装 Python，示例脚本需要系统 `python3`。

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
