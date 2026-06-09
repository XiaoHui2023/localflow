import { useCallback, useEffect, useState } from "react";
import {
  createBlueprint,
  deleteBlueprint,
  fetchBlueprint,
  fetchBlueprints,
  postBlueprintRun,
} from "./api.js";

export default function BlueprintPanel({
  scriptId,
  scriptName,
  isBatch,
  flatForm,
  batchForm,
  disabled,
  onLoad,
  onRunStarted,
  onError,
  onMessage,
}) {
  const [items, setItems] = useState([]);
  const [saveName, setSaveName] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = useCallback(async () => {
    if (!scriptId) {
      setItems([]);
      return;
    }
    const payload = await fetchBlueprints(scriptId);
    setItems(payload.blueprints || []);
  }, [scriptId]);

  useEffect(() => {
    reload().catch(() => setItems([]));
  }, [reload]);

  const saveBlueprint = async () => {
    const name = saveName.trim();
    if (!name) {
      onError("请填写蓝图名称");
      return;
    }
    setBusy(true);
    onError("");
    try {
      const body = {
        name,
        script_id: scriptId,
        script_name: scriptName,
        is_batch: isBatch,
      };
      if (isBatch) {
        body.batch_params = batchForm;
      } else {
        body.variables = flatForm;
      }
      await createBlueprint(body);
      setSaveName("");
      onMessage("蓝图已保存");
      await reload();
    } catch (err) {
      onError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const loadBlueprint = async (id) => {
    setBusy(true);
    onError("");
    try {
      const payload = await fetchBlueprint(id);
      if (!payload.ok) {
        onError(payload.error || "加载蓝图失败");
        return;
      }
      await onLoad(payload.blueprint);
      onMessage(`已加载蓝图：${payload.blueprint.name}`);
    } catch (err) {
      onError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const runBlueprint = async (id) => {
    setBusy(true);
    onError("");
    try {
      const payload = await postBlueprintRun(id);
      if (!payload.ok) {
        onError(payload.error || "启动失败");
        return;
      }
      onMessage("已按蓝图启动运行");
      onRunStarted(payload);
    } catch (err) {
      onError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const removeBlueprint = async (id) => {
    setBusy(true);
    onError("");
    try {
      await deleteBlueprint(id);
      onMessage("蓝图已删除");
      await reload();
    } catch (err) {
      onError(String(err));
    } finally {
      setBusy(false);
    }
  };

  const inactive = disabled || busy || !scriptId;

  return (
    <div className="blueprint-panel">
      <h3>蓝图</h3>
      <p className="hint">保存当前参数，下次一键加载或运行。</p>
      <div className="blueprint-save">
        <input
          type="text"
          placeholder="蓝图名称"
          value={saveName}
          disabled={inactive}
          onChange={(event) => setSaveName(event.target.value)}
        />
        <button type="button" disabled={inactive} onClick={saveBlueprint}>
          保存
        </button>
      </div>
      {items.length === 0 ? (
        <p className="hint">暂无蓝图</p>
      ) : (
        <ul className="blueprint-list">
          {items.map((item) => (
            <li key={item.id} className="blueprint-item">
              <div className="blueprint-item-head">
                <strong>{item.name}</strong>
              </div>
              <div className="blueprint-item-actions">
                <button type="button" disabled={inactive} onClick={() => loadBlueprint(item.id)}>
                  加载
                </button>
                <button
                  type="button"
                  className="btn-primary"
                  disabled={inactive}
                  onClick={() => runBlueprint(item.id)}
                >
                  运行
                </button>
                <button type="button" disabled={inactive} onClick={() => removeBlueprint(item.id)}>
                  删除
                </button>
              </div>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
