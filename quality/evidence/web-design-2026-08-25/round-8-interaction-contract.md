# 交互便利性质量合同

## 用户可观察结果

| 场景 | 预算 | 权威证据 | 失败变体 |
| --- | --- | --- | --- |
| 使用有效配置 | 从文件激活到运行表单 1 次操作 | Edge DOM 中 `mode=use` | 默认打开编辑模式 |
| 诊断无效配置 | 从文件激活到错误详情 1 次操作 | Edge 中 `.config-diagnosis` 可见 | 只染色、不展示错误 |
| 保存成功反馈 | 不遮挡；5 秒内消失 | computed `position: static` 与定时断言 | 固定右上角绿色弹窗 |
| 配置状态识别 | 图标、颜色、可访问名称三重线索 | 四种 `data-config-state` 与 aria-label | 全部同图标或只用颜色 |
| 常用界面降噪 | 0 个手动刷新/扫描按钮；0 个重复诊断徽标 | Edge DOM 缺席断言 | 增加冗余按钮或标题 |
| 小屏可用性 | 390px 无水平溢出；axe serious/critical 为 0 | Edge 几何与 axe 扫描 | 固定宽度导致溢出 |

## Oracle 边界

生产者是 Vite 构建后的前端与真实 HTTP 服务；验证者是 Edge/Playwright 对 DOM、计算样式、几何和计时结果的读取。浏览器收据绑定前端源码、测试源码和七张截图的 SHA-256，质量门同时要求四条交互断言存在。

该合同证明已声明的配置浏览、诊断和运行路径在 Edge 桌面与 390px 视口满足预算；不证明所有辅助技术、语言、浏览器版本和任意视口均无缺陷。

## Oracle 故障注入

质量检查器必须拒绝缺少 `explorer-four-state-decoration`、`opened-invalid-inline-diagnosis`、`config-opens-in-use-mode` 或 `nonblocking-expiring-status` 任一断言的浏览器收据。成功基线必须接受；删除断言的副本必须非零退出，且不得修改正式收据。
