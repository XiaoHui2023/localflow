# Round 7 迭代记录

## 基线

`round-7-baseline-settings.png` 显示 112px 全高侧栏；设置页时间区域同时有图标、标题、说明、粗体时间和输入。配置读取只投影 `plugin_loaded`，不能解释普通文件、公共片段与具体错误。

## 候选实现

- 导航轨道 124px 保持内容位置，可见容器改为 100px 宽、内容高度、左上 12px 的安静卡片；入口 40px。
- 时间区域压缩为日期+时分秒的 `role=timer` 与带标签的 `datetime-local`；校准仍在有效输入变化后自动提交。
- 配置库使用 `python-library-configlib` 组合，先执行 include 路径闭包检查；诊断结果区分 `generic`、`fragment`、`task`。
- 内置插件声明 `required_common_fields` 与 Pydantic `config_model`；网页只为 `runnable` 配置显示“使用”。

## 闭环门禁

- Microsoft Edge 1/1 通过：可见导航高度不超过 300px，六个入口均不小于 40px；live timer 跨秒变化，时间区域没有第二次确认按钮。
- 公共片段显示“公共配置”且没有“使用”；任务配置显示“有效”并可提交。
- axe WCAG A/AA serious/critical 为 0；390px 视口无横向溢出。
- 七张截图及本轮源码摘要写入 `quality/evidence/browser/browser-receipt.json`。
- Python 成功、失败和越界导入故障样本通过；外部无效文件 GET 返回原文与诊断，不产生 500。
- API 页以单个默认收起的“调用说明”集中解释密钥权限、每请求重读、nonce/generation、规范串、轮换与 403 重试；端点列表不重复协议文字。

## 视觉复核

`admin-settings-compact-light.png` 中导航可见容器在 API 入口后结束；时间卡只保留日期时间和“时间校准”输入。`admin-config-explorer-dark.png` 中配置路径、插件名和“有效”徽标同处文件上下文，资源树可见 `shared/task-defaults.yaml`，没有第二个插件选择器。

`round-7-api-guide.png` 复核 API 页：默认入口只有“调用说明”，展开后四步签名闭环与二级“Python 最小示例”按需显示；下面直接进入端点分组，没有页面标题、版本摘要或重复密钥卡片。
