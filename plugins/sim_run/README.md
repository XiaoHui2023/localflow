# sim_run

在工作目录执行仿真命令，读取日志并用正则判定 PASS / FAIL / ERROR。

限定名：`plugins.sim_run`。

## 导出

| 符号 | 说明 |
| --- | --- |
| `SimRunScript` | 仿真运行 Script |
| `sim_run` | 默认实例 |
| `format_command` | 用实例变量填充命令模板 |
| `evaluate_log_result` | 按 pass / fail 正则判定日志 |
| `resolve_log_path` | 解析相对工作目录的日志路径 |

## Script 参数

| 字段 | 必填 | 说明 |
| --- | --- | --- |
| `project` | 是 | 项目名 |
| `module` | 是 | 模块名 |
| `case` | 是 | Case 名；命令模板可用 `{case}` |
| `seed` | 是 | 随机种子 |
| `work_dir` | 是 | 命令执行的工作目录 |
| `command` | 是 | 命令模板，`str.format` 占位符来自实例变量 |
| `pass_regex` | 是 | 命中日志则 PASS |
| `fail_regex` | 否 | 未命中 pass 时再匹配；留空则直接 FAIL |
| `log_path` | 是 | 仿真日志路径；相对路径相对于 `work_dir` |

## 判定规则

1. 日志文件存在：先匹配 `pass_regex` → PASS；否则若有 `fail_regex` 且匹配 → FAIL；无 `fail_regex` 或未匹配 → FAIL。
2. 日志文件不存在 → ERROR。
3. 运行结束后的历史记录与结果页包含 `terminal_log_path`（终端输出落盘路径）。

## 命令模板示例

```
make run PROJECT={project} MODULE={module} CASE={case} SEED={seed}
```
