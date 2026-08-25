# LocalFlow 插件开发

插件是运行根目录 `plugins/*.py` 中的受信任 Python 代码。它声明网页字段、候选项发现、显示状态，以及把输入展开为一个或多个 `TaskCreate` 的方法；稳定的排队和进程生命周期仍由核心服务管理。

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
    example = {"plugin": "example", "name": "示例", "command": ["echo", "ok"]}
    run_fields = [
        run_field("name", "string", required=True, label="名称"),
        run_field("command", "string-list", required=True, label="命令"),
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

装饰器只能在 LocalFlow 装载该文件时调用。`expand` 必须返回 `TaskCreate` 列表，不能自行启动进程或写任务数据库。返回后核心会把插件名称、版本、文件 SHA-256、装载代次、输入和显示状态合同保存进每个任务快照。

## API 合同

每个插件同时服务网页和 `POST /api/v1/runs`，不维护第二套 API 参数。请求中的 `configuration` 与 YAML 配置含义相同，`inputs` 对应本次运行输入；核心调用同一个 `expand_config()`。`GET /api/v1/plugins` 为每个已加载插件返回 `api.endpoint`、`api.configuration_schema`、`api.plugin_fields_schema`、`api.input_fields` 和 `api.example`，用于生成调用文档或客户端表单。`configuration_schema` 合并公共字段与该插件字段，可直接校验完整配置；`plugin_fields_schema` 只描述插件专属部分。插件不得在 `config_model` 中重复定义公共字段。插件必须维护可运行的 `example`、定义 `config_model`，并让示例同时通过配置诊断和 API 展开测试。若可运行示例需要 Case 等本次输入，另设 `api_inputs`；它与 `example` 一起组成可直接提交的请求体。

### AI Agent 组合验证配置

AI Agent 应先读取 `GET /api/v1/plugins` 中 `verification.api`，复制 `example.configuration` 作为最小骨架，再按 `configuration_schema` 增删字段；不要猜字段名或另造一套模板。长期不变的 `command`、`case_directory`、`labels`、`mutex_keys`、`compile_logs`、`run_logs` 和变量放入配置文件，本次选择的 `cases`、逐 Case `case_runs` 与可选 `seed` 放入 `inputs`。命令和日志路径可自由组合 `${case}`、`${seed}`、`${run}` 及配置变量；提交前使用配置诊断或 JSON Schema 拒绝未知字段。`api.example` 本身必须能直接运行，因此也可作为生成器的正向样本。

```python
api_inputs = {
    "cases": ["case-a"],
    "case_runs": {"case-a": 1},
    "seed": None,
}
```

插件一次展开多个 `TaskCreate` 时，API 在一个事务中建立批次并返回有序任务 ID。插件不得在展开期间启动进程；任何一个草稿无效都必须使整次请求失败，避免只创建半个批次。

任务使用哪个插件只由配置顶层的 `plugin` 字段决定。插件可声明：

- `required_common_fields`：该插件要求出现的公共字段集合。
- `config_model`：只描述插件专属字段的 Pydantic 模型；建议 `extra="forbid"`，使拼错字段立即出现在配置诊断中。

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

`seed` 留空表示每次生成随机值，填写整数表示固定起始值。字段仍应在插件的 `config_model` 和 `expand` 中做业务校验；最终任务还会经过 Pydantic `TaskCreate` 校验。

插件可提供同步 `discover(values, context) -> list[str]`。选择一份配置时，核心先用 configlib 展开该文件的显式 `!include`，解析共享与本配置变量，再调用发现钩子。核心把钩子放入工作线程并设置 5 秒上限；非字符串列表、异常和超时都会成为该配置的行内诊断，不会终止服务。

## 随安装提供的插件

- `verification.py`：配置 Case 路径后自动发现 Case，支持点击或滚轮调整、框选后的同步增量/固定值、逐 Case 次数以及留空随机/手工种子；每次运行形成独立任务。`${case}`、`${seed}` 和 `${run}` 延迟到单任务展开时解析，命令可直接引用。每个显示标签同时生成 `tag:<标签>` 互斥键，因此任一标签相同的仿真按队列串行。
- `declarative.py`（插件名 `command`）：把名称、目录、命令、标签、互斥键和自定义字段解析成普通任务。
- `marker.py`：用退出码表达“检查通过、需要关注、未通过、检查异常”，示范插件任意领域状态。
- `interactive.py`：持续程序在 Ctrl+C 后进入控制模式，可输入 `status`、`resume` 或 `quit`；同时示范停止按钮自动等待提示并输入 quit。

停止协议和人在环终端的完整合同分别见 [停止与残留进程保证](stopping.md) 和 [交互终端](terminal.md)。

声明式模板示例：

```yaml
plugin: command
name: "${name}"
working_directory: "${scripts_dir}"
command: [bash, -lc, "./run.sh --seed ${seed}"]
labels: [verification, "${project}"]
mutex_keys: ["license:${simulator}"]
custom:
  report_path: "${report_root}/${seed}/index.html"
variables:
  name: nightly
  project: chip-a
```

`config/variables.yaml` 提供全局和项目变量，模板中的 `variables` 是模板层，网页 JSON 是本次运行层。优先级依次为本次运行、模板、项目、全局；未知引用、循环和结构值误嵌入文本都会拒绝。变量来源只用于内部诊断，不会混入任务的插件计算信息或网页详情。

验证插件可配置多个 `compile_logs` 与 `run_logs`。没有任何实际存在的运行日志时状态为“编译错误”，详情只列出确实存在的编译日志；只要存在运行日志，就只显示运行日志，并优先解析最后一个 `UVM Report Summary` 的 `UVM_ERROR`/`UVM_FATAL` 计数，形成 `PASS`、`ERROR` 或 `FATAL`，不把计数显示在状态或计算信息中。没有 UVM 摘要时才使用行首锚定的 VCS `Error-[…]`、`Fatal-…`、`*E,`、`*F,` 诊断，避免普通说明文字或较早的旧摘要误判。seed 留空时，排队任务只以 case 命名；任务取得执行资格后才用当前 Unix 时间戳冻结 seed、替换命令，并在详情显示随机种子。

## 装载代次与错误边界

文件监视器发现插件变化后重新扫描全部插件，并使用包含代次和摘要的新模块名装载。单个文件导入错误写入诊断；只要新扫描产生了可用插件，它们构成新代次。正在运行和历史任务不重新展开，因此不受插件修改影响。

插件没有操作系统级沙箱，能以 `localflow` 服务用户权限读写文件。只安装受信任代码，并依赖服务用户、根目录权限和 systemd 单元限制缩小影响范围。
