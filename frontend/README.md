# 前端

React + Vite 单页应用，`base` 为相对路径 `./`，API 请求使用 `/api/...` 相对路径。

## 本地开发

终端一（仓库根，默认端口 8765 供 proxy 使用）：

```bash
cd src/app_main
python __main__.py --port 8765
```

终端二：

```bash
cd frontend
npm install
npm run dev
```

浏览器打开 Vite 提示的地址；`/api` 由 `vite.config.js` 代理到 `http://127.0.0.1:8765`。

## 生产构建

```bash
cd frontend
npm install
npm run build
```

产物在 `frontend/dist/`，由 Python 服务或 PyInstaller 打包一并发布。
