# 网页秘钥登录闭环

## 合同

- `127.0.0.1`、远端地址和随机端口均不构成管理员身份。
- 未登录设置页只呈现主题和一行秘钥登录；成功后登录控件消失，不增加“已登录”等状态元素。
- 登录秘钥来自 `secrets/web-admin-key`，服务不打印、不返回、不持久化到浏览器；程序 API 继续独立使用 `secrets/api-key`。
- 浏览器会话使用由当前网页秘钥签名的 `HttpOnly; SameSite=Strict` cookie。刷新与服务重启后可恢复并续期；修改网页秘钥撤销旧会话。
- Ubuntu 的 `secrets` 为 `0700`，两个秘钥文件为 `0600`，权限不合格时拒绝启动。

## 闭环判据

| 风险 | 自动检查 |
| --- | --- |
| 回环地址绕过登录 | `test_loopback_is_not_administrator_identity` |
| 错误秘钥被接受 | `test_web_key_session_survives_service_restart_until_key_changes` |
| 重启丢失会话 | 同一测试使用两个应用实例复用 cookie |
| 修改秘钥后旧 cookie 仍有效 | 同一测试修改文件后断言 `401` |
| 旧版秘钥文件升级丢失 | `test_legacy_admin_key_is_migrated_without_changing_value` |
| 秘钥权限或文件类型不安全 | `test_secret_permissions.py` 与安全测试 |
| 登录界面冗余、溢出或不消失 | Edge E2E 的桌面/390px 截图、DOM 和无横向溢出断言 |

最终结果以本次 `pytest`、Edge 浏览器回执、Linux Release 构建和下载产物复验为准。

## Edge 资源采样说明

加入匿名登录旅程后，当前 Edge 在真实登录、刷新以及加载 Monaco/xterm 的完整旅程中，连续两轮、每轮前后各两次强制 GC 后均报告 5 个 document 上下文，旧预算为 4。预算精确调整为 5；DOM 节点、监听器、JS 堆、CPU、后台请求和 WebSocket 上限均未放宽，避免用单个聚合计数掩盖资源增长。
