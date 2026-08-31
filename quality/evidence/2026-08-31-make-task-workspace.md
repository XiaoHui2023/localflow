# Make 命令与任务工作区闭环

## 失败基线

- `make all --case ...` 把领域参数错误地当成 Make 选项，GNU Make 会拒绝；插件原先在模板缺少变量时自动追加 `--case`/`--seed`，无法兼容任意工具。
- 任务与运行分属一级页面，查看状态与发起任务需要往返；运行页在全屏时也独占全部宽度。

## 冻结合同

- 验证命令显式包含 `${case}` 和 `${seed}`。插件不猜参数名；GNU Make 示例为 `make all CASE=${case} SEED=${seed}`，其它命令使用自己的语法。
- 字符串保留 `/bin/sh -lc`，列表保留精确 argv。任务入队前冻结变量；执行器先进入配置的 `working_directory`，再启动命令，并把最终命令与实际工作目录写入任务输出。
- 主导航只保留任务、终端、设置。运行是任务页内默认折叠的一键面板；宽屏并排，中窄屏置顶并逐级堆叠，折叠状态和运行上下文限当前浏览器标签页保存。

## 学习与取舍

使用 GNU Make 官方命令行变量、VS Code 可调整工作台、WAI-ARIA disclosure 和 MDN 响应式容器资料。Find Skills 检索了 Make、响应式 split-pane 与 React dashboard 候选；没有安装第三方技能，因为现有项目技能与官方资料已经覆盖本次窄合同，引入未审查包不会提高证据等级。网络检索和资料读取均成功，没有静默降级。

## 自动判定

- Python：显式占位符正反例、字符串/列表规范化、配置诊断、递增 seed 和最终命令日志。
- Ubuntu：systemd 目标测试把 LocalFlow 根和仿真工程建成两个独立目录，Makefile 只存在于工程目录；断言 recipe 读取的 `$PWD` 等于配置工作目录、`CASE`/`SEED` 正确到达且输出包含最终命令。任何误用 LocalFlow 根目录的实现都会直接找不到 Makefile。
- 浏览器：管理员导航、开合语义、任务与运行同时可见、状态保留、1440/760/390px 几何、无水平溢出、axe 与 Chrome/Firefox Release 旅程。
