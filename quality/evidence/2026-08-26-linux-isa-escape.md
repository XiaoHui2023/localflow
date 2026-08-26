# Linux `Illegal instruction` 发布逃逸

## 失败基线

- 用户从 GitHub Release 解压后执行 `localflow`，进程报告 `Illegal instruction`。
- 旧发布流程在 Ubuntu 16.04/glibc 2.23 容器内生成 PyInstaller 主体，却回到 Ubuntu 24.04
  runner 安装 wheel 版 StaticX 并二次封装。最终制品原生 smoke 只运行在新 runner。
- 旧制品在本机 QEMU 的 `qemu64`、`Nehalem`、`SandyBridge`、`Haswell-noTSX`、`phenom`、
  `core2duo` 与 `Opteron_G1` 模型均能执行 `--help`，因此本轮没有伪称已复现用户目标机的
  精确 SIGILL 地址。目标机 CPU/虚拟化 CPUID/内核仍是待用户用新制品复验的边界。

逃逸分类为 `lineage_escape + oracle_escape`：旧基线只约束了中间物，最终封装阶段重新引入了
未受该基线约束的宿主环境；最终门又只在同一台新 runner 上执行。

## 成熟实现对照与资料

| 路线 | 本地/上游证据 | 优点 | 缺点 | 决定 |
| --- | --- | --- | --- | --- |
| 不使用 StaticX | gitmail 在 Ubuntu 16.04 只构建 PyInstaller | 链路最短 | 不满足 LocalFlow 已确定的静态单文件发布合同 | 拒绝 |
| 同基线源码构建 StaticX | drawclock 在 Ubuntu 16.04 安装 musl，并用 `--no-binary=staticx` 源码构建 | bootloader、加载器与主体共享基线 | 构建稍慢，需要编译工具链 | 采用 |
| 新宿主 wheel StaticX 二次封装 | LocalFlow 旧流程 | 新 `objcopy` 容易获得 | 破坏最终制品谱系，宿主加载器不再受旧基线约束 | 拒绝 |
| Debian 11 等中间 finalizer | StaticX 问题 #205 表明 binutils 2.35.2 可处理预编译 bootloader | 可规避旧 objcopy 问题 | 仍需证明加载器来源，不能自动继承 Ubuntu 16.04 基线 | 本项目拒绝 |

主资料为 StaticX 上游问题
[`#205 Older objcopy mangles bootloader built with musl`](https://github.com/JonathonReinhart/staticx/issues/205)：
旧 `objcopy` 处理新系统预编译 bootloader 会损坏 ELF，上游给出的规避方式是从源码安装
StaticX。本轮使用 GitHub API 回读完整问题正文；通用网页搜索两次没有返回可用结果，Find Skills
查询 `pyinstaller staticx linux compatibility` 也没有直接相关 skill，因此以官方问题、本地成功
项目和真实制品实验降级完成研究，没有安装低相关 skill。

## 修复与 Oracle

1. `tools/ci_pack_ubuntu16.sh` 在 Ubuntu 16.04 内安装 musl 工具链，并设置
   `PACK_STATICX_SOURCE_BUILD=1`。
2. `tools/pack.sh` 把虚拟环境加入 `PATH`，从 sdist 构建 StaticX，保留
   `dist/localflow.pyinstaller` 作为不可覆盖的显式中间边界，再调用 finalizer。
3. GitHub workflow 删除 Ubuntu 24.04 StaticX finalization。
4. `tools/check_linux_compatibility.sh` 对最终文件检查静态 ELF、原生启动，并在 QEMU 的
   `qemu64`、`core2duo` 与 `Opteron_G1` 上执行 `--help`；缺 QEMU、超时、SIGILL 或非零退出均阻断。
5. `tests_v2/test_quality.py` 把“恢复延后封装、恢复 wheel、删除任一 CPU 模型或覆盖输入路径”
   固定为可拒绝的工作流 mutant。

## 受控迭代

- 轮次 1：StaticX sdist 找不到 `scons`，错误为
  `FileNotFoundError: No such file or directory: 'scons'`。原因是虚拟环境脚本目录未加入 `PATH`；
  修复所有者为 pack 环境，不放宽源码构建门。
- 轮次 2：finalizer 报 `PyInstaller input is missing: dist/localflow`。原因是旧 finalizer 的输出清理
  会删除同名输入；修复为显式 `.pyinstaller` 中间文件，并增加输入不得等于输出的 fail-closed 检查。
- 轮次 3：Ubuntu 16.04 全链构建成功；最终静态 ELF 声明 GNU/Linux 2.6.32，原生功能 smoke、
  三个旧 CPU 模型、SHA256SUMS 与全新解压包功能 smoke 均通过。

## 声明边界

当前证据证明候选制品的同基线构建谱系及所列 QEMU CPU 模型启动，不证明任意 x86-64 物理机或
任意虚拟化 CPUID 均兼容。只有 GitHub Release 完成、重新下载文件复验，并由用户在原服务器运行
新制品后，才能关闭本次目标环境观察项。
