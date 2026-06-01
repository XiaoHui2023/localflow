import { useCallback, useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router-dom";
import {
  fetchConfig,
  fetchProgress,
  fetchResult,
  fetchStatus,
  postRun,
} from "./api.js";

function HomePage() {
  const [status, setStatus] = useState(null);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      setStatus(await fetchStatus());
    } catch (err) {
      setError(String(err));
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  return (
    <section className="card">
      <h1>masterslave</h1>
      <p>本地 Web 工具（React + Python 标准库 HTTP）</p>
      <button type="button" onClick={load}>
        刷新状态
      </button>
      {error ? <p>{error}</p> : null}
      <pre>{status ? JSON.stringify(status, null, 2) : "加载中…"}</pre>
    </section>
  );
}

function SettingsPage() {
  const [config, setConfig] = useState(null);

  useEffect(() => {
    fetchConfig().then(setConfig).catch(() => setConfig({ ok: false }));
  }, []);

  return (
    <section className="card">
      <h2>配置</h2>
      <pre>{config ? JSON.stringify(config, null, 2) : "加载中…"}</pre>
    </section>
  );
}

function TaskPage() {
  const [progress, setProgress] = useState(null);
  const [result, setResult] = useState(null);

  const refresh = useCallback(async () => {
    setProgress(await fetchProgress());
    setResult(await fetchResult());
  }, []);

  const start = async () => {
    await postRun({ action: "demo" });
    await refresh();
  };

  useEffect(() => {
    refresh().catch(() => {});
  }, [refresh]);

  return (
    <section className="card">
      <h2>任务</h2>
      <button type="button" onClick={start}>
        启动任务（占位）
      </button>
      <button type="button" onClick={refresh}>
        刷新进度
      </button>
      <h3>进度</h3>
      <pre>{progress ? JSON.stringify(progress, null, 2) : "—"}</pre>
      <h3>结果</h3>
      <pre>{result ? JSON.stringify(result, null, 2) : "—"}</pre>
    </section>
  );
}

export default function App() {
  return (
    <main>
      <nav>
        <NavLink to="/" end>
          首页
        </NavLink>
        <NavLink to="/task">任务</NavLink>
        <NavLink to="/settings">设置</NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/task" element={<TaskPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </main>
  );
}
