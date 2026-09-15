# 任务私有 Shell source

## 方案

`source` 是公共任务执行字段，而不是 command/verification 的插件字段。一个字符串或路径列表在最终工作目录解析为绝对路径，并与用户命令在同一个任务交互 Shell 中执行。脚本全部成功后才执行命令；source 的环境只由该 Shell 的子进程继承，控制器与其它任务不变。sh/dash 使用 POSIX `.`，bash、zsh、csh/tcsh、fish 使用 `source`。精确 argv 不具备 Shell 上下文，因此与 source 组合时在模型层拒绝。

## 覆盖

- `tests_v2/test_command_contract.py`：单路径/列表规范化、工作目录冻结、含空格路径引用、argv 反例、命令展示不泄漏注入包装。
- `tests_v2/test_plugins.py`：command 与 verification 都由注册表取得同一公共 source 行为，不依赖插件转发。
- `tests_v2/test_config.py`：运行审查按数组边界显示解析路径，缺失脚本为明确错误。
- `tests_v2/test_tasks.py`：冻结后的 source 路径随任务详情 API 返回，不依赖配置文件继续存在。
- `frontend/e2e/localflow.spec.js`：真实任务展开详情逐项显示“加载环境”。
- `tests_target/test_shell_profile.py`：Linux 上真实 bash source、tcsh source，以及并行未 source 任务看不到另一任务的变量；任务终端在命令前记录 `process.source`。

## 边界

source 脚本是受信任的用户任务输入，权限与命令相同。LocalFlow 不解析或合并脚本内容，也不把脚本变量提升为 YAML/configlib 变量。网页运行审查与任务详情逐项显示冻结后的 source 路径和原始 command；终端逐项记录实际加载路径。实际 shell、`-ic`、`cd` 与引用包装继续只留在不可变执行快照/API。

本机是 Windows，Linux 专属 bash/tcsh 测试按平台条件跳过；Docker Desktop Linux pipe `npipe:////./pipe/dockerDesktopLinuxEngine` 不存在，固定浏览器编排也在三次有界重试后确认引擎不可用。因此公共模型、插件传播、路径冻结与审查已在本机通过，真实 Linux Shell 执行证据保持 partial，不冒充完成。恢复条件是启动 Docker Desktop Linux engine 或在 Ubuntu runner 执行 `pytest -q tests_target/test_shell_profile.py`。
