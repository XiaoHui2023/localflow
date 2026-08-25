# 配置诊断样例

将任一文件复制到运行目录的 `config/` 后，资源树会立即显示红色错误图标；打开文件可看到具体诊断，并且不能运行。

- `missing-field.yaml`：缺少验证插件要求的 `case_directory`。
- `wrong-type.yaml`：`command` 和 `labels` 的类型错误。
- `syntax-error.yaml`：YAML 语法错误。

修正文件并保存后，资源树会自动恢复为对应的正常图标。
