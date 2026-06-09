# git_update

Git 仓库读取与 HEAD 变更监控。提供一次性查询 `get_last_update`，以及轮询型 `GitUpdateAutomation` 事件源。

限定名：`plugins.git_update`。

## 导出

| 符号 | 说明 |
| --- | --- |
| `get_last_update(repo_path)` | 读取 HEAD 最近一次提交的完整信息与 diff |
| `get_head_hash(repo_path)` | 仅读取当前 HEAD 哈希（轮询用） |
| `GitUpdateAutomation` | 输入 `repo_path`，按 `interval` 轮询；HEAD 变更时触发事件 |
| `GitRepoUpdatePayload` | 事件载荷：`previous_hash`、`update`（`GitLastUpdate`） |
| `GitLastUpdate` | 提交元数据、`diff`、逐文件统计 |
| `GitCommitInfo` / `GitFileChange` / `GitDiffStats` | 提交与 diff 细分结构 |

`author_timestamp` / `committer_timestamp` 为 Unix 秒。

监控的是**本地**仓库 HEAD（含 `pull`、本地 `commit` 等导致的移动）；不会自动 `git fetch` 远端。

## 一次性查询

```python
from pathlib import Path

from plugins.git_update import get_last_update

update = get_last_update(Path("/path/to/repo"))
print(update.commit.short_hash, update.commit.subject)
```

## Automation 事件

在 `examples/` 中实例化并注册监听（`plugins` 须在主配置 `sources` 中排在 `examples` 之前）：

```python
from pathlib import Path

from plugins.git_update import GitRepoUpdatePayload, GitUpdateAutomation

git_watch = GitUpdateAutomation(
    name="git_watch",
    repo_path=Path("/path/to/repo"),
    interval=60.0,
)

@git_watch.register
async def on_git_update(payload: GitRepoUpdatePayload) -> None:
    commit = payload.update.commit
    print(payload.previous_hash[:7], "->", commit.short_hash, commit.subject)
    print(payload.update.diff)
```

首次轮询只记录当前 HEAD，不触发事件；之后 HEAD 变化时触发，载荷含变更前后的哈希与 `get_last_update` 的完整结果。

本仓库示例见 [examples/git_watch.py](../../examples/git_watch.py)（默认监视仓库根目录）。
