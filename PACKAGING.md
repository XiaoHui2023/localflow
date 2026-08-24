# 打包发布

Linux Release 是 PyInstaller onefile 再经 staticx 封装的 x86_64 单文件。GitHub Actions 在 Ubuntu 16.04/glibc 2.23 基线上构建，以降低目标 Ubuntu 的 glibc 要求。

## 本地打包

在仓库根执行：

```bash
./tools/pack.sh
```

脚本使用独立 `.venv-release`，每次运行 `npm ci` 重建离线前端、重装项目与打包工具，然后清理 `build/`、`dist/` 并重新构建。Linux 需要系统命令 `patchelf`、`file` 和 `ldd`。

| 产物 | 用途 |
| --- | --- |
| `dist/localflow` | 可直接执行的 staticx 单文件 |
| `dist/localflow-<version>-linux-x86_64.tar.gz` | 单文件与 systemd 部署资料 |
| `dist/SHA256SUMS` | 下载完整性校验 |

staticx 固定使用 `--no-compress`：默认压缩形式曾在 Xenial 实测启动 `SIGSEGV`。最终文件仍必须通过静态结构检查和真实任务冒烟。

## 自动 Release

`.github/workflows/release.yml` 在 `main` 每次 push 后运行。全部质量门通过后，工作流把 `v<pyproject version>` 标签移动到当前提交并覆盖更新对应 GitHub Release。

发布前会分别对 `dist/localflow` 和全新解压的压缩包执行代表性冒烟：从仓库外启动服务，完成初始化、管理员登录、提交 shell 任务、等待成功并读取日志。只运行 `--help` 不能发布。

版本号来自 `pyproject.toml`。需要保留一个不可移动的历史版本时，应先提升版本号再推送。
