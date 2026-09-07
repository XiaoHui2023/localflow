# 仿真工作台、配置资源与大日志闭环

## 用户反馈自然复现

基线 `bc27e509` 上从公开 HTTP 入口运行 `tests_v2/test_feedback_20260907.py`，四项全部失败：workspace 同时投影 config/plugins；语义诊断令自由保存返回 422；验证预演不显示编译/运行日志；工作目录测试因旧公共夹具关闭调度器而一直 queued。修正最后一项的测试驱动为真实 scheduler 后，读取相对依赖、创建相对目录、写入 `Path.cwd()` 三个直接副作用断言均证明现源码 cwd 正确，LocalFlow 根没有生成文件。

实际代码缺陷位于验证插件的 `_compile_logs`/`_run_logs`：相对路径在结束判定时由控制器 cwd 解释。现改为入队时相对冻结后的任务工作目录解析为绝对路径，并以不存在的未来日志进行预演测试。

## 自主学习与方案选择

2026-09-07 检索 WAI-ARIA APG、React Aria NumberField、MDN Pointer Events、react-arborist、React Aria Tree DnD、Atlassian Pragmatic DnD、Monaco large-file options、xterm.js、react-window、react-logviewer 与 ripgrep。候选矩阵和复用合同已写入用户级 `modern-web-interface-design/references/operator-interaction-solution-catalog.md`。

选择：显式增减 + 550ms 延迟分级连发；现有 react-arborist 虚拟树 + DnD 与键盘剪切/粘贴；自由原子保存 + 行内语法诊断 + 插件运行诊断；xterm 实时/4MiB 窗口 + 磁盘区间 + 服务端固定块全日志搜索。拒绝滚轮改值、modal 保存门、xterm 从零回放整份大日志以及缺乏维护证据的“千万行”小众组件。

## 失败与降级记录

- Docker daemon：`npipe:////./pipe/dockerDesktopLinuxEngine` 不存在，WSL `docker-desktop` 为 Stopped。本轮按发布门禁不为复现强启本机 Docker；Windows 隔离测试负责源码行为，Ubuntu systemd/浏览器/冻结制品由托管 runner 负责。恢复条件是 Docker Desktop 后台 daemon 正常启动，但它不是发布证明。
- `npm test`：项目没有 test script，明确错误为 `Missing script: "test"`。改用项目声明的 `npm run build`、`test:e2e`/浏览器质量驱动与 Python API/行为测试，没有把该命令计为通过。
- Playwright 直接运行：未设置 `LOCALFLOW_QA_URL`，`page.goto('/')` 报 `Cannot navigate to invalid URL`。改用 `tools/run_browser_quality.py` 启动真实服务并注入 URL；直接失败不计入产品回归。
- Skill quick validator 首次按系统 GBK 解码 UTF-8 失败；一次重试设置 `PYTHONUTF8=1` 后两个用户 Skill 均由官方脚本验证通过。

## 门禁状态

QM-043 至 QM-045 已进入 passed；本地证据由真实 Edge、Python 行为测试、约 25 MiB 跨块检索恒定内存测试和静态交互合同组成。远端发布收据将在托管 Ubuntu 工作流完成后绑定源提交、workflow、Release tag、资产 SHA-256 与下载后消费 smoke。
