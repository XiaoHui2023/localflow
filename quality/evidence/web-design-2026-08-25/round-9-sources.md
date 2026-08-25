# 第九轮：配置使用态与测试构建刷新

## 研究结论

- JSON Forms 官方把数据 schema 与 UI schema 分开，控件只绑定明确声明的属性，规则还能隐藏或禁用不适用控件。本轮据此把插件契约明确为 `run_fields`：它不是完整配置模型，只是每次运行需要用户决定的最小控件集合。
- React Aria 的 NumberField 文档强调原生数字输入在平台间行为与样式不一致。本轮不新增重型依赖，但把逐 Case 次数限制为独立数字控件，并对复选框、数字框和工具栏控件建立统一几何门禁。
- MDN 明确区分 `no-store` 与 `no-cache`，并说明 `Location.reload()` 等同浏览器刷新。本轮测试环境对 HTML 与 API 返回 `Cache-Control: no-store`，客户端每两秒读取构建修订；变化时调用同源 `location.reload()`。哈希静态资源仍可复用，HTML 不复用。

## 渐进披露决策

| 内容 | 默认表面 | 披露位置 |
| --- | --- | --- |
| 运行时 Case、逐项次数、seed | 使用态直接显示 | 插件 `run_fields` |
| 命令、工作目录、Case 目录、互斥键 | 使用态隐藏 | “修改 YAML” |
| 重命名、删除 | 默认隐藏 | 资源树省略号菜单 |
| 插件说明、开发协议、状态映射 | 网页不重复 | `plugins/README.md` 与 `docs/plugins.md` |
| 构建更新 | 无按钮、无提示打扰 | 修订变化自动刷新 |

## 质量闭环

- Edge 故障注入把修订端点从 `qa-a` 改为 `qa-b`，断言主文档至少导航两次。
- Case 钩子断言只返回一层目录和文件 stem，不返回目录中的更深文件。
- Edge 断言配置专属字段不出现在使用态，每个 Case 有独立次数输入。
- 工作台操作按钮高度限定为 34–38px；资源树图标动作使用 32px 令牌。
- 四态资源树继续用形状、颜色与可访问名称共同传意。

## 来源

- JSON Forms，UI Schema / Controls / Rules：https://jsonforms.io/docs/uischema/
- React Aria，useNumberField：https://react-spectrum.adobe.com/react-aria/useNumberField.html
- MDN，Cache-Control：https://developer.mozilla.org/en-US/docs/Web/HTTP/Reference/Headers/Cache-Control
- MDN，Location.reload：https://developer.mozilla.org/en-US/docs/Web/API/Location/reload
