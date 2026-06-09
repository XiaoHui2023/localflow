# diff_render

将 unified diff 或 `GitLastUpdate` 渲染为带固定配色的终端输出（Rich truecolor）。包内不实例化 Automation。

限定名：`plugins.diff_render`。

## 导出

| 符号 | 说明 |
| --- | --- |
| `render_diff(diff)` | 输入 diff 字符串，返回含 ANSI 的渲染文本 |
| `print_diff(diff, file=...)` | 渲染并写入流（默认标准输出） |
| `render_git_update(update)` | 输入 `GitLastUpdate`，输出提交摘要面板 + 着色 diff |

增行绿色、删行红色、hunk 与文件头分别着色；颜色在 `theme.py` 中用 hex 固定，不跟终端 16 色调色板漂移。

## 用法

```python
from plugins.diff_render import print_diff, render_diff, render_git_update
from plugins.git_update import get_last_update

update = get_last_update("/path/to/repo")

# 返回字符串（写日志、拼消息）
text = render_diff(update.diff)
colored = render_git_update(update)

# 直接打印到终端
print_diff(update.diff)
```

`render_git_update` 的参数类型来自 `plugins.git_update.models.GitLastUpdate`，与 git 查询/监控事件载荷共用。
