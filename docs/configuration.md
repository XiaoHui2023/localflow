# LocalFlow 配置说明

## 文件来源

运行根目录的 `config` 文件夹是配置来源。支持 `.yaml`、`.yml`、`.toml` 和 `.json`。网页读取和修改同一批文件，不建立第二份数据库配置。

推荐布局：

```text
config/
├── server.yaml
├── variables.yaml
├── projects/
│   └── project-a.toml
└── templates/
    └── smoke.json
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
  task_days: 90
  log_days: 30
  event_days: 30

time:
  display_timezone: Asia/Shanghai
  privileged_helper:
    - /usr/bin/sudo
    - -n
    - /usr/libexec/localflow-set-time.py
```

`port: 0` 表示每次启动由内核选择端口，实际地址写入 `runtime/port`。`anonymous_access` 可为 `disabled`、`summary` 或 `readonly`。非回环 `bind` 必须同时配置存在的 TLS 证书、私钥和明确的受信任反向代理 CIDR；缺一项服务都会拒绝启动。

网页与磁盘内容、版本和诊断实时同步；`variables.yaml` 与声明式任务模板在每次展开时重新读取，插件文件保存后自动进入新代次。`server.yaml` 中的监听、执行器、并发度、宽限期和保留期属于进程级设置，保存并校验后需要重启主 `localflow.service` 才生效，已有 systemd 任务不会因此终止。

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

## 模板

```yaml
name: verification
plugin: verification
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
computed_fields:
  report_path: "${report_root}/${case}/${seed}/index.html"
```

命令推荐使用参数数组，避免 shell 再解析。确需 shell 管道时模板必须显式设置 `shell: true`，详情页会突出显示该风险。

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
secrets/                 0700
secrets/api-key          0600
secrets/admin-bootstrap  0600
runtime/port             0600
```

若需要同机只读用户查看摘要，应通过 HTTP 权限投影或独立只读组实现，不应赋予 `secrets`、配置写权限或服务用户身份。
