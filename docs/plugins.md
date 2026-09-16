# LocalFlow 插件开发

插件是配置根 `plugins/*.py` 中的受信任 Python 代码。它声明网页字段、候选项发现、显示状态，以及把输入展开为一个或多个 `TaskCreate`/`TaskDraft` 的方法；自动值、稳定排队和进程生命周期仍由核心服务管理。

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

AI Agent 应先读取 `GET /api/v1/plugins/verification`，复制 `api.example.configuration` 作为最小骨架，再分别按 `configuration_schema` 和 `input_schema` 生成两部分；不要猜字段名或另造一套模板。长期不变的 `command`、Case 来源、`labels`、`mutex_keys`、`compile_logs`、`run_logs`、`custom_texts` 和变量放入配置，本次选择的 `cases`、逐 Case `case_runs` 与可选 `seed` 放入 `inputs`。Case 来源由插件所有：验证插件可用 `case_names` 直接生成候选，或用 `case_directory` 扫描显式外部目录；核心不创建或维护通用 `cases/`。提交前调用 `/runs/plan` 或已有配置的 `/plan`，检查任务数量、命令、目录、标签、互斥键和 `deferred_values`；预演不分配 seed、不创建任务。正式提交在一个事务中分配自动值、冻结快照并建立批次。

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
- `config_model`：只描述并校验插件专属字段；顶层其它键属于站点自定义变量，不送入该模型，也不因模型的 `extra` 策略报错。
- `input_model`：只描述本次运行输入的 Pydantic 模型；字段必须对应 `run_fields` 及其次数辅助字段。

公共字段由核心统一校验，不要在 `config_model` 中重复声明。所有插件的完整配置都允许任意站点键：configlib 在整棵 include 合并树上解析这些变量，核心保留它们并把完整解析值传给 `expand`，但插件模型只接收自己声明的字段。因此 `extra="forbid"` 可继续用于捕获插件模型内部错误，却不能拒绝 `root`、`extra_inputs`、工具链参数等站点键；宿主公开的完整配置与插件字段 JSON Schema 均以 `additionalProperties: true` 如实表达这一边界。若插件需要判断某个站点键，可在 `validate_config(document)` 中按语义检查，而不是封闭全部未知键。本次运行 `inputs` 是另一条边界，仍由 `input_model`/`run_fields` 严格拒绝未知输入。

扩展键不等于宿主隐式变量。所有变量必须由当前 YAML 或其直接、间接 include 合并结果定义；LocalFlow 不为 command、verification 或第三方插件注入 `root`、`scripts_dir`、`cases_dir`，也不把本次 `inputs` 当作配置变量。插件唯一可声明的延迟占位符是 `${case}` 与 `${seed}`；其它未知变量会使配置保持可见但不可运行，便于在同一编辑工作台修正。需要路径别名时应在 YAML 中显式定义，例如 `project_root: /srv/sim` 后引用 `${project_root}`。

`shell` 是公共字段，只对字符串 `command` 有效；插件只传递配置值，核心在省略时根据服务用户自动选择登录 Shell，统一转换为 `<shell> -ic` 并在 rc 载入后恢复冻结工作目录。插件不得自行拼接 `source ~/.bashrc`、猜测登录 Shell 或把参数列表重新送入 Shell。已有的第三方插件若未提供 `config_model` 仍可装载，但配置页只能完成公共字段与插件存在性诊断，并会显示能力降级警告；新增插件应提供模型，才能形成完整 API schema。

`source` 也是公共执行字段，不归 command、verification 或任一具体插件所有。它只能是非空的脚本路径字符串列表；注册表把全部路径按顺序绑定到该任务自己的字符串命令 Shell。插件不得自行读取脚本、根据扩展名切换 Shell、猜测 `-env_path` 等工具参数、污染 `os.environ`、在控制器进程执行 source，或为不同任务共享可变环境。带参数的厂商初始化由用户写入一个与任务 Shell 兼容的包装脚本，再把该脚本路径放入列表。精确 argv 命令与 `source` 组合、单个字符串、完整语句、对象或混合列表必须在配置诊断阶段拒绝。运行审查由核心逐项显示冻结路径并提前检查存在性。

## 字段与候选项发现

使用 `run_field(name, component, **options)` 注册运行组件。当前组件类型为 `string`、`integer`、`seed`、`path`、`string-list`、`json` 和 `case-picker`。核心会在装载插件时检查字段名、组件类型和重名；无效声明只隔离该插件，不会破坏其他插件。字段合同不依赖 React，前端实现可以替换而不改变插件。

`case-picker` 默认全部为零。每行使用明确的增加按钮，非零时才显示减少按钮；鼠标滚轮和 Case 名称不改变次数。按下只立即改变一次，持续 550ms 后才连发并有界加速，释放或取消立即停止；键盘每次激活严格一步。鼠标框选只建立临时编辑作用域，组内增减同步作用于整组；成功提交后全部次数清零。插件用 `count_field` 声明逐项次数映射字段，用 `default_count_field` 声明默认次数字段，前端不依赖 `case_runs` 或 `runs` 等固定名称：

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

- `verification.py`：通过 `case_names` 生成或从 `case_directory` 动态发现 Case，支持整行增加、减号减少、延迟长按连发、框选同步调整、逐 Case 次数以及留空随机/手工种子；每次运行形成独立任务。插件只提供 `${case}` 与 `${seed}`，可使用任意子集或完全不用；其它变量必须来自合并后的配置树。插件用 Case 名称与完整标签集合的稳定摘要生成一个自动互斥键，因此只有 Case 和全部标签同时相同的仿真自动串行；用户显式 `mutex_keys` 仍可表达许可证等额外资源约束。
- `command.py`：生产插件。只需名称、工作目录和命令，示例优先使用字符串，也兼容精确 argv 列表，适合直接代为执行一条命令。
- `verification.py`：生产插件。发现 Case、展开逐 Case 任务、在入队事务中分配递增 seed 并判定 VCS/UVM 结果。

其它状态、交互退出和通用选择器插件只作为测试夹具在质检时动态写入隔离目录，不进入首启内容或 Linux 发布包。

插件可选实现 inspect(values, context)，返回只读检查项列表。宿主总会先显示公共工作目录与完整命令，再合并插件项；不得从完整字符串命令重复提取“命令入口”。每项声明稳定 name、可选 label、value、text/path/command/tokens 类型、ok/info/warning/error 严重级别、可选说明，以及 none（默认）或 availability 检查策略；`tokens` 的 value 是字符串列表，其余类型是字符串。网页只在 availability + error 时显示叉号；成功与普通信息不显示图案。检查钩子不得修改配置、扫描多层无界目录或长期阻塞；网页与 API 使用同一有界调用。

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

configlib 先合并 `!include`，再以合并后的整棵配置作为变量根；例如被导入文件中的 `project.command` 可由 `${project.command}` 引用。`variables:` 保留为短名兼容表，但不再是唯一变量来源。验证插件的运行输入不会泄漏为模板变量，只有 `${case}` 和 `${seed}` 由插件在逐任务展开时提供。未知引用、循环和结构值误嵌入文本都会拒绝。

验证插件可选配置多个 `compile_logs` 与 `run_logs`，两者省略或使用空列表都可运行。运行前检查区只显示非空配置基于任务工作目录展开后的绝对值，不渲染空栏目，也不检查存在性，因为它们是未来输出。入队快照冻结同一绝对路径，结果判定不会退回控制器目录。未配置编译日志时不产生编译栏目或编译状态；未配置运行日志时只冻结中性的“运行结束”，不根据退出码声称验证成功或失败，但可保留实际存在的编译日志供查看。只有同时配置了编译和运行日志、而运行日志未产生时，才显示存在的编译日志并判定“编译错误”；实际运行日志存在时只显示运行日志并按最终 UVM/VCS 证据判定。

`custom_texts` 是供操作者核对和复制的字符串列表，不参与命令解释。每项可以引用配置变量、`${case}` 或 `${seed}`；运行配置审查区逐行显示模板，保留这两个运行期占位符，不随当前选择变化，入队事务才把它们冻结成每个任务的最终值。运行配置和任务详情都不显示重复的“自定义文本”标题，只呈现文本本身；每项仍是独立复制目标，结果解析更新状态和日志字段时必须保留这些文本。

## 装载代次与错误边界

文件监视器发现插件变化后重新扫描全部插件，并使用包含代次和摘要的新模块名装载。单个文件导入错误写入诊断；只要新扫描产生了可用插件，它们构成新代次。正在运行和历史任务不重新展开，因此不受插件修改影响。

插件没有操作系统级沙箱，能以 `localflow` 服务用户权限读写文件。只安装受信任代码，并依赖服务用户、根目录权限和 systemd 单元限制缩小影响范围。
