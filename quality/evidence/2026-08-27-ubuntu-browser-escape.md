# Ubuntu 浏览器兼容性逃逸

## 撤销

旧门禁只让 Windows Edge 通过真实局域网旅程，却把网页可用性结论扩张到 Ubuntu 浏览器。用户在 Release 上报告网页控制台异常后，相关跨平台兼容声明撤销；分类为执行范围小于声明范围的 claim/execution escape。

## 新合同

- Release 流水线先构建最终 StaticX 二进制，再在同一个 Ubuntu runner 上启动该二进制。
- Playwright 按官方浏览器项目机制分别运行稳定 Google Chrome 与其匹配的 Firefox；浏览器与被测服务使用打印出的局域网 HTTP 地址，不使用 localhost 安全上下文特例。
- 两种浏览器都必须实际渲染 React 根节点，并完成秘钥登录、Monaco 配置、任务创建与详情复制、xterm WebSocket 终端、温和中止和设置页访问。
- `pageerror`、console error 和非预期请求失败均阻断发布。配置页切换时关闭已成功建立的 SSE 会由浏览器报告 ABORT；门禁只在此前观察到 `/events` 真实 200 且失败原因为 ABORT 时接受，不能屏蔽其它 SSE 或网络故障。
- 每个浏览器写出独立版本、操作系统、来源提交、访问地址、控制台错误和请求失败收据及截图；缺任一文件时发布工作流失败。

## 反证

- 删除 Chrome 或 Firefox 项目，结构测试失败。
- 把最终二进制替换为源码服务，结构测试检查 `--binary dist/localflow` 并失败。
- 页面根节点为空、登录失败、Monaco/xterm 不可见、复制内容不符、控制台异常或普通资源失败，Playwright 旅程失败。
- 将任意请求失败都作为正常关闭忽略不会通过：豁免同时受 `/api/v1/events` 精确路径、ABORT 类别和至少一次 200 响应约束。
