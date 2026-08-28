# 配置

首次直接运行 `localflow` 后，运行根目录只提供两份可运行配置：

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
cases/
scripts/
```

配置目录按插件名分组。网页“运行”页只扫描 `config/`；根目录的 `config.yaml` 不属于任务配置，不进入资源树，也不会动态加载。时间校准保存在运行状态中，不写入启动配置。

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
retention:
  # One duration covers task details and terminal output.
  task_days: 3
```

未写字段使用安全默认值：监听 `0.0.0.0`、匿名摘要读取、最多四个并发任务和有界日志容量。需要覆盖高级字段时参照 `Settings` 模型或运维文档添加，不为默认安装预先生成空字段。

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

运行后在 LocalFlow 根目录生成 `hello-world.txt`。把 `working_directory` 和 `command` 改成自己的目录与命令即可。`command` 优先使用字符串，Ubuntu 明确以 `/bin/sh -lc` 执行，管道、重定向和 shell 变量均可直接使用；需要完全绕过 shell 解析时仍可写参数列表，例如 `command: [python3, -u, script.py]`。任务快照最终统一保存为参数数组。

## 验证仿真

`config/verification/demo.yaml` 保存稳定内容：Case 目录、工作目录、命令、标签与日志模板。`${case}`、`${seed}` 和 `${run}` 是验证插件为每个任务填入的延迟变量；首启文件不再使用含义不明的 `${root}`。本次要运行的 Case、各自次数和可选 seed 只在使用界面或 API `inputs` 中提供。

进入使用界面后，顶部只读检查区显示已经解析的工作目录、命令、Case 目录和脚本路径。检查项由宿主与插件共同返回：正常为勾选，警告或错误为感叹号；悬浮或键盘聚焦图标可读原因。首次打开、保存成功、外部同步和相关运行输入变化都会重新检查。检查使用有界超时和旧请求取消，不能阻塞编辑器，也不能把旧结果覆盖到新配置上。

## 诊断与导入

- 没有任何公共任务字段：普通参数文件。
- 出现任一公共字段：校验公共字段。
- 出现 `plugin`：继续校验插件是否加载以及插件专属字段。
- 语法、导入、类型、必填字段或插件字段错误：文件仍可编辑，但不可运行。

YAML 可使用 configlib 的显式 `!include`。需要复用时再创建一份共享参数文件；默认安装不生成空变量文件或共享默认文件。

网页保存携带内容版本，服务先解析和诊断，再在同目录写临时文件、刷新并原子替换。外部编辑由文件事件自动同步。保存、同步和运行提示位于固定通知层，不参与资源树、工具栏或编辑器布局；必须处理的冲突和字段错误仍保留在对应内容旁。

## 资源与软链接

“运行”页的资源树同时管理 `config/` 与 `plugins/`，支持空目录、新建目录、拖放、行内重命名、复制、剪切、粘贴和删除。快捷键为 `Ctrl/Command+C`、`X`、`V`、`F2` 与 `Delete`；常用动作也直接显示在工具栏，不藏入更多菜单。插件 Python 文件保存前先做语法编译，配置保存前先做完整解析与诊断；版本冲突不会覆盖外部更新。

整个 `config/`、`plugins/`，其中的目录或单个文件都可以是软链接。读取和编辑跟随目标，但保留链接目录项；移动或重命名软链接移动链接本身，复制软链接复制链接文本，删除软链接不删除目标。目录移动、复制或删除若会让原本可解析的 `!include` 失效，操作会回滚。HTTP 路径仍只接受以 `config/` 或 `plugins/` 开头的词法路径，禁止绝对路径和 `..`；外部目标必须由本机所有者预先创建软链接才能获得能力。

原生文件事件对嵌套软链接的跟随行为不一致，因此服务每秒进行一次有界内容哈希校对。网页和 AI Agent 修改 `config/` 或顶层插件文件后，另一侧无需刷新按钮即可看到变化。
