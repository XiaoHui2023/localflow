# LocalFlow 插件开发

插件是运行根目录 `plugins/*.py` 中的受信任 Python 代码。它声明网页字段、候选项发现、显示状态，以及把输入展开为一个或多个 `TaskCreate`/`TaskDraft` 的方法；自动值、稳定排队和进程生命周期仍由核心服务管理。

## 最小注册示例

```python
from localflow.models import TaskCreate
from localflow.plugins import plugin, run_field
from pydantic import BaseModel, ConfigDict


class ExampleConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


@plugin("example", version="1")
class Example:
    config_model = ExampleConfig
    required_common_fields = {"name", "command"}
    title = "示例"
    instructions = "填写名称和命令。"
    example = {"plugin": "example", "name": "示例", "command": "echo ok"}
    run_fields = []

    def expand(self, values, context):
        return [
            TaskCreate(
                name=values["name"],
                working_directory=context["root"],
                command=values["command"],
            )
        ]
```

装饰器只能在 LocalFlow 装载该文件时调用。`expand` 必须返回 `TaskCreate` 列表，不能自行启动进程或写任务数据库。返回后核心会把插件名称、版本、文件 SHA-256、装载代次、输入和显示状态合同保存进每个任务快照。

## API 合同

每个插件同时服务网页和 `POST /api/v1/runs`，不维护第二套 API 参数。请求中的 `configuration` 与 YAML 配置含义相同，`inputs` 对应本次运行输入；核心调用同一个 `expand_config()`。`GET /api/v1/plugins` 和单插件入口返回 `api.configuration_schema`、`api.plugin_fields_schema`、`api.input_schema`、`api.input_fields` 和 `api.example`。`configuration_schema` 校验完整稳定配置；`input_schema` 是可独立校验的本次运行输入；`input_fields` 只决定网页组件。插件提供 `input_model` 时，其字段必须与组件及 Case 次数字段完全一致，未知字段由 Pydantic 拒绝。插件必须维护可运行的 `example` 与 `api_inputs`，并让示例同时通过配置诊断、输入模型和 API 展开测试。

### AI Agent 组合验证配置

AI Agent 应先读取 `GET /api/v1/plugins/verification`，复制 `api.example.configuration` 作为最小骨架，再分别按 `configuration_schema` 和 `input_schema` 生成两部分；不要猜字段名或另造一套模板。长期不变的 `command`、`case_directory`、`labels`、`mutex_keys`、`compile_logs`、`run_logs` 和变量放入配置，本次选择的 `cases`、逐 Case `case_runs` 与可选 `seed` 放入 `inputs`。提交前调用 `/runs/plan` 或已有配置的 `/plan`，检查任务数量、命令、目录、标签、互斥键和 `deferred_values`；预演不分配 seed、不创建任务。正式提交在一个事务中分配自动值、冻结快照并建立批次。

```python
api_inputs = {
    "cases": ["case-a"],
    "case_runs": {"case-a": 1},
    "seed": None,
}
```

插件一次展开多个任务时，API 在一个事务中分配宿主自动值、建立批次和任务并写入幂等回执，返回有序任务 ID。插件不得在展开期间启动进程、读取任务数据库或自行生成易冲突的全局序号；任何一个草稿无效都必须使自动值和整批任务一起回滚。

任务使用哪个插件只由配置顶层的 `plugin` 字段决定。插件可声明：

- `required_common_fields`：该插件要求出现的公共字段集合。
- `config_model`：只描述插件专属字段的 Pydantic 模型；建议 `extra="forbid"`，使拼错字段立即出现在配置诊断中。
- `input_model`：只描述本次运行输入的 Pydantic 模型；字段必须对应 `run_fields` 及其次数辅助字段。

公共字段由核心统一校验，不要在 `config_model` 中重复声明。已有的第三方插件若未提供 `config_model` 仍可装载，但配置页只能完成公共字段与插件存在性诊断，并会显示能力降级警告；新增插件应提供模型，才能形成完整 API schema。

## 字段与候选项发现

使用 `run_field(name, component, **options)` 注册运行组件。当前组件类型为 `string`、`integer`、`seed`、`path`、`string-list`、`json` 和 `case-picker`。核心会在装载插件时检查字段名、组件类型和重名；无效声明只隔离该插件，不会破坏其他插件。字段合同不依赖 React，前端实现可以替换而不改变插件。

`case-picker` 默认没有运行项。单击 Case 增加一次，非零时才显示 `×N`，点击次数才展开精确输入。鼠标框选只建立临时编辑作用域，不增加次数；滚轮悬浮单项时调整单项，位于作用域内时同步调整整组。编辑组内任一 `×N` 会把固定值应用到整组，点击组件外取消作用域，因此不需要额外批量工具条。插件用 `count_field` 声明逐项次数映射字段，用 `default_count_field` 声明默认次数字段，前端不依赖 `case_runs` 或 `runs` 等固定名称：

```python
run_field(
    "jobs",
    "case-picker",
    required=True,
    multiple=True,
    label="Job",
    count_field="job_repeats",
    default_count_field="default_repeats",
)
```

`seed` 留空表示使用宿主自动值，填写整数表示固定起始值。配置由 `config_model` 校验，本次输入由 `input_model` 校验，最终任务再经过 `TaskCreate` 或 `TaskDraft` 校验。

## 自动值与不可变快照

任务在事务提交后不可修改参数。插件需要 Unix 时间型递增 seed 时返回 `TaskDraft`，而不是在 `starting` 钩子里修改任务：

```python
from localflow.models import DeferredValue, TaskDraft

TaskDraft(
    name=case_name,
    working_directory=working_directory,
    command=["./run", "--seed", "${seed}"],
    custom={"report": "reports/${seed}.log"},
    deferred_values={
        "seed": DeferredValue(
            source="monotonic_unix",
            namespace="my-plugin.seed",
        )
    },
)
```

核心在入队写事务中按命名空间分配 `max(当前 Unix 秒, 上次值+1)`，递归替换名称、目录、命令、标签、互斥键和自定义信息，并把最终值加入 `custom`。同一批、并发请求、进程重启和墙钟回拨仍严格递增；字段冲突或任一任务无效会回滚整个批次。普通插件继续返回 `TaskCreate`，无需了解自动值机制。

插件可提供同步 `discover(values, context) -> list[str]`。选择一份配置时，核心先用 configlib 展开该文件的显式 `!include`，解析共享与本配置变量，再调用发现钩子。核心把钩子放入工作线程并设置 5 秒上限；非字符串列表、异常和超时都会成为该配置的行内诊断，不会终止服务。

## 随安装提供的插件

- `verification.py`：配置 Case 路径后自动发现 Case，支持点击或滚轮调整、框选后的同步增量/固定值、逐 Case 次数以及留空随机/手工种子；每次运行形成独立任务。`${case}`、`${seed}` 和 `${run}` 延迟到单任务展开时解析，命令可直接引用。每个显示标签同时生成 `tag:<标签>` 互斥键，因此任一标签相同的仿真按队列串行。
- `command.py`：生产插件。只需名称、工作目录和命令，示例优先使用字符串，也兼容精确 argv 列表，适合直接代为执行一条命令。
- `verification.py`：生产插件。发现 Case、展开逐 Case 任务、在入队事务中分配递增 seed 并判定 VCS/UVM 结果。

其它状态、交互退出和通用选择器插件只作为测试夹具在质检时动态写入隔离目录，不进入首启内容或 Linux 发布包。

插件可选实现 `inspect(values, context)`，返回只读检查项列表。宿主总会先检查公共工作目录与命令入口，再合并插件项；每项声明稳定 `name`、可选 `label`、字符串 `value`、`text/path/command` 类型、`ok/info/warning/error` 严重级别和可选说明。检查钩子不得修改配置、扫描多层无界目录或长期阻塞；网页与 API 使用同一有界调用。

停止协议和人在环终端的完整合同分别见 [停止与残留进程保证](stopping.md) 和 [交互终端](terminal.md)。

声明式模板示例：

```yaml
plugin: command
name: "${name}"
working_directory: "${scripts_dir}"
command: "./run.sh --seed ${seed}"
labels: [verification, "${project}"]
mutex_keys: ["license:${simulator}"]
custom:
  report_path: "${report_root}/${seed}/index.html"
variables:
  name: nightly
  project: chip-a
```

`config/variables.yaml` 提供全局和项目变量，模板中的 `variables` 是模板层，网页 JSON 是本次运行层。优先级依次为本次运行、模板、项目、全局；未知引用、循环和结构值误嵌入文本都会拒绝。变量来源只用于内部诊断，不会混入任务的插件计算信息或网页详情。

验证插件可配置多个 `compile_logs` 与 `run_logs`。没有任何实际存在的运行日志时状态为“编译错误”，详情只列出确实存在的编译日志；只要存在运行日志，就只显示运行日志，并优先解析最后一个 `UVM Report Summary` 的 `UVM_ERROR`/`UVM_FATAL` 计数，形成 `PASS`、`ERROR` 或 `FATAL`，不把计数显示在状态或计算信息中。没有 UVM 摘要时才使用行首锚定的 VCS `Error-[…]`、`Fatal-…`、`*E,`、`*F,` 诊断，避免普通说明文字或较早的旧摘要误判。seed 留空时，任务仍只以 case 命名；入队事务为每次运行分配不同且递增的 seed，命令、日志路径与详情保存同一个最终值。

## 装载代次与错误边界

文件监视器发现插件变化后重新扫描全部插件，并使用包含代次和摘要的新模块名装载。单个文件导入错误写入诊断；只要新扫描产生了可用插件，它们构成新代次。正在运行和历史任务不重新展开，因此不受插件修改影响。

插件没有操作系统级沙箱，能以 `localflow` 服务用户权限读写文件。只安装受信任代码，并依赖服务用户、根目录权限和 systemd 单元限制缩小影响范围。
