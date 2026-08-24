# LocalFlow 插件开发

插件是运行根目录 `plugins/*.py` 中的受信任 Python 代码。它声明网页字段、可选的候选项发现方法，以及把输入展开为一个或多个 `TaskCreate` 的方法；任务状态和进程生命周期仍只由核心服务管理。

## 最小注册示例

```python
from localflow.models import TaskCreate
from localflow.plugins import plugin


@plugin("example", version="1")
class Example:
    fields = [
        {"name": "name", "type": "string", "required": True, "label": "名称"},
        {"name": "command", "type": "string-list", "required": True, "label": "命令"},
    ]

    def expand(self, values, context):
        return [
            TaskCreate(
                name=values["name"],
                working_directory=context["root"],
                command=values["command"],
            )
        ]
```

装饰器只能在 LocalFlow 装载该文件时调用。`expand` 必须返回 `TaskCreate` 列表，不能自行启动进程或写任务数据库。返回后核心会把插件名称、版本、文件 SHA-256、装载代次和输入保存进每个任务快照。

## 字段与候选项发现

当前网页原生处理文本、整数、逗号列表、JSON、路径、seed、`case-picker` 和 `template-picker`。字段仍应在插件中自行做业务校验；最终任务还会经过 Pydantic `TaskCreate` 校验。

插件可提供同步 `discover(values) -> list[str]`。核心把它放入工作线程并设置 5 秒上限，非字符串列表、异常和超时都会变成该插件的诊断，不会终止服务。当前发现结果一次性返回，适合本机中等规模目录；尚未实现发现结果的服务端分页。

## 随安装提供的插件

- `verification.py`：扫描 case 目录，支持搜索、多选、全选当前结果、逐 case 次数、自动或手工 seed，以及用户填写的串行互斥键。每个 case 的每次运行形成独立任务。
- `declarative.py`：扫描 `config/templates` 中的 YAML/TOML/JSON，把名称、目录、命令、标签、互斥键和自定义字段解析成普通任务。

声明式模板示例：

```yaml
name: "${task_name}"
working_directory: "${runtime_root}"
command: [bash, -lc, "./run.sh --seed ${seed}"]
labels: [verification, "${project}"]
mutex_keys: ["license:${simulator}"]
custom:
  report_path: "${report_root}/${seed}/index.html"
variables:
  task_name: nightly
  project: chip-a
```

`config/variables.yaml` 提供全局和项目变量，模板中的 `variables` 是模板层，网页 JSON 是本次运行层。优先级依次为本次运行、模板、项目、全局；未知引用、循环和结构值误嵌入文本都会拒绝。解析后的值和来源写入任务自定义快照。

## 装载代次与错误边界

文件监视器发现插件变化后重新扫描全部插件，并使用包含代次和摘要的新模块名装载。单个文件导入错误写入诊断；只要新扫描产生了可用插件，它们构成新代次。正在运行和历史任务不重新展开，因此不受插件修改影响。

插件没有操作系统级沙箱，能以 `localflow` 服务用户权限读写文件。只安装受信任代码，并依赖服务用户、根目录权限和 systemd 单元限制缩小影响范围。
