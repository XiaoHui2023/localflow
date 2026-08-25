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
localflow init --root ./demo-root
```

初始化后的根目录为四个内置插件各放一份任务 YAML：一次性随机数、验证仿真、结果标记和交互退出。交互示例持续运行，可在 Ctrl+C 后输入 `status`、`resume` 或 `quit`。脚本位于 `scripts/`；网页“运行”页自动显示这些任务配置，不需要导入或扫描。

试用环境把 `demo-root/config/server.yaml` 中的执行器改为：

```yaml
execution:
  backend: subprocess
  max_concurrency: 4
```

随后启动：

```bash
localflow serve --root ./demo-root
localflow status --root ./demo-root
localflow open --root ./demo-root
```

默认绑定 `127.0.0.1`，端口为 `0`，实际随机端口写入 `runtime/port`。`localflow open` 从仅服务用户可读的文件取得一次性短码，在 URL fragment 中交给网页并立即换成短时 `HttpOnly` 会话；长期 API 密钥不会进入网页。回环地址和随机端口不是身份验证；匿名访问默认只能读取去敏摘要。浏览器写操作、WebSocket、时间校准和受保护 OpenAPI 需要管理员会话；程序客户端以磁盘密钥逐请求 HMAC 签名后，可以使用配置、插件、任务、日志和 HTTP 终端控制 API。

## Ubuntu 安装要点

GitHub Release 提供 `localflow` 静态单文件、完整目录压缩包和 `SHA256SUMS`。压缩包根目录已包含 `config/tasks`、`scripts`、`plugins` 及运行目录骨架；在解压目录执行 `./localflow init --root .` 只生成本机密钥和缺失设置，不覆盖示例或用户文件。`main` 每次 push 只有在解压目录示例与静态包真实任务冒烟通过后才更新滚动 Release；目标 Ubuntu 无需为 LocalFlow 本身安装 Python，示例脚本需要系统 `python3`。

```bash
sudo useradd --system --create-home --home-dir /var/lib/localflow localflow
sudo loginctl enable-linger localflow
sudo install -D -m 0644 deploy/localflow.service /etc/systemd/system/localflow.service
sudo install -D -m 0644 deploy/localflow.tmpfiles.conf /usr/lib/tmpfiles.d/localflow.conf
sudo install -D -m 0755 deploy/localflow-set-time.py /usr/libexec/localflow-set-time.py
sudo visudo -cf deploy/localflow.sudoers
sudo install -D -m 0440 deploy/localflow.sudoers /etc/sudoers.d/localflow
sudo systemd-tmpfiles --create /usr/lib/tmpfiles.d/localflow.conf
sudo -u localflow XDG_RUNTIME_DIR=/run/user/$(id -u localflow) localflow init --root /var/lib/localflow
sudo systemctl daemon-reload
sudo systemctl enable --now localflow
```

把仓库或发行包部署到 `/opt/localflow`，在其中建立 Python 环境并把 `frontend/dist` 生产产物保留在 `/opt/localflow/frontend/dist`；保证 `/opt/localflow/venv/bin/localflow` 存在。服务单元通过 `LOCALFLOW_WEB_DIST` 明确网页产物位置。systemd 用户管理器必须启用 linger；主服务通过用户 D-Bus 建立任务瞬态单元。

生产使用前必须在目标 Ubuntu 主机运行 systemd 验收。没有 systemd 的容器测试不能证明主服务重启接管、PTY 信号与真实权限行为。

## 质量检查

```bash
ruff check src/localflow tests_v2 tests_target tools/check_quality.py tools/run_browser_quality.py
pytest
python tools/check_quality.py
npm --prefix frontend audit
python tools/run_browser_quality.py
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
