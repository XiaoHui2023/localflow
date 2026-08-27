# LocalFlow 配置说明

## 文件来源

运行根目录的 `config` 文件夹是配置来源。支持 `.yaml`、`.yml`、`.toml` 和 `.json`。网页读取和修改同一批文件，不建立第二份数据库配置。

推荐布局：

```text
config/
├── server.yaml
├── variables.yaml
├── shared/
│   └── task-defaults.yaml
├── projects/
│   └── project-a.toml
└── tasks/
    ├── random-number.yaml
    ├── verification-demo.yaml
    ├── marker-warning.yaml
    └── interactive-shutdown.yaml
```

## 服务设置

```yaml
server:
  bind: 127.0.0.1
  port: 0
  anonymous_access: summary
  tls_certfile: null
  tls_keyfile: null
  trusted_proxies: []

execution:
  backend: systemd
  max_concurrency: 4
  sigint_grace_seconds: 20
  sigterm_grace_seconds: 10

retention:
  task_days: 3

logging:
  level: info
  service_file_mb: 10
  service_files: 5
  task_file_mb: 100
  task_total_mb: 4096
  keep_free_mb: 512
  database_mb: 512
  wal_mb: 16

time:
  display_timezone: Asia/Shanghai
  privileged_helper:
    - /usr/bin/sudo
    - -n
    - /usr/libexec/localflow-set-time.py
```

`port: 0` 表示每次启动由内核选择端口，实际地址写入 `runtime/port`。`anonymous_access` 可为 `disabled`、`summary` 或 `readonly`。非回环 `bind` 必须同时配置存在的 TLS 证书、私钥和明确的受信任反向代理 CIDR；缺一项服务都会拒绝启动。

任务信息、任务事件和终端输出共用 `retention.task_days`，默认保留三天并成对清理。总日志容量与预留空闲空间仍是防止磁盘耗尽的硬安全阀。

`logging` 同时约束服务日志、任务输出和数据库文件。`service_file_mb` 是单个服务日志文件上限，`service_files` 是轮转备份数；`task_file_mb` 是每个任务的输出上限，达到后任务继续运行，只停止保存后续输出并在文件末尾写入说明；`task_total_mb` 是全部任务日志预算，必须至少覆盖 `max_concurrency × task_file_mb`。终态任务按结束时间从旧到新清理，运行中任务不删除。`keep_free_mb` 是运行目录所在文件系统的保留空间，达到阈值时暂停文件日志。`database_mb` 和 `wal_mb` 分别限制 SQLite 主库与 WAL。

网页与本机文件内容、版本和诊断实时同步；`variables.yaml` 与 `tasks/` 中的任务配置在每次使用时重新读取，插件文件保存后自动进入新代次。配置资源树自动读取任务配置，不需要手动扫描。编辑和运行共用同一文件页面：可运行配置默认直接显示运行参数，其它文件默认打开编辑器；需要修改可运行配置时点击“编辑”。`server.yaml` 中的监听、执行器、并发度、宽限期和保留期属于进程级设置，保存并校验后需要重启主 `localflow.service` 才生效，已有 systemd 任务不会因此终止。

## 导入与诊断

公共片段不需要插件，可用 `python-library-configlib` 的 YAML `!include` 合并到任务配置：

```yaml
!include ../shared/task-defaults.yaml
plugin: command
name: 随机数
working_directory: "${scripts_dir}"
command: [python3, -u, random_number.py]
```

导入路径必须留在当前运行根目录的 `config/` 中；越界、缺失或不支持格式会被拒绝。JSON、TOML 和 YAML 都可作为独立配置，YAML 可负责组合导入。`plugin` 只从合并后的配置顶层读取，网页不保存另一份插件选择。

诊断按内容逐层启用：

- 没有 `plugin`、`name`、`working_directory`、`command`、`labels`、`mutex_keys`、`custom`、`stop`、`variables`、`project` 中的任何字段：普通配置，不当成任务。
- 出现任一公共字段但没有 `plugin`：共享片段，校验已经出现的公共字段，可被其它配置导入，但不可直接运行。`shared/task-defaults` 就属于这一类，因此使用共享片段图标，而不是可运行任务图标。
- 写有 `plugin`：任务配置；先校验公共字段，再校验插件是否已加载、插件所需公共字段和插件专属字段。全部通过后才显示运行操作。

外部编辑产生的无效文件仍可在网页打开并看到错误，以便修复；网页不会允许保存新的无效公共/任务配置，也不会运行诊断未通过的配置。

资源树只在图标上表达诊断：无公共字段使用普通文件图标，共享片段使用叠放文件图标，可运行配置使用带检查标记的文件图标，错误使用红色警告图标。文件名始终保持中性色并隐藏配置扩展名。具体错误不堆在资源树中；打开无效文件后，错误列表出现在编辑区上方。每个文件独立诊断，一个损坏文件不会阻止其它文件显示。

缺字段、类型错误和 YAML 语法错误的可复制样例位于 `examples/config-errors/`。三类错误都会被标记为无效、显示具体诊断，并由运行 API 拒绝。

## 变量

```yaml
global:
  workspace_root: /srv/workspaces
  report_root: /srv/reports

projects:
  chip-a:
    project_dir: "${workspace_root}/chip-a"
    simulator: vcs
```

模板按变量名使用 `${workspace_root}`、`${project_dir}`、`${name}` 和 `${seed}`。变量来源层不会写进引用前缀，而是在解析结果中单独记录，便于查看某个值来自全局、项目、模板还是本次运行。插值不执行任意 Python 表达式。

层级优先级：本次运行、模板、项目、全局。解析器检测未知变量、循环和类型不匹配。预览响应显示每个字段的来源和值，并对密钥型变量做遮盖。

## 任务配置

```yaml
plugin: verification
name: verification
project: chip-a
labels: [verification, "${simulator}"]
mutex_keys: ["license:${simulator}"]
working_directory: "${project_dir}"
command:
  - ./run_case.sh
  - --case
  - "${case}"
  - --seed
  - "${seed}"
custom:
  report_path: "${report_root}/${case}/${seed}/index.html"
```

命令使用参数数组，不经过 shell 二次解析。确需管道或重定向时，应显式把 shell 程序及其参数写入数组，例如 `[bash, -lc, "cmd | other"]`。

## 同步与冲突

外部编辑器保存后，文件监视器进行去抖、读取和完整校验。有效内容产生新版本并推送网页；无效内容保留在磁盘但不进入运行配置，网页显示文件、行列和原因。

网页保存携带当前版本。服务在同目录创建仅所有者可读的临时文件，完成写入、同步和校验后原子替换目标。版本冲突不自动合并。

## 权限

推荐权限：

```text
localflow-root/          0750 localflow:localflow
config/                  0750
plugins/                 0750
runtime/                 0750
logs/                    0750
logs/service/            0750
secrets/                 0700
secrets/api-key          0600
secrets/web-admin-key    0600
runtime/port             0600
```

若需要同机只读用户查看摘要，应通过 HTTP 权限投影或独立只读组实现，不应赋予 `secrets`、配置写权限或服务用户身份。
