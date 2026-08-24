# 打包与发布工具

## 一键 Linux 静态打包

```bash
./tools/pack.sh
```

每次执行都会先运行 `npm ci` 和前端生产构建。CI 可在宿主机完成前端后设置 `PACK_SKIP_FRONTEND_BUILD=1`，并通过 `PACK_PYTHON` 指定固定的 Python 3.11。

本地修复打包规格后可临时设置 `PACK_SKIP_PYTHON_INSTALL=1` 复用刚建立的发布环境；正式 CI 不使用该开关。

| 产物 | 文件 |
| --- | --- |
| 直接执行 | `dist/localflow` |
| 部署包 | `dist/localflow-<version>-linux-x86_64.tar.gz` |
| 校验 | `dist/SHA256SUMS` |

`ci_pack_ubuntu16.sh` 固定 CI 的 glibc/Python 构建基线。`run_frozen_smoke.py` 对最终单文件与解压文件分别完成服务启动、管理员登录、任务执行和日志断言。

更完整的发布说明见 [PACKAGING.md](../PACKAGING.md)。
