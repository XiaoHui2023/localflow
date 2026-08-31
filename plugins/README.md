# LocalFlow 插件目录

服务自动加载本目录中的受信任 `*.py` 插件；保存后新任务使用新代次，已经提交的任务继续使用其插件快照。

- 插件的完整使用、字段合同、API 示例与开发流程见 [`../docs/plugins.md`](../docs/plugins.md)。
- 配置文件、变量和 configlib 显式导入见 [`../docs/configuration.md`](../docs/configuration.md)。
- HMAC 签名及配置、发现、运行 API 见 [`../docs/api.md`](../docs/api.md)。

配置必须在顶层声明 `plugin`。新增插件应提供 `config_model`、与 `run_fields` 完全对应的 `input_model`、状态映射以及可直接提交的 `example`/`api_inputs`。`run_fields` 只公开用户每次运行确实需要改变的值，命令、工作目录和 Case 目录等稳定内容留在配置文件中。普通任务返回 `TaskCreate`；需要跨请求、重启仍唯一递增的自动值时返回 `TaskDraft` 和 `DeferredValue`，由核心在入队事务中分配，禁止插件修改已排队任务。
