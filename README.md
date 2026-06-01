# masterslave

面向离线 Ubuntu 的本地 Web 工具：浏览器访问 React 页面，同一进程内的 Python 标准库 HTTP 服务提供 `/api` 与静态资源。可打包为 Linux 单文件 `app`，启动后监听 `0.0.0.0`，默认由系统分配空闲端口。

## 命令行参数

入口：`python src/app_main/__main__.py`（或打包后的 `./app`）

| 长参数 | 短参数 | 类型 | 默认值 | 说明 |
| --- | --- | --- | --- | --- |
| `--port` | | 整数 | `0` | 监听端口；`0` 表示随机空闲端口 |

示例：

```bash
python src/app_main/__main__.py
python src/app_main/__main__.py --port 8000
./dist/app --port 8000
```

启动后终端会打印本机与局域网访问地址。

## 开发与发布

| 阶段 | 前端 | 后端 |
| --- | --- | --- |
| 开发 | `cd frontend && npm run dev`（代理 `/api`） | `python src/app_main/__main__.py --port 8765` |
| 发布 | `npm run build` | `./tools/pack.sh` → `dist/app` |

前端说明见 [frontend/README.md](frontend/README.md)。打包说明见 [PACKAGING.md](PACKAGING.md)。

## HTTP 接口

| 路径 | 方法 | 说明 |
| --- | --- | --- |
| `/api/status` | GET | 服务与任务运行状态 |
| `/api/config` | GET | 当前配置 |
| `/api/run` | POST | 启动任务（JSON 体，占位） |
| `/api/progress` | GET | 任务进度 |
| `/api/result` | GET | 任务结果 |

静态页：`/`、`/assets/...` 来自 `frontend/dist/`。
