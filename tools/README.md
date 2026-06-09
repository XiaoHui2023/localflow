# 打包工具

## 一键打包（PyInstaller；Linux 再 staticx）

在仓库根执行（使用根目录 `.venv`，无则创建）：

### Linux / macOS / Git Bash

```bash
./tools/pack.sh
```

### Windows

```bat
tools\pack.bat
```

默认构建 `app` 入口。只打该入口时可显式传入子命令（两脚本一致）：

```bash
./tools/pack.sh app
```

```bat
tools\pack.bat app
```

若 `frontend/dist` 不存在，脚本会先执行 `npm install` 与 `npm run build`。

产物写入 `dist/`：

| 目标 | 产物 |
| --- | --- |
| `app` | `app` / `app.exe` |

| 平台 | 脚本 | staticx |
| --- | --- | --- |
| Linux | `pack.sh` | 需要系统 **patchelf** |
| macOS 等 | `pack.sh` | 跳过 |
| Windows | `pack.bat` | 跳过 |

更完整的说明见仓库根目录 [PACKAGING.md](../PACKAGING.md)。
