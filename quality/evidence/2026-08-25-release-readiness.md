# Release 就绪性审计

## 当前结论

测试阶段已经结束，发布授权已生效。`.github/workflows/release.yml` 保持 `main` push 的滚动发布设计；`build` 完成源码门禁、Ubuntu 16.04 PyInstaller、Ubuntu 24.04 staticx、最终单文件 smoke 和全新解压包 smoke 后，`publish` 才能移动版本 tag 并更新附件。当前提交的外部 `Actions run → tag/source SHA → Release 下载 → 摘要 → 解压后 smoke` 回执尚待取得，因此质量指标 `QM-013` 暂时保持 `partial`；取得可复验回执后必须回写本文件并再次完成同一发布闭环。

## 本轮发现与修复

- 首次远端运行 `32867398244` 在源码门禁失败。匿名 job 日志接口返回 HTTP 403，本机 Git 凭据的安全提取被执行策略拒绝；干净 Python 3.12 Linux 容器复现出 wheel 遗漏根层 `starter_root/cases/smoke.case`。包数据现覆盖 `cases/*`，并新增逐文件覆盖回归测试，后续远端运行与下载复验仍须闭合。
- 干净 Linux 复验还发现终端测试把 Ctrl+C 错误限定为“读取到字节 3”；POSIX PTY 的正确行为是行规程触发 `SIGINT`。测试子进程现同时处理 POSIX 信号与 Windows 字节路径，并以统一的 `control-3` 用户语义作为预言。
- workflow 原先检查已移除的 `heartbeat.yaml` 和 `heartbeat.py`，会在当前包正确生成后反而失败。已改为核对随机数、验证仿真、结果标记、交互退出四份 YAML、四个脚本、四个插件及 API/配置/插件文档。
- `tests_v2/test_quality.py` 现在拒绝旧 heartbeat 名称，并要求 workflow 与当前 starter 清单一致。
- 初始化插件 README 原先仍写“插件页”“修改 YAML”、过时的密钥能力和陈旧文档入口；已与当前“运行”页、HMAC 完整程序 API 和机器插件合同同步，并由初始化测试拒绝旧文案。
- 在全新审计根执行 `localflow init` 后，实际得到四份任务配置、四个脚本、`command/interactive/marker/verification` 四个插件，插件诊断为空；审计根已清理。

## 工具与资料状态

| 来源 | 状态 | 用途/结论 |
| --- | --- | --- |
| 本机 `github-release`、`python-pack-github-release`、frozen release quality gate | 已完整阅读 | 滚动 tag、最终 frozen smoke、解压消费门和发布后下载复验 |
| `npx skills find "github actions release"` | 已运行，未安装候选 | 找到 `github-actions`、`configure-workflows` 等；本机技能合同更完整，第三方说明与脚本未审查，故不采用 |
| `npx skills find "pyinstaller staticx"` | 已运行，未安装候选 | 命中结果稀少且没有比本机 staticx 门更完整的候选 |
| `npx skills find "ci workflow validation"` | 已运行，未安装候选 | 找到 CI/workflow 技能，仅作发现记录 |
| GitHub Actions workflow syntax | 已阅读 | `contents: write` 允许创建 Release；其它未声明权限为 none |
| `actions/checkout`、`setup-node`、`upload-artifact`、`download-artifact` 主仓库 | 已阅读 | 当前 workflow 使用的 v7/v7/v7/v8 与 2026-08 官方示例一致 |
| `softprops/action-gh-release` 主仓库 | 已阅读 | v3 是 Node 24 主线；已有 Release 会被更新；`.zip.sha512` 的 v3.0.0 社区失败不命中当前附件类型 |
| `rhysd/actionlint:latest` 本机镜像 | 已实际运行 | 以仓库只读挂载检查全部 workflow，退出码 0、无诊断；镜像已存在，本轮未下载 |

官方入口：

- https://docs.github.com/en/actions/reference/workflows-and-actions/workflow-syntax
- https://github.com/actions/checkout
- https://github.com/actions/setup-node
- https://github.com/actions/upload-artifact
- https://github.com/actions/download-artifact
- https://github.com/softprops/action-gh-release
- https://github.com/rhysd/actionlint

## 已通过与未证明

本地已证明：workflow YAML 可被 actionlint 接受；当前 Action 主版本存在；源码测试 60/60；当前 starter 初始化和插件装载成功；历史 Ubuntu 24.04/systemd 目标门 10/10；最终静态包工作流具有真实 frozen/解压 smoke 步骤。

本地不能提前证明：GitHub 托管 runner 能完成本次网络下载与构建、仓库 `GITHUB_TOKEN` 实际允许强制更新 tag、Release 资产已上传且可重新下载、远程资产摘要与 build artifact 一致。当前恢复条件已经满足，将由实际 workflow 回执和下载后 smoke 闭合；在取得这些证据之前不得把 `QM-013` 提升为 `passed`。
