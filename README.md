# localflow

本机任务自动化平台：通过配置文件定义命令、监听器和工作流，并提供网页管理、执行日志与通知能力。浏览器访问 React 页面，同一进程内的 Python 标准库 HTTP 服务提供 `/api` 与静态资源。可打包为 Linux 单文件 `app`，启动后监听 `0.0.0.0`，默认由系统分配空闲端口。

## 命令行

入口：`python src/app_main/__main__.py <配置文件>`（或打包后的 `./app <配置文件>`）

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| `config` | 文件路径（必填） | 主配置，支持 YAML / JSON / TOML |

示例：

```bash
# 首次：复制 config.example.yaml 为 config.yaml
python src/app_main/__main__.py config.yaml
./dist/app /path/to/config.yaml
example.bat
```

仓库根提供 `config.example.yaml`；复制为 `config.yaml` 后修改（`config.yaml` 已 gitignore）。

启动后终端会打印本机与局域网访问地址、IP 白名单（若已配置），以及已加载的插件包、Automation 与动作。

## 主配置

由 [python-library-configlib](https://pypi.org/project/python-library-configlib/) 加载；模型定义见 `src/app_main/app_config.py`。

| 字段 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- |
| `port` | 整数 | `0` | 监听端口；`0` 表示随机空闲端口 |
| `bind_host` | 字符串 | `0.0.0.0` | 监听地址 |
| `sources` | 字符串列表 | 仓库 `plugins/` | 插件根目录，路径相对配置文件所在目录 |
| `whitelist` | 字符串列表 | 空 | 客户端 IP 白名单；**非空时仅列表内 IP 可访问**；留空不限制 |

`sources` 中 `plugins` 须排在 `examples` 之前，以便 `examples` 可 `import plugins.*`。

局域网远程访问时，在 `whitelist` 填入管理机 IP（例如 `192.168.1.100`），浏览器用服务器局域网地址打开，不要用 `0.0.0.0`。

## 插件与示例

| 目录 | 作用 |
| --- | --- |
| `plugins/` | 可复用的 Automation 类、工具函数；导入时不实例化、不绑定监听；每个子目录一份 `README.md` 写用法 |
| `examples/` | 实例化 `plugins` 中的 Automation，注册监听函数与 `action` |

`plugins/` 下每个**子目录**是一个插件包（须有 `__init__.py`）；`plugins/` 自身**不要**放 `__init__.py`。

`examples/` 可平铺 `.py` 文件，每个文件单独加载为模块；也可继续用子目录包，或直接指定某个 `.py` 路径。

配置里 `sources` 列出 `plugins` 与 `examples` 时：前者展开为各插件子目录，后者展开为目录下顶层 `.py` 文件。

### 目录结构

```text
repo/
  plugins/
    a/
      README.md
      __init__.py
      automation.py
    b/
      README.md
      __init__.py
      util.py
  examples/
    git_watch.py
```

### 限定名

| 磁盘路径 | 加载后限定名 |
| --- | --- |
| `plugins/a/` | `plugins.a` |
| `plugins/b/` | `plugins.b` |
| `examples/git_watch.py` | `examples.git_watch` |

终端启动日志会打印实际限定名，例如 `plugins.git_update (包, …/plugins/git_update)`。

### 导入写法

| 所在位置 | 写法 | 说明 |
| --- | --- | --- |
| `examples/*.py` | `from plugins.a import SomeClass` | 从 plugins 子包导入符号 |
| `examples/*.py` | `from plugins import a` | 导入子模块 `plugins.a` |
| `plugins/a/` 包内 | `from .helper import fn` | 引用 `plugins.a.helper` |
| `plugins/a/` 引用同级 `plugins/b/` | `from ..b import fn` | 引用 `plugins.b` |
| `plugins/a/` | `from .b import fn` | 不可用；表示 `plugins.a.b`（a 的子包），不是兄弟目录 `plugins/b/` |

`examples` 引用 `plugins` 时，配置中 `plugins` 须排在 `examples` 之前，以便 `plugins.*` 已进入 `sys.modules`。

### 代码示例

```python
# examples/git_watch.py
from pathlib import Path

from plugins.git_update import GitRepoUpdatePayload, GitUpdateAutomation

_repo = Path(__file__).resolve().parents[1]

git_watch = GitUpdateAutomation(
    name="git_watch",
    repo_path=_repo,
    interval=30.0,
)

@git_watch.register
async def on_git_update(payload: GitRepoUpdatePayload) -> None:
    commit = payload.update.commit
    print(payload.previous_hash[:7], "->", commit.short_hash, commit.subject)
```

```python
# plugins/a/automation.py
from automation import Automation
from ..b.util import shared_check   # 同级 plugins/b

class SomeAutomation(Automation):
    ...
```

```python
# plugins/b/util.py
async def shared_check() -> bool:
    return True
```

插件用法见各子目录 README，例如 [plugins/git_update/README.md](plugins/git_update/README.md)、[plugins/diff_render/README.md](plugins/diff_render/README.md)、[plugins/mail_send/README.md](plugins/mail_send/README.md)、[plugins/git_mail_notify/README.md](plugins/git_mail_notify/README.md)、[plugins/sim_run/README.md](plugins/sim_run/README.md)。接线示例见 [examples/git_watch.py](examples/git_watch.py)、[examples/git_mail_notify.py](examples/git_mail_notify.py)。

## 开发与发布

| 阶段 | 前端 | 后端 |
| --- | --- | --- |
| 开发 | `cd frontend && npm run dev`（代理 `/api`） | `python src/app_main/__main__.py config.yaml` 或 `debug.bat` |
| 发布 | `npm run build` | `./tools/pack.sh` → `dist/app` |

前端说明见 [frontend/README.md](frontend/README.md)。打包说明见 [PACKAGING.md](PACKAGING.md)。

## HTTP 接口

| 路径 | 方法 | 说明 |
| --- | --- | --- |
| `/api/status` | GET | 服务与任务运行状态 |
| `/api/config` | GET | 当前配置 |
| `/api/run` | POST | 启动任务（JSON 体，占位） |
| `/api/progress` | GET | 任务进度 |
| `/api/result` | GET | 任务结果 |

静态页：`/`、`/assets/...` 来自 `frontend/dist/`。
