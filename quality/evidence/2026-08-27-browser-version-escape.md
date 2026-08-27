# 浏览器版本兼容性逃逸

## 撤销

上一轮只在最新版 Ubuntu Chrome 和 Firefox 中运行真实旅程，却把结果表述成 Ubuntu Chrome、Firefox 均已解决。用户用原环境再次复现后，该表述撤销。根因是覆盖矩阵只有浏览器品牌，没有浏览器版本与生成 bundle 类型。

## 直接反证

- Vite 8 的默认生产目标对应约 2023 年浏览器。
- 旧发布 bundle 中直接保留 `Object.hasOwn`、`Array.prototype.at` 与 `import.meta.resolve`。
- `Object.hasOwn` 在 Chrome 92、Firefox 91 及更早版本不存在；最新版门禁无法观察这个失败面。

## 修复合同

- 使用 Vite 官方 `@vitejs/plugin-legacy`，目标为 Chrome 79、Firefox 78 及以上。
- 关闭 modern chunk，只输出 SystemJS 兼容 bundle和按实际用法生成的 polyfill，避免模块能力探测本身产生控制台异常。
- 在所有应用脚本前安装有界启动错误收集器，记录脚本/资源错误和未处理 Promise 拒绝。
- 最新 Chrome/Firefox 继续跑完整任务、复制和终端旅程；固定 Chrome 84 与 Firefox 78 额外直接跑根节点、秘钥登录和 Monaco 动态资源旅程。
- Release 只有同时产生四份浏览器收据才能发布。

## 本轮实际截获的缺陷

- 兼容 bundle 的内联 SystemJS 启动器最初被严格 CSP 拦截；服务端现在从最终 `index.html` 精确计算内联脚本 SHA-256 并写入 CSP。
- Monaco 在 Chrome 84 中使用正则 `d` 标志，直接产生 `Invalid flags supplied to RegExp constructor 'd'`；构建阶段对该已知模块做具备上游变更拒绝机制的等价变换。
- Monaco 在 Firefox 78 中要求 `WeakRef`，直接产生 `ReferenceError: WeakRef is not defined`；首屏兼容层为缺少该能力的浏览器提供有界用途的强引用退化实现。
- 配置事件流曾从事件 0 重放历史，并在配置重命名时用旧路径再次读取产生 404；新连接默认从最新游标开始，重连遵循 `Last-Event-ID`，前端在同步前重新确认文件仍存在。

## 通过证据

- 当前 Edge 全旅程：2/2 通过。
- 当前 Chromium 与 Firefox 发布兼容旅程：2/2 通过。
- Chrome `84.0.4147.105`：根页面、秘钥登录、运行页、`server.yaml` 和 Monaco 加载通过，启动错误和严重控制台错误均为 0。
- Firefox `78.0.2`：相同旅程通过，启动错误为 0；该版本 Selenium 不提供浏览器日志端点，因此以首屏错误收集器和语义断言代替，收据明确记录 `console_log_supported=false`。

## 剩余边界

Chrome 79–83 由相同的声明式编译目标覆盖，但当前可获取的 Selenium 官方 Chrome 镜像最早为 84，因此直接旧浏览器证据从 Chrome 84 开始。若目标主机版本低于 84，必须以实际版本追加目标机复验，不能把编译目标写成真机通过。
