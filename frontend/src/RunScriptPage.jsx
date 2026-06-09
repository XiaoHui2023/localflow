import { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import {
  fetchRunHistoryRecord,
  fetchScript,
  fetchScripts,
  patchScriptVariables,
  postScriptStart,
} from "./api.js";
import BlueprintPanel from "./BlueprintPanel.jsx";
import ParamSchemaForm from "./ParamSchemaForm.jsx";
import TemplateView from "./TemplateView.jsx";

function variableFieldType(value) {
  if (typeof value === "boolean") {
    return "boolean";
  }
  if (typeof value === "number") {
    return "number";
  }
  if (typeof value === "string" && value.length > 80) {
    return "textarea";
  }
  return "text";
}

function VariableField({ name, value, onChange, disabled }) {
  const fieldType = variableFieldType(value);

  if (fieldType === "boolean") {
    return (
      <label className="var-field var-field-check">
        <input
          type="checkbox"
          checked={Boolean(value)}
          disabled={disabled}
          onChange={(event) => onChange(name, event.target.checked)}
        />
        <span>{name}</span>
      </label>
    );
  }

  if (fieldType === "textarea") {
    return (
      <label className="var-field">
        <span className="var-label">{name}</span>
        <textarea
          rows={4}
          value={value ?? ""}
          disabled={disabled}
          onChange={(event) => onChange(name, event.target.value)}
        />
      </label>
    );
  }

  return (
    <label className="var-field">
      <span className="var-label">{name}</span>
      <input
        type={fieldType === "number" ? "number" : "text"}
        value={value ?? ""}
        disabled={disabled}
        onChange={(event) =>
          onChange(
            name,
            fieldType === "number" ? Number(event.target.value) : event.target.value,
          )
        }
      />
    </label>
  );
}

export default function RunScriptPage() {
  const [searchParams] = useSearchParams();
  const [scripts, setScripts] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [flatForm, setFlatForm] = useState({});
  const [batchForm, setBatchForm] = useState({});
  const [paramSchema, setParamSchema] = useState([]);
  const [isBatch, setIsBatch] = useState(false);
  const [preview, setPreview] = useState(null);
  const [status, setStatus] = useState("idle");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [historyHint, setHistoryHint] = useState("");

  const selected = useMemo(
    () => scripts.find((item) => item.id === selectedId) ?? null,
    [scripts, selectedId],
  );

  const loadScripts = useCallback(async () => {
    const payload = await fetchScripts();
    const list = payload.scripts || [];
    setScripts(list);
    return list;
  }, []);

  const selectScript = useCallback(async (id) => {
    setError("");
    setMessage("");
    setSelectedId(id);
    const payload = await fetchScript(id);
    if (!payload.ok) {
      setError(payload.error || "加载失败");
      return;
    }
    const script = payload.script;
    setIsBatch(Boolean(script.is_batch));
    setParamSchema(script.param_schema || []);
    setBatchForm(script.batch_params || {});
    setFlatForm(script.user_variables || {});
    setPreview(script.view);
    setStatus(script.status);
  }, []);

  useEffect(() => {
    const urlId = searchParams.get("id");
    const historyId = searchParams.get("history");
    setHistoryHint("");
    loadScripts()
      .then(async (list) => {
        if (list.length === 0) {
          return;
        }
        const pick =
          urlId && list.some((item) => item.id === urlId) ? urlId : list[0].id;
        await selectScript(pick);
        if (!historyId) {
          return;
        }
        const payload = await fetchRunHistoryRecord(historyId);
        if (!payload.ok) {
          setError(payload.error || "历史记录不存在");
          return;
        }
        const record = payload.record;
        if (record.script_id !== pick) {
          await selectScript(record.script_id);
        }
        await applyRecordParams(record.script_id, record);
        const finishedAt = record.finished_at
          ? new Date(record.finished_at).toLocaleString()
          : "";
        setHistoryHint(
          finishedAt
            ? `已从历史记录载入参数（${finishedAt}）`
            : "已从历史记录载入参数",
        );
      })
      .catch((err) => setError(String(err)));
  }, [loadScripts, selectScript, searchParams]);

  const onFlatFieldChange = (name, value) => {
    setFlatForm((prev) => ({ ...prev, [name]: value }));
  };

  const onBatchFieldChange = (name, value) => {
    setBatchForm((prev) => ({ ...prev, [name]: value }));
  };

  const buildPatchBody = () => {
    if (isBatch) {
      return { batch_params: batchForm };
    }
    return { variables: flatForm };
  };

  const refreshPreview = async () => {
    if (!selectedId) {
      return;
    }
    setBusy(true);
    setError("");
    try {
      const payload = await patchScriptVariables(selectedId, buildPatchBody());
      if (!payload.ok) {
        setError(payload.error || "预览失败");
        return;
      }
      setPreview(payload.script.view);
      setStatus(payload.script.status);
      if (payload.script.is_batch) {
        setBatchForm(payload.script.batch_params || batchForm);
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const applyRecordParams = async (scriptId, record) => {
    const body = record.is_batch
      ? { batch_params: record.batch_params || {} }
      : { variables: record.variables || {} };
    if (record.is_batch) {
      setBatchForm(record.batch_params || {});
    } else {
      setFlatForm(record.variables || {});
    }
    const payload = await patchScriptVariables(scriptId, body);
    if (!payload.ok) {
      throw new Error(payload.error || "载入参数失败");
    }
    setPreview(payload.script.view);
    setStatus(payload.script.status);
    if (payload.script.is_batch) {
      setBatchForm(payload.script.batch_params || record.batch_params || {});
    }
  };

  const applyBlueprint = async (blueprint) => {
    if (blueprint.script_id !== selectedId) {
      await selectScript(blueprint.script_id);
    }
    const body = blueprint.is_batch
      ? { batch_params: blueprint.batch_params || {} }
      : { variables: blueprint.variables || {} };
    if (blueprint.is_batch) {
      setBatchForm(blueprint.batch_params || {});
    } else {
      setFlatForm(blueprint.variables || {});
    }
    const payload = await patchScriptVariables(blueprint.script_id, body);
    if (!payload.ok) {
      throw new Error(payload.error || "应用蓝图失败");
    }
    setPreview(payload.script.view);
    setStatus(payload.script.status);
  };

  const onBlueprintRunStarted = (payload) => {
    setStatus("running");
    if (payload.script?.view) {
      setPreview(payload.script.view);
    }
  };

  const runScript = async () => {
    if (!selectedId) {
      return;
    }
    setBusy(true);
    setError("");
    setMessage("");
    try {
      const payload = await postScriptStart(selectedId, buildPatchBody());
      if (!payload.ok) {
        setError(payload.error || "启动失败");
        return;
      }
      setMessage("已启动，可在任务页查看进度。");
      setStatus("running");
      if (payload.script?.view) {
        setPreview(payload.script.view);
      }
    } catch (err) {
      setError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const running = status === "running";

  return (
    <section className="card run-script-layout">
      <h2>手动运行 Script</h2>
      <p className="hint">
        {isBatch
          ? "批处理 Script：勾选用例、设置次数与其它参数后运行。"
          : "编辑参数后预览界面，确认无误再运行。"}
      </p>
      {error ? <p className="msg-error">{error}</p> : null}
      {historyHint ? <p className="msg-ok">{historyHint}</p> : null}
      {message ? <p className="msg-ok">{message}</p> : null}
      <div className="run-script-columns">
        <aside className="run-script-list">
          <h3>Script 列表</h3>
          {scripts.length === 0 ? (
            <p className="hint">暂无已注册 Script</p>
          ) : (
            scripts.map((item) => (
              <button
                key={item.id}
                type="button"
                className={`script-pick${selectedId === item.id ? " selected" : ""}`}
                onClick={() => selectScript(item.id)}
              >
                <strong>{item.name}</strong>
                <span className={`status-pill status-${item.status}`}>
                  {item.is_batch ? "batch" : item.status}
                </span>
              </button>
            ))
          )}
          <BlueprintPanel
            scriptId={selectedId}
            scriptName={selected?.name || ""}
            isBatch={isBatch}
            flatForm={flatForm}
            batchForm={batchForm}
            disabled={running || busy}
            onLoad={applyBlueprint}
            onRunStarted={onBlueprintRunStarted}
            onError={setError}
            onMessage={setMessage}
          />
        </aside>
        <div className="run-script-main">
          {!selected ? (
            <p className="hint">请选择 Script</p>
          ) : (
            <>
              <div className="run-script-head">
                <h3>{selected.name}</h3>
                <span className="hint">{selected.type}</span>
              </div>
              <form
                className="var-form"
                onSubmit={(event) => {
                  event.preventDefault();
                  runScript();
                }}
              >
                <h4>参数</h4>
                {isBatch ? (
                  <ParamSchemaForm
                    schema={paramSchema}
                    values={batchForm}
                    disabled={running || busy}
                    onChange={onBatchFieldChange}
                  />
                ) : Object.keys(flatForm).length === 0 ? (
                  <p className="hint">该 Script 无可编辑参数</p>
                ) : (
                  Object.entries(flatForm).map(([name, value]) => (
                    <VariableField
                      key={name}
                      name={name}
                      value={value}
                      disabled={running || busy}
                      onChange={onFlatFieldChange}
                    />
                  ))
                )}
                <div className="run-script-actions">
                  <button type="button" disabled={running || busy} onClick={refreshPreview}>
                    更新预览
                  </button>
                  <button type="submit" className="btn-primary" disabled={running || busy}>
                    运行
                  </button>
                  {running ? (
                    <Link to="/task" className="run-link">
                      查看任务进度 →
                    </Link>
                  ) : null}
                </div>
              </form>
              <div className="run-preview">
                <h4>界面预览</h4>
                {preview ? <TemplateView node={preview} /> : <p className="hint">—</p>}
              </div>
            </>
          )}
        </div>
      </div>
    </section>
  );
}
