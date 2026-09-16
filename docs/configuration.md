# 配置

首次直接运行 `localflow` 后，配置根只提供两份可运行配置：

```text
localflow
config.yaml                    # 启动配置，网页不显示，修改后重启
config/
├── command/
│   └── hello-world.yaml       # 简易命令
└── verification/
    └── demo.yaml              # 验证仿真
plugins/
├── command.py
└── verification.py
scripts/
```

配置目录按插件名分组。任务页内的运行工作区只扫描 `config/`；根目录的 `config.yaml` 不属于任务配置，不进入资源树，也不会动态加载。时间校准保存在运行状态中，不写入启动配置。

## 启动配置

`config.yaml` 的默认内容只保留常改项，并在原位解释含义：

```yaml
# LocalFlow reads this file only when it starts. Restart after editing.
server:
  # 0 asks Ubuntu for an available port; use 1-65535 for a fixed port.
  port: 0
execution:
  # auto uses systemd when its user manager is available, otherwise subprocess.
  backend: auto
  # unlimited (and legacy auto) adds no LocalFlow task-slot limit.
  max_concurrency: unlimited
retention:
  # One duration covers task details and terminal output.
  task_days: 3
```

未写字段使用安全默认值：监听 `0.0.0.0`、匿名摘要读取、不设置 LocalFlow 任务槽位上限，并使用有界日志容量。`max_concurrency: unlimited` 不会因 CPU 核数把独立任务留在队列；旧版本生成的 `auto` 作为 `unlimited` 的兼容别名，保证升级后不会延续旧上限。只有 `1..4096` 的整数会由管理员显式限制并行任务数。无软件槽位上限不等于无限硬件资源：任务仍共享服务器的 CPU、内存和 I/O，过量负载可能降低吞吐或触发系统级资源失败。需要覆盖其它高级字段时参照 `Settings` 模型或运维文档添加。

多服务器免重复登录只适用于一个共同管理的 DNS 父域。例如各节点均通过 HTTPS 使用 `node-a.localflow.example.test` 一类主机名，并安全配置相同的 `secrets/web-admin-key` 后，可在每台加入：

```yaml
server:
  session_cookie_domain: localflow.example.test
```

省略时使用更安全的 host-only cookie；同一主机名即使随机端口改变也不需要此项。原始 IP 或无共同受控父域的地址不能共享浏览器会话。

`auto` 会先探测当前账号的 systemd 用户管理器；可用时任务由 transient unit 持有，网页服务重启不带走任务。直接解压运行且用户管理器不可达时会在服务日志明确记录原因并使用 subprocess，避免页面可打开但所有任务随后启动失败。要求强制持久承载的部署可写 `backend: systemd`，并按运维文档启用用户管理器；此模式探测失败时任务会如实失败并把原因写入任务输出。

旧安装若只有根目录 `localflow.yaml` 或更早的 `config/server.yaml`，下一次启动会把它原样迁移为根目录 `config.yaml`，随后仅从新位置读取。若 `config.yaml` 已存在，则不会覆盖。

## 简易命令

`config/command/hello-world.yaml` 只有四个字段：

```yaml
# The working directory is relative to the LocalFlow folder.
plugin: command
name: hello-world
working_directory: .
command: "printf 'hello world\\n' > hello-world.txt"
```

运行后在 LocalFlow 配置根生成 `hello-world.txt`。把 `working_directory` 和 `command` 改成自己的目录与命令即可。所有可运行配置都必须显式给出工作目录；绝对路径原样使用，相对路径统一以 LocalFlow 配置根为基准，并在预演和入队前冻结成绝对路径。字符串 `command` 自动选择服务进程的 `$SHELL`，缺失时读取该运行用户的 passwd 登录 Shell，并以 `<shell> -ic` 加载 `.bashrc`、`.cshrc`、`.zshrc` 或该 Shell 自己的交互启动配置，因此任意插件都能使用同一账号日常终端中的函数和别名。配置可用 `shell: /bin/bash` 等显式覆盖；交互启动文件执行完后，核心再次切回冻结工作目录。参数列表例如 `command: [python3, -u, script.py]` 始终完全绕过 Shell，不能同时设置 `shell`。任务快照最终统一保存为参数数组。

## 验证仿真

`config/verification/demo.yaml` 保存稳定内容：插件提供的 Case 名称、工作目录、命令、标签与日志模板。Case 不是 LocalFlow 核心目录；验证插件既可从 `case_names` 生成候选，也可通过 `case_directory` 扫描用户指定目录的一层内容，发现结果随配置或目录重新读取。`${case}` 和 `${seed}` 是验证插件仅有的两个按任务变量；命令可以使用任意子集，也可以完全不用。插件不会提供 `root`、`scripts_dir`、`cases_dir`、`run`、`runs` 或 `cases` 等隐式变量，也不会猜测或追加参数。首启示例演示 GNU Make 命令行变量 `make all CASE=${case} SEED=${seed}`，但它只是示例而非验证合同。其它工具可按自身语法写，或直接使用不带 Case/seed 的任意命令。本次要运行的 Case、各自次数和可选 seed 只在使用界面或 API `inputs` 中提供。

字符串命令支持 Make、Shell、可执行文件以及管道、重定向等任意 Ubuntu shell 命令；参数列表用于完全绕过 shell。GNU Make 的 `-f` 只选择 Makefile，不会切换目录；要在项目目录运行，应设置 `working_directory`，或在命令中明确使用 `make -C <目录>`，LocalFlow 不从任意命令文本猜测目录。任务启动前，输出日志会记录解析后的工作目录和最终命令，自动 seed 也已替换，便于直接核对实际执行内容。

需要为单个任务加载工具链环境时使用公共 `source` 字段。它是一个按顺序执行的非空脚本路径列表：

```yaml
working_directory: /srv/project
source:
  - env/license.csh
  - env/toolchain.csh
command: make all
```

相对路径以冻结后的 `working_directory` 为基准，绝对路径直接使用；包含空格和软链接的路径由核心安全引用。所有文件在任务选择或自动检测的同一个 Shell 进程中依次加载，前一个脚本设置的环境变量、函数和别名可供后一个脚本及最终命令使用，但不会泄漏到其它任务。即使脚本内部切换目录，LocalFlow 也会在运行 `command` 前恢复工作目录。POSIX sh/dash 使用等价的 `.` 语义。

如果厂商脚本要求 `-env_path` 等参数，把调用封装在一个属于所选 Shell 的薄包装脚本中，配置仍然只填写包装脚本路径：

```csh
# env/localflow-toolchain.csh
source /tools/vendor/setup.csh -env_path /tools/project/environment.env
```

```yaml
source:
  - env/localflow-toolchain.csh
```

脚本内容必须与任务所选 Shell 兼容；LocalFlow 不根据扩展名或 shebang 为每项启动不同的子 Shell，因为子进程无法把环境、函数和别名写回父任务 Shell。缺失、不可读或执行失败的任一项都会阻止用户命令。`source` 只适用于字符串命令；精确 argv 列表没有 Shell 环境，配置时会直接诊断为无效。运行审查、任务详情和终端输出逐项显示冻结路径，而命令行仍只显示用户写入的 `command`。字符串、完整 source 语句和 `{path, arguments}` 对象不是该字段的合法形式。

进入使用界面后，顶部只读检查区显示已经解析的工作目录、完整命令、Case 来源、标签、编译日志和运行日志，不再重复显示字符串命令的首词。插件决定检查内容：必须预先存在的输入路径可声明 availability，仅缺失时显示叉号；插件直接提供的 Case 列表以及普通信息和未来生成的日志均不显示图案。首次打开、保存成功、外部同步和相关运行输入变化都会重新检查；检查使用有界超时和旧请求取消。

配置无效时仍保留同一运行入口位置，并把“问题”和“YAML 解析结果”作为主调试工作面展示。调试卡片占满配置标题栏以下的剩余高度；宽屏左右分栏，窄屏上下分区，各区独立滚动。不得按当前错误条数收缩卡片或用固定最大高度在下方留下空白。

编辑器按文件保留未保存草稿。修改后的文件及其父目录在资源树显示圆点，切换文件不会丢失草稿；保存成功、删除或明确采用外部最新版本后清除对应状态。未保存配置可以进入运行审查，但必须先保存才能提交。

## 诊断与导入

- 没有任何公共任务字段：普通参数文件。
- 出现任一公共字段：校验公共字段。
- 出现 `plugin`：继续校验插件是否加载以及插件专属字段。
- 语法、导入、类型、必填字段或插件字段错误：文件仍可编辑，但不可运行。

YAML 使用 `python-library-configlib >= 0.1.11` 的显式 `!include`、根路径变量、相对变量、列表展开和字典深合并。变量在全部 include 合并后按整棵 YAML 树解析，因此任意 YAML 键都可被 `${project.command}` 这类路径引用；兼容的 `variables:` 表仍把自己的键作为短名别名。未知引用和循环引用会阻止运行。公共任务字段和插件声明字段必须在变量全部结算后再次执行与提交期相同的类型校验，例如 `labels: ["${x}"]` 在 `x: null` 时直接进入网页调试状态，不能等到运行后才由任务模型失败。未被插件使用的站点自定义空值保持合法；可选公共字段的显式 `null` 按未提供处理。`|` / `>` 块标量内的独占行变量仍是命令文本，不参与结构层 spread/merge。需要复用时再创建共享参数文件；默认安装不生成空变量文件或共享默认文件。

网页保存携带内容版本并在同目录写临时文件、刷新、原子替换。文本没有变化时保存按钮禁用；发生变化后启用，保存成功或重新载入后再次禁用。编辑变化经过 220 ms 防抖后取消旧请求并重新诊断；Monaco 在具体行列画错误标记，下方有界“问题”面板列出同一结果，点击可回到位置。语法或导入错误不阻断保存，也不跳离编辑页；公共字段、插件 schema 与运行路径只在插件使用界面诊断。所有插件都保留站点自定义顶层配置；这些键属于合并后的 YAML 变量树，可被其它值引用并原样传给插件，但插件专属模型只校验自己声明的字段。本次运行输入仍严格限制为插件声明的 `run_fields`。外部编辑由原生文件事件与至多一秒的内容校对自动同步，并通过 SSE 定向刷新资源树和当前文件；有效与无效 YAML 都载入无脏草稿的编辑器，无效内容直接投影到 Monaco 与“问题”面板。已有未保存草稿时保留草稿并提示版本冲突，不以磁盘内容静默覆盖。

允许自定义键不等于提供隐式环境变量。command、verification 和第三方插件都只能引用 YAML 合并树中实际定义的键；`root`、`scripts_dir`、`cases_dir` 与本次运行 `inputs` 不会自动出现。只有插件显式声明的 `${case}`、`${seed}` 可以保留到任务展开阶段。未知变量会参与实时诊断并阻止运行，但不妨碍继续编辑或保存。

## 资源与软链接

任务页运行工作区以 `config/` 内容作为资源树根，不显示冗余根节点或 `plugins`。所有配置均为普通文件；新建文件只创建空白文件。资源树支持空目录、拖放移动、行内重命名、复制、剪切、粘贴和删除；剪切/粘贴也是拖放的键盘等价路径。

整个 `config/`、`plugins/`，其中的目录或单个文件都可以是软链接。读取和编辑跟随目标，但保留链接目录项；移动或重命名软链接移动链接本身，复制软链接复制链接文本，删除软链接不删除目标。目录移动、复制或删除若会让原本可解析的 `!include` 失效，操作会回滚。HTTP 路径仍只接受以 `config/` 或 `plugins/` 开头的词法路径，禁止绝对路径和 `..`；外部目标必须由本机所有者预先创建软链接才能获得能力。

原生文件事件对嵌套软链接的跟随行为不一致，因此服务每秒进行一次有界内容哈希校对。网页和 AI Agent 修改 `config/` 或顶层插件文件后，另一侧无需刷新按钮即可看到变化。
