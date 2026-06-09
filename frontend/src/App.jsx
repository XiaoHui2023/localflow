import { useCallback, useEffect, useState } from "react";
import { Link, NavLink, Route, Routes } from "react-router-dom";
import {
  createBlueprint,
  fetchAutomations,
  fetchConfig,
  fetchRunHistory,
  fetchRunHistoryRecord,
  fetchScript,
  fetchScripts,
  fetchStatus,
  postScriptCancel,
} from "./api.js";
import RunScriptPage from "./RunScriptPage.jsx";
import TemplateView from "./TemplateView.jsx";

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
      <h1>localflow</h1>
      <p>本机任务自动化（React + Python 标准库 HTTP）</p>
      <button type="button" onClick={load}>
        刷新状态
      </button>
      {error ? <p className="msg-error">{error}</p> : null}
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

function ScriptListItem({ item, selected, onSelect }) {
  const failed = item.status === "failed";
  return (
    <button
      type="button"
      className={`script-item${selected ? " selected" : ""}${failed ? " failed" : ""}`}
      onClick={() => onSelect(item)}
    >
      <div className="script-item-head">
        <strong>{item.name}</strong>
        <span className={`status-pill status-${item.status}`}>{item.status}</span>
      </div>
      {item.view ? <TemplateView node={item.view} /> : null}
    </button>
  );
}

function formatFinishedAt(value) {
  if (!value) {
    return "";
  }
  try {
    return new Date(value).toLocaleString();
  } catch {
    return value;
  }
}

function SaveAsBlueprint({ scriptId, scriptName, isBatch, variables, batchParams }) {
  const [name, setName] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");

  const save = async () => {
    const trimmed = name.trim();
    if (!trimmed) {
      setError("请填写蓝图名称");
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const body = {
        name: trimmed,
        script_id: scriptId,
        script_name: scriptName,
        is_batch: isBatch,
      };
      if (isBatch) {
        body.batch_params = batchParams || {};
      } else {
        body.variables = variables || {};
      }
      await createBlueprint(body);
      setName("");
      setMessage("已保存为蓝图");
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="detail-blueprint-save">
      <input
        type="text"
        placeholder="蓝图名称"
        value={name}
        disabled={busy}
        onChange={(event) => setName(event.target.value)}
      />
      <button type="button" disabled={busy} onClick={save}>
        保存为蓝图
      </button>
      {error ? <p className="msg-error">{error}</p> : null}
      {message ? <p className="msg-ok">{message}</p> : null}
    </div>
  );
}

function HistoryListItem({ item, selected, onSelect }) {
  const failed = item.status === "failed";
  return (
    <button
      type="button"
      className={`script-item${selected ? " selected" : ""}${failed ? " failed" : ""}`}
      onClick={() => onSelect(item)}
    >
      <div className="script-item-head">
        <strong>{item.script_name}</strong>
        <span className={`status-pill status-${item.status}`}>{item.status}</span>
      </div>
      <p className="hint">{formatFinishedAt(item.finished_at)}</p>
      {item.error ? <p className="msg-error">{item.error}</p> : null}
    </button>
  );
}

function HistoryDetail({ record }) {
  if (!record) {
    return <p className="hint">选择左侧历史记录查看详情</p>;
  }

  const runLink = `/run?id=${encodeURIComponent(record.script_id)}&history=${encodeURIComponent(record.id)}`;

  return (
    <div className="script-detail">
      <div className="script-detail-head">
        <div>
          <h3>{record.script_name}</h3>
          <p className="hint">
            {formatFinishedAt(record.finished_at)}
            {record.is_batch ? " · 批处理" : ""}
          </p>
        </div>
        <div className="detail-actions">
          <Link to={runLink} className="run-link">
            编辑参数并运行
          </Link>
        </div>
      </div>
      {record.result ? <TemplateView node={record.result} /> : null}
      {record.terminal_log_path ? (
        <p className="hint">日志文件：{record.terminal_log_path}</p>
      ) : null}
      {record.terminal ? (
        <>
          <h4>终端输出</h4>
          <pre className="terminal-box">{record.terminal}</pre>
        </>
      ) : null}
      {record.error ? (
        <>
          <h4 className="msg-error">错误</h4>
          <p className="msg-error">{record.error}</p>
        </>
      ) : null}
      {record.error_traceback ? (
        <>
          <h4>堆栈</h4>
          <pre className="terminal-box error-box">{record.error_traceback}</pre>
        </>
      ) : null}
      <SaveAsBlueprint
        scriptId={record.script_id}
        scriptName={record.script_name}
        isBatch={Boolean(record.is_batch)}
        variables={record.variables}
        batchParams={record.batch_params}
      />
    </div>
  );
}

function StopScriptButton({ script, onUpdated, onError }) {
  const [busy, setBusy] = useState(false);

  if (!script || script.status !== "running") {
    return null;
  }

  const force = Boolean(script.cancel_pending);
  const label = force ? "强制停止" : "停止";

  const onStop = async () => {
    setBusy(true);
    onError("");
    try {
      const payload = await postScriptCancel(script.id, { force });
      if (!payload.ok) {
        onError(payload.error || "停止失败");
        return;
      }
      onUpdated(payload.script);
    } catch (err) {
      onError(String(err));
    } finally {
      setBusy(false);
    }
  };

  return (
    <button type="button" className="btn-danger" disabled={busy} onClick={onStop}>
      {label}
    </button>
  );
}

function ScriptDetail({ script, onScriptUpdated, onError }) {
  if (!script) {
    return <p className="hint">选择左侧条目查看详情</p>;
  }

  const finished =
    script.status === "succeeded" ||
    script.status === "failed" ||
    script.status === "cancelled";
  const panel = finished && script.result ? script.result : script.view;
  const canEdit =
    script.status === "idle" ||
    script.status === "succeeded" ||
    script.status === "failed" ||
    script.status === "cancelled";

  return (
    <div className="script-detail">
      <div className="script-detail-head">
        <h3>{script.name}</h3>
        <div className="detail-actions">
          <StopScriptButton
            script={script}
            onUpdated={onScriptUpdated}
            onError={onError}
          />
          {canEdit ? (
            <Link to={`/run?id=${encodeURIComponent(script.id)}`} className="run-link">
              编辑参数并运行
            </Link>
          ) : null}
        </div>
      </div>
      {script.cancel_pending ? (
        <p className="hint">已发送停止信号，等待进程退出；可点击「强制停止」或等待超时。</p>
      ) : null}
      <TemplateView node={panel} />
      {script.terminal_log_path ? (
        <p className="hint">日志文件：{script.terminal_log_path}</p>
      ) : null}
      {script.terminal ? (
        <>
          <h4>终端输出</h4>
          <pre className="terminal-box">{script.terminal}</pre>
        </>
      ) : null}
      {script.error ? (
        <>
          <h4 className="msg-error">错误</h4>
          <p className="msg-error">{script.error}</p>
        </>
      ) : null}
      {script.error_traceback ? (
        <>
          <h4>堆栈</h4>
          <pre className="terminal-box error-box">{script.error_traceback}</pre>
        </>
      ) : null}
      {finished ? (
        <SaveAsBlueprint
          scriptId={script.id}
          scriptName={script.name}
          isBatch={Boolean(script.is_batch)}
          variables={script.user_variables}
          batchParams={script.batch_params}
        />
      ) : null}
    </div>
  );
}

function TaskPage() {
  const [data, setData] = useState({ running: [], history: [], idle: [] });
  const [detailMode, setDetailMode] = useState("script");
  const [selectedId, setSelectedId] = useState(null);
  const [selectedHistoryId, setSelectedHistoryId] = useState(null);
  const [detail, setDetail] = useState(null);
  const [historyDetail, setHistoryDetail] = useState(null);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    setError("");
    try {
      const [scriptsPayload, historyPayload] = await Promise.all([
        fetchScripts(),
        fetchRunHistory(),
      ]);
      const all = scriptsPayload.scripts || [];
      setData({
        running: scriptsPayload.running || [],
        history: historyPayload.history || [],
        idle: all.filter((item) => item.status === "idle"),
      });
    } catch (err) {
      setError(String(err));
    }
  }, []);

  const loadDetail = useCallback(async (id) => {
    if (!id) {
      setDetail(null);
      return;
    }
    try {
      const payload = await fetchScript(id);
      if (payload.ok) {
        setDetail(payload.script);
      }
    } catch {
      setDetail(null);
    }
  }, []);

  const loadHistoryDetail = useCallback(async (id) => {
    if (!id) {
      setHistoryDetail(null);
      return;
    }
    try {
      const payload = await fetchRunHistoryRecord(id);
      if (payload.ok) {
        setHistoryDetail(payload.record);
      }
    } catch {
      setHistoryDetail(null);
    }
  }, []);

  const selectScriptItem = (item) => {
    setDetailMode("script");
    setSelectedId(item.id);
    setSelectedHistoryId(null);
    setHistoryDetail(null);
    setDetail(item);
    loadDetail(item.id);
  };

  const selectHistoryItem = (item) => {
    setDetailMode("history");
    setSelectedHistoryId(item.id);
    setSelectedId(null);
    setDetail(null);
    setHistoryDetail(item);
    loadHistoryDetail(item.id);
  };

  useEffect(() => {
    refresh().catch(() => {});
    const timer = setInterval(() => {
      refresh().catch(() => {});
      if (detailMode === "script" && selectedId) {
        loadDetail(selectedId).catch(() => {});
      }
      if (detailMode === "history" && selectedHistoryId) {
        loadHistoryDetail(selectedHistoryId).catch(() => {});
      }
    }, 2000);
    return () => clearInterval(timer);
  }, [refresh, loadDetail, loadHistoryDetail, detailMode, selectedId, selectedHistoryId]);

  return (
    <section className="card task-layout">
      <h2>工作流</h2>
      {error ? <p className="msg-error">{error}</p> : null}
      <div className="task-columns">
        <div className="task-column">
          <h3>可启动 ({data.idle.length})</h3>
          {data.idle.length === 0 ? (
            <p className="hint">暂无待启动 Script</p>
          ) : (
            data.idle.map((item) => (
              <ScriptListItem
                key={item.id}
                item={item}
                selected={selectedId === item.id}
                onSelect={selectScriptItem}
              />
            ))
          )}
        </div>
        <div className="task-column">
          <h3>运行中 ({data.running.length})</h3>
          {data.running.length === 0 ? (
            <p className="hint">暂无运行中任务</p>
          ) : (
            data.running.map((item) => (
              <ScriptListItem
                key={item.id}
                item={item}
                selected={detailMode === "script" && selectedId === item.id}
                onSelect={selectScriptItem}
              />
            ))
          )}
        </div>
        <div className="task-column">
          <h3>历史记录 ({data.history.length})</h3>
          {data.history.length === 0 ? (
            <p className="hint">暂无历史记录</p>
          ) : (
            data.history.map((item) => (
              <HistoryListItem
                key={item.id}
                item={item}
                selected={detailMode === "history" && selectedHistoryId === item.id}
                onSelect={selectHistoryItem}
              />
            ))
          )}
        </div>
      </div>
      {detailMode === "history" ? (
        <HistoryDetail record={historyDetail} />
      ) : (
        <ScriptDetail
          script={detail}
          onScriptUpdated={setDetail}
          onError={setError}
        />
      )}
    </section>
  );
}

function AutomationsPage() {
  const [items, setItems] = useState([]);
  const [error, setError] = useState("");

  const load = useCallback(async () => {
    setError("");
    try {
      const payload = await fetchAutomations();
      setItems(payload.automations || []);
    } catch (err) {
      setError(String(err));
    }
  }, []);

  useEffect(() => {
    load();
    const timer = setInterval(() => {
      load().catch(() => {});
    }, 3000);
    return () => clearInterval(timer);
  }, [load]);

  return (
    <section className="card">
      <h2>Automation 事件</h2>
      <button type="button" onClick={load}>
        刷新
      </button>
      {error ? <p className="msg-error">{error}</p> : null}
      {items.length === 0 ? (
        <p className="hint">暂无已注册的 Automation</p>
      ) : (
        items.map((auto) => (
          <article key={auto.name} className="automation-card">
            <div className="automation-head">
              <h3>{auto.name}</h3>
              <span className="hint">
                {auto.type} · {auto.mode} · {auto.interval}s
              </span>
            </div>
            {auto.scripts.length > 0 ? (
              <div className="bound-scripts automation-scripts">
                {auto.scripts.map((script) => (
                  <span
                    key={script.id}
                    className={`status-pill status-${script.status}`}
                  >
                    {script.name}
                  </span>
                ))}
              </div>
            ) : (
              <p className="hint">未注册 Script</p>
            )}
            {auto.handlers.length === 0 ? (
              <p className="hint">未注册监听函数</p>
            ) : (
              <ul className="handler-list">
                {auto.handlers.map((handler) => (
                  <li key={`${handler.module}.${handler.qualname}`}>
                    <div className="handler-title">
                      <code>{handler.qualname}</code>
                      <span className="hint">{handler.module}</span>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </article>
        ))
      )}
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
        <NavLink to="/run">运行</NavLink>
        <NavLink to="/events">事件</NavLink>
        <NavLink to="/settings">设置</NavLink>
      </nav>
      <Routes>
        <Route path="/" element={<HomePage />} />
        <Route path="/task" element={<TaskPage />} />
        <Route path="/run" element={<RunScriptPage />} />
        <Route path="/events" element={<AutomationsPage />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </main>
  );
}
