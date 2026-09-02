# 任意验证命令、工作目录与左侧运行入口（2026-09-02）

## 失效基线

- 发行模板把 `${case}` 与 `${seed}` 同时存在作为运行条件；仓库根的运行插件则在缺失时猜测并追加 `--case`、`--seed`。两条路线都拒绝了“用户命令可以完全不消费 Case/seed”的合同。
- 字符串命令规范化为 `/bin/sh -lc`。`-l` 会启用登录 shell startup files；其中的 `cd` 可以覆盖执行器先前设置的 cwd。
- systemd Make 测试只比对日志中的 `PWD`，没有以相对 `mkdir`/文件写入证明真实副作用位置，也没有断言 LocalFlow 根不存在同名副作用。
- 运行面板开关是任务区右上角 34px 的纯图标，并在展开后换到面板内部另一位置。

## 成熟方案对照

- Python `subprocess` 明确规定 `cwd` 在执行子程序前改变目录；其 POSIX shell 等价形式使用 `/bin/sh -c`。
- systemd `WorkingDirectory=` 为执行进程设置目录，瞬态服务支持该属性；PTY supervisor 仍需在最终 exec 前再次 `chdir`，使职责边界自证。
- GNU Make 启动后以 `CURDIR` 表示当前工作目录；每条 recipe 使用新的子 shell，因此测试必须观察相对文件系统副作用，不能只观察一行输出。
- W3C disclosure 采用带可见状态的按钮；Primer Action List 把带图标、文字和分组分隔的动作放在侧栏。本项目不为一个开关新增运行时组件库，而是复用原生按钮、现有图标和设计令牌。

参考资料：

- [Python subprocess cwd 与 shell 语义](https://docs.python.org/3/library/subprocess.html#popen-constructor)
- [systemd.exec WorkingDirectory 源文档](https://github.com/systemd/systemd/blob/main/man/systemd.exec.xml)
- [systemd transient settings](https://github.com/systemd/systemd/blob/main/docs/TRANSIENT-SETTINGS.md)
- [GNU Make recipe execution](https://www.gnu.org/software/make/manual/html_node/Execution.html)
- [GNU Make recursion 与 CURDIR](https://www.gnu.org/software/make/manual/html_node/Recursion.html)
- [Bash login shell startup files](https://www.gnu.org/software/bash/manual/html_node/Bash-Startup-Files)
- [Ubuntu dash invocation](https://manpages.ubuntu.com/manpages/jammy/man1/sh.1.html)
- [W3C disclosure pattern](https://www.w3.org/WAI/ARIA/apg/patterns/disclosure/)
- [Primer Action List](https://primer.github.io/design/components/action-list/)

## Find Skills 与候选处理

执行了 `python subprocess working directory cwd testing`、`systemd transient service WorkingDirectory`、`GNU Make current working directory relative paths` 和 `pytest process cwd integration testing` 四组检索。发现 systemd、Make 与 pytest 候选，但均未安装：项目已有更窄的 LocalFlow configuration/operations/plugin Skills，且本轮事实由 Python、systemd、GNU 与 W3C/Primer 官方资料直接覆盖；第三方 Skill 不会提高运行时或验证证据等级。

## 实现与门禁

- 删除 verification 的占位符强制检查和猜测参数追加；字符串/argv 分别覆盖“不使用、只用 Case、只用 seed、同时使用”。
- 字符串命令改为非登录 `/bin/sh -c`；日志显示逻辑兼容数据库中尚未执行的旧 `-lc` 快照。
- subprocess、systemd Make 和冻结制品都创建相对目录/marker：目标目录必须存在 marker，LocalFlow 根必须不存在同名目录。
- 左侧侧栏固定显示“运行配置”按钮，开合共用同一位置，并保留 `aria-expanded`/`aria-controls`。

## 本轮验证结果

- 能力专题机器合同：`PASS localflow-working-directory-integrity`。
- 变更范围 Ruff 检查：通过。
- 完整 `tests_v2`：通过；Windows 条件下的 POSIX 专属用例按既有标记跳过。
- Vite 生产构建：通过；保留既有大 chunk 警告。
- Edge 完整流程与当前 Chromium/Firefox 兼容流程：通过；浏览器 receipt、截图、资源预算与源码哈希已刷新。
- Chrome 84 固定版本交互本身通过并写出零 boot/console error 证据，但 Docker 在随后删除临时容器时连续两次未收到退出事件；Firefox 78 因该清理阻塞未进入本轮复验。
- 当前主机是 Windows，无法在本轮直接执行 Ubuntu user systemd、Linux 冻结制品及 cgroup 门禁；正式 Release 未获授权，也未提交或发布。

Docker 的可验证失败为 `could not kill container: tried to kill container, but did not receive an exit event`；`docker desktop restart --timeout 120` 随后以 `context deadline exceeded` 失败，启动与状态查询也无法在有界等待内完成。恢复条件是 Docker Desktop/WSL 后端恢复健康，或改用可用 Ubuntu 质量机，然后从最终源码重跑固定浏览器、systemd、cgroup 与冻结制品门禁。工作目录历史现场的原运行数据库和日志在本机不可读取（SQLite：`unable to open database file`，对应日志不存在），因此无法还原用户当时那一个具体任务；替代证据是源码路径审计、非登录 shell 修复，以及目标目录正向 marker 与 LocalFlow 根负向 marker 的副作用测试。若要逐字复核旧任务，还需要提供其实际运行根或任务数据库与日志。

作为降级核查，曾在 Windows 直接执行 `tests_target/test_localflow_systemd_executor.py`；8 项全部失败，日志显示 systemd 任务无法启动，且参数化名 `stop:1:signal` 在 Windows 触发 `WinError 123`。这些用例的合同就是 Linux systemd/PTY/cgroup，故该结果只证明当前主机不能替代目标环境，不作为产品失败或通过。测试产生的临时目录由 pytest 管理，没有修改项目运行数据。

因此本轮只声明源码、Windows subprocess 与已完成浏览器范围通过；Ubuntu systemd、Linux 冻结制品、Firefox 78 和正式附件仍是后续 Linux 发布门禁，不能由本地结果替代。
