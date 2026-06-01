# 打包发布

在可访问 PyPI 与 npm 的机器上于仓库根执行一键脚本；Linux 上会在 PyInstaller onefile 之后再做 staticx，得到更易在旧 glibc 环境运行的自解压单文件 `dist/app`。

## 一键打包

### Linux / macOS / Git Bash

```bash
./tools/pack.sh
```

### Windows

```bat
tools\pack.bat
```

脚本会创建或复用根目录 `.venv`，安装项目依赖，在缺少 `frontend/dist` 时执行 `npm run build`，再调用 PyInstaller。详细参数见 [tools/README.md](tools/README.md)。

| 命令 | 产物（`dist/`） |
| --- | --- |
| `./tools/pack.sh` 或 `app` | `app` |
| `tools\pack.bat` | `app.exe` |

Windows 产物为 `app.exe`，无 staticx 步骤。

## Linux staticx

在 Linux 上，`tools/pack.sh` 对 ELF 产物再运行 **staticx**，需要系统已安装 **patchelf**（例如 `sudo apt install patchelf`）。**macOS** 当前跳过 staticx，仅保留 PyInstaller onefile。

## Spec 文件

- `app.spec` → 可执行文件名 `app`

## 兼容边界

单文件可执行文件的系统兼容性取决于**执行打包的那台机器**。要支持较旧的 Linux 发行版，应在 glibc 基线不高于目标环境的系统上构建，并在目标机实测 staticx 产物。
