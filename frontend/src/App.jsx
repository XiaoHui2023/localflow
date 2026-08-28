import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Editor, { DiffEditor } from "@monaco-editor/react";
import { Tree } from "react-arborist";
import { FitAddon } from "@xterm/addon-fit";
import { SearchAddon } from "@xterm/addon-search";
import { WebLinksAddon } from "@xterm/addon-web-links";
import { Terminal } from "@xterm/xterm";
import "@xterm/xterm/css/xterm.css";
import { Activity, Check, ChevronDown, ChevronRight, ClipboardPaste, Clock3, Copy, File, FileCheck2, FileCode2, FilePenLine, Files, Folder, FolderOpen, FolderPlus, Link, ListChecks, Moon, Pencil, Play, Plus, Scissors, Search, Send, Settings2, Sun, TerminalSquare, Trash2, TriangleAlert, X } from "lucide-react";
import { api } from "./api";
import { Hint } from "./Tooltip";

const finalStates = new Set(["succeeded", "failed", "cancelled", "lost"]);
const coreLabels = { queued: "队列中", starting: "启动中", running: "运行中", stopping: "退出中", succeeded: "已完成", failed: "执行错误", cancelled: "已停止", lost: "状态丢失" };
const showTime = (value) => value ? new Intl.DateTimeFormat("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date(value)) : "—";
const taskLabel = (task) => task.status?.label || coreLabels[task.state] || task.state;
const taskTone = (task) => task.status?.tone || (task.state === "succeeded" ? "success" : ["failed", "lost"].includes(task.state) ? "danger" : "neutral");
const QUEUE_FOLD_THRESHOLD = 20;
const tagKey = (task) => [...(task.labels || [])].sort().join("\u001f");
const compactQueued = (tasks) => {
  const rows = new Map();
  for (const task of tasks) {
    const key = `${tagKey(task)}\u001e${task.name}`;
    const row = rows.get(key);
    if (row) row.count += 1;
    else rows.set(key, { task, count: 1 });
  }
  return [...rows.values()];
};

function useTheme() {
  const [theme, setTheme] = useState(document.documentElement.dataset.theme === "dark" ? "dark" : "light");
  const apply = (next) => { document.documentElement.dataset.theme = next; document.documentElement.dataset.themeGuard = next; localStorage.setItem("localflow-theme", next); setTheme(next); };
  return [theme, apply];
}

function useUiRevision() {
  const revision = useRef();
  useEffect(() => {
    let active = true;
    const check = async () => {
      try {
        const current = (await api.uiRevision()).revision;
        if (!active) return;
        if (revision.current && revision.current !== current) location.reload();
        revision.current = current;
      } catch { /* the service may still be starting */ }
    };
    check();
    const timer = setInterval(check, 2000);
    return () => { active = false; clearInterval(timer); };
  }, []);
}

function TaskTerminal({ task, interactive, theme }) {
  const host = useRef(); const finder = useRef(); const [searching, setSearching] = useState(false); const [query, setQuery] = useState("");
  useEffect(() => {
    const element = host.current;
    const dark = theme === "dark"; const term = new Terminal({ convertEol: true, cursorBlink: interactive, fontSize: 13, fontFamily: "Cascadia Mono, ui-monospace, monospace", scrollback: 5000, theme: dark ? { background: "#111418", foreground: "#e5e7eb" } : { background: "#fbfcfd", foreground: "#24292f" } });
    const fit = new FitAddon(); const search = new SearchAddon(); term.loadAddon(fit); term.loadAddon(search); term.loadAddon(new WebLinksAddon((event, uri) => { if (event.ctrlKey || event.metaKey) window.open(uri, "_blank", "noopener,noreferrer"); })); term.open(element); finder.current = search;
    let frame; const observer = new ResizeObserver(() => { cancelAnimationFrame(frame); frame = requestAnimationFrame(() => { if (element.clientWidth && element.clientHeight) fit.fit(); }); }); observer.observe(element); fit.fit(); element.dataset.rows = String(term.rows); element.dataset.columns = String(term.cols);
    const protocol = location.protocol === "https:" ? "wss" : "ws"; const socket = new WebSocket(`${protocol}://${location.host}/api/v1/tasks/${task.id}/terminal`);
    socket.onopen = () => { element.dataset.connection = "open"; term.writeln(interactive ? "[终端已连接]" : "[只读回放已连接]"); }; socket.onmessage = (event) => { const message = JSON.parse(event.data); if (message.type === "output") { const bytes = Uint8Array.from(atob(message.data), (value) => value.charCodeAt(0)); term.write(bytes, () => { if (socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "ack", offset: message.offset })); }); } else if (message.type === "error") term.writeln(`\r\n[${message.message}]`); }; socket.onclose = () => { if (element.isConnected) { element.dataset.connection = "closed"; term.writeln("\r\n[连接关闭]"); } };
    term.onData((data) => { if (interactive && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "input", data: btoa(unescape(encodeURIComponent(data))) })); }); term.onResize(({ rows, cols }) => { element.dataset.rows = String(rows); element.dataset.columns = String(cols); if (interactive && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify({ type: "resize", rows, cols })); });
    return () => { observer.disconnect(); cancelAnimationFrame(frame); socket.onopen = null; socket.onmessage = null; socket.onclose = null; socket.close(); finder.current = undefined; term.dispose(); };
  }, [task.id, interactive, theme]);
  return <div className="terminal-shell"><div className="terminal-tools">{searching && <input autoFocus aria-label="终端搜索" placeholder="查找" value={query} onChange={(event) => { setQuery(event.target.value); finder.current?.findNext(event.target.value); }} onKeyDown={(event) => { if (event.key === "Enter") finder.current?.findNext(query); if (event.key === "Escape") setSearching(false); }}/>}<button className="icon" aria-label="在终端中查找" aria-pressed={searching} onClick={() => setSearching((old) => !old)}><Search/></button></div><div className="terminal" ref={host}/></div>;
}

async function writeClipboard(text) {
  if (navigator.clipboard?.writeText) { try { await navigator.clipboard.writeText(text); return; } catch { /* compatible fallback */ } }
  const input = document.createElement("textarea"); input.value = text; input.setAttribute("readonly", ""); input.style.cssText = "position:fixed;left:-9999px;top:0;opacity:0"; document.body.appendChild(input); input.select(); const copied = document.execCommand("copy"); input.remove(); if (!copied) throw new Error("copy unavailable");
}
function CopyValue({ label, value }) {
  const [copied, setCopied] = useState(false); const timer = useRef();
  useEffect(() => () => clearTimeout(timer.current), []);
  const text = typeof value === "object" ? JSON.stringify(value) : String(value ?? "—");
  const copy = async () => { await writeClipboard(text); setCopied(true); clearTimeout(timer.current); timer.current = setTimeout(() => setCopied(false), 1200); };
  return <div className="copy-field">{label && <span className="copy-label">{label}</span>}<span className="copy-shell" data-copied={copied}><Hint label={copied ? "已复制" : "点击复制"}><button className="copy-value" type="button" onClick={copy} aria-label={`${label ? `${label}，` : ""}${copied ? "已复制" : "点击复制"}`}><code>{text}</code></button></Hint><i className="copy-confirm" aria-hidden="true"><Check/></i><span className="copy-status" role="status">{copied ? "已复制" : ""}</span></span></div>;
}

function TaskDetail({ task, role, interrupt }) {
  const hidden = new Set(["source", "variable_sources"]); const custom = Object.entries(task.custom || {}).filter(([key, value]) => !hidden.has(key) && !key.startsWith("_") && value != null && value !== "" && (!Array.isArray(value) || value.length));
  const stopLabel = task.state === "stopping" ? "加快退出" : "中止";
  return <div className="detail"><div className="details"><div className="detail-time"><span>开始时间</span><time>{showTime(task.started_at)}</time></div>{task.command && <CopyValue label="命令" value={task.command.join(" ")}/>}<CopyValue label="工作目录" value={task.working_directory}/><CopyValue label="输出" value={task.log_path}/>{custom.map(([key, value]) => <CopyValue label={key === "seed" ? "随机种子" : key} value={value} key={key}/>)}</div>{role === "admin" && !finalStates.has(task.state) && <Hint label={stopLabel}><button className="stop-action" aria-label={task.state === "stopping" ? "加快退出任务" : "中止任务"} onClick={interrupt}><X strokeWidth={2}/></button></Hint>}</div>;
}

function TaskItem({ task, count = 1, open, fresh, role, toggle, ack, interrupt }) {
  const tone = taskTone(task); const timeKind = task.ended_at ? "结束" : "开始"; return <article className={`task-item ${open ? "open" : ""}`}><button className={`task-row ${fresh ? "has-fresh" : ""}`} aria-expanded={open} onClick={toggle} onMouseEnter={() => fresh && ack()}>{fresh && <i className="fresh-dot" aria-label="新完成"/>}<span className="task-name"><b>{task.name}</b>{task.labels?.length > 0 && <small>{task.labels.map((item) => <em key={item}>{item}</em>)}</small>}{count > 1 && <strong className="queue-multiple" aria-label={`${count} 个相同任务`}>×{count}</strong>}</span><span className={`status tone-${tone}`}>{taskLabel(task)}</span><time aria-label={`${timeKind}时间`}>{showTime(task.ended_at || task.started_at || task.created_at)}</time><ChevronDown/></button>{open && <TaskDetail task={task} role={role} interrupt={interrupt}/>}</article>;
}

function QueueTasks({ tasks, renderTask }) {
  const [expanded, setExpanded] = useState(new Set());
  if (tasks.length <= QUEUE_FOLD_THRESHOLD) return compactQueued(tasks).map(({ task, count }) => renderTask(task, count));
  const buckets = new Map();
  for (const task of tasks) {
    const key = tagKey(task); const bucket = buckets.get(key);
    if (bucket) bucket.tasks.push(task);
    else buckets.set(key, { key, labels: [...(task.labels || [])].sort(), tasks: [task] });
  }
  return [...buckets.values()].flatMap((bucket) => {
    if (!bucket.key || bucket.tasks.length < 2) return compactQueued(bucket.tasks).map(({ task, count }) => renderTask(task, count));
    const open = expanded.has(bucket.key);
    return <section className={`queue-cluster ${open ? "open" : ""}`} key={`queue:${bucket.key}`}><button className="queue-cluster-row" aria-expanded={open} onClick={() => setExpanded((old) => { const next = new Set(old); if (next.has(bucket.key)) next.delete(bucket.key); else next.add(bucket.key); return next; })}><span>{bucket.labels.map((label) => <em key={label}>{label}</em>)}</span><strong>×{bucket.tasks.length}</strong><ChevronDown/></button>{open && <div className="queue-cluster-items">{compactQueued(bucket.tasks).map(({ task, count }) => renderTask(task, count))}</div>}</section>;
  });
}

function TerminalPage({ tasks, role, theme }) {
  const available = tasks.filter((task) => ["starting", "running", "stopping"].includes(task.state));
  const [selectedId, setSelectedId] = useState(); const [input, setInput] = useState(""); const [notice, setNotice] = useState("");
  useEffect(() => { if (!available.some((task) => task.id === selectedId)) setSelectedId(available[0]?.id); }, [tasks, selectedId]);
  const selected = available.find((task) => task.id === selectedId);
  const send = async () => { if (!selected || !input) return; try { await api.terminalInput(selected.id, `${input}\n`); setInput(""); setNotice("已发送"); } catch (error) { setNotice(error.message); } };
  const control = async (key) => { try { await api.terminalControl(selected.id, key); setNotice(`${key === "ctrl_c" ? "Ctrl+C" : "Ctrl+D"} 已发送`); } catch (error) { setNotice(error.message); } };
  return <div className="terminal-page"><aside aria-label="运行中的终端">{available.map((task) => <button className={task.id === selectedId ? "active" : ""} key={task.id} onClick={() => setSelectedId(task.id)}><i className={`tone-${taskTone(task)}`}/><span><b>{task.name}</b><small>{taskLabel(task)}</small></span></button>)}{available.length === 0 && <p>没有可交互的任务</p>}</aside><section>{selected ? <><header><div><TerminalSquare/><b>{selected.name}</b></div>{role === "admin" && <div className="terminal-actions"><button className="terminal-key" onClick={() => control("ctrl_c")}>Ctrl+C</button><button className="terminal-key" onClick={() => control("ctrl_d")}>Ctrl+D</button><span className="terminal-command"><input aria-label="发送终端指令" placeholder="输入后按 Enter" value={input} onChange={(event) => setInput(event.target.value)} onKeyDown={(event) => event.key === "Enter" && send()}/><button aria-label="发送终端指令" disabled={!input} onClick={send}><Send/></button></span></div>}</header><span className="terminal-status" role="status">{notice}</span><TaskTerminal task={selected} interactive={role === "admin"} theme={theme}/></> : <div className="tasks-empty"><TerminalSquare/><p>启动任务后可在这里交互</p></div>}</section></div>;
}

function configState(diagnosis) {
  if (!diagnosis || diagnosis.valid === false) return "invalid";
  if (diagnosis.kind === "task") return "task";
  if (diagnosis.kind === "fragment") return "fragment";
  return "generic";
}

const configStateLabels = { generic: "普通参数", fragment: "共享片段", task: "可运行配置", invalid: "配置有误" };
const configExtension = (name) => name.match(/\.(?:ya?ml|json|toml)$/i)?.[0] || "";
const visibleConfigName = (name) => name.slice(0, name.length - configExtension(name).length);
const workspaceExtension = (name) => name.match(/\.(?:ya?ml|json|toml|py|md)$/i)?.[0] || "";

function buildTree(entries, diagnostics) {
  const nodes = new Map(); const roots = [];
  for (const entry of [...entries].sort((a, b) => a.path.split("/").length - b.path.split("/").length || a.path.localeCompare(b.path))) {
    const name = pathLeaf(entry.path); const node = { id: entry.kind === "directory" ? `folder:${entry.path}` : entry.path, name, path: entry.path, kind: entry.kind, symlink: entry.symlink, readonly: entry.readonly, diagnosis: diagnostics[entry.path], ...(entry.kind === "directory" ? { children: [] } : {}) };
    nodes.set(entry.path, node); const parentPath = entry.path.includes("/") ? entry.path.slice(0, entry.path.lastIndexOf("/")) : ""; const parent = nodes.get(parentPath); if (parent) parent.children.push(node); else roots.push(node);
  }
  return roots;
}

function TreeNode({ node, style, dragHandle }) {
  const state = node.isInternal ? "folder" : node.data.path.startsWith("plugins/") ? "plugin" : configState(node.data.diagnosis);
  const Icon = node.data.symlink ? Link : node.isInternal ? (node.isOpen ? FolderOpen : Folder) : state === "plugin" ? FileCode2 : state === "task" ? FileCheck2 : state === "fragment" ? Files : state === "invalid" ? TriangleAlert : File;
  const label = node.isInternal ? "文件夹" : state === "plugin" ? "插件文件" : configStateLabels[state];
  const displayName = node.isInternal ? node.data.name : visibleConfigName(node.data.name); const submit = (value) => { const clean = value.trim(); const extension = node.isInternal ? "" : workspaceExtension(node.data.name); node.submit(node.isInternal ? clean : `${clean.slice(0, clean.length - workspaceExtension(clean).length)}${extension}`); };
  return <Hint label={node.data.symlink ? `${label} · 软链接` : label} side="right"><div data-file={node.id} data-config-state={state} aria-label={`${displayName}，${label}`} className={`tree-node state-${state} ${node.isSelected ? "selected" : ""}`} style={style} ref={dragHandle} onClick={() => { node.select(); if (node.isInternal) node.toggle(); }} onDoubleClick={() => !node.data.readonly && node.edit()}>{node.isInternal ? (node.isOpen ? <ChevronDown aria-hidden="true"/> : <ChevronRight aria-hidden="true"/>) : <span className="tree-spacer"/>}<Icon aria-hidden="true"/>{node.isEditing ? <input aria-label="名称" ref={node.editInputRef} defaultValue={displayName} onBlur={(event) => submit(event.currentTarget.value)} onKeyDown={(event) => { if (event.key === "Enter") submit(event.currentTarget.value); if (event.key === "Escape") node.reset(); }}/>: <span>{displayName}</span>}</div></Hint>;
}

function CasePicker({ field, filePath, values, discoverValues, setValues }) {
  const [options, setOptions] = useState([]); const [error, setError] = useState(""); const [editing, setEditing] = useState(); const [scope, setScope] = useState([]); const [drag, setDrag] = useState(); const dragRef = useRef(); const wheelRef = useRef({ amount: 0, direction: 0 }); const wheelAction = useRef(); const grid = useRef(); const suppressClick = useRef(false);
  const countField = field.count_field; const defaultCountField = field.default_count_field;
  const included = new Set(values[field.name] || []); const runs = values[countField] || {}; const defaultRuns = (defaultCountField && values[defaultCountField]) || 1; const scoped = new Set(scope);
  useEffect(() => { const timer = setTimeout(() => api.discoverConfig(filePath, discoverValues).then((result) => { setOptions(result.items); setError(""); }).catch((reason) => setError(reason.message)), 250); return () => clearTimeout(timer); }, [filePath, discoverValues]);
  useEffect(() => { const clear = (event) => { if (grid.current && !grid.current.contains(event.target)) setScope([]); }; document.addEventListener("pointerdown", clear, true); return () => document.removeEventListener("pointerdown", clear, true); }, []);
  const count = (name) => included.has(name) ? Number(runs[name] ?? defaultRuns) : 0;
  const changeCounts = (names, resolve) => setValues((current) => {
    const currentIncluded = new Set(current[field.name] || []); const nextRuns = { ...(current[countField] || {}) }; const fallback = (defaultCountField && current[defaultCountField]) || 1;
    for (const name of names) { const old = currentIncluded.has(name) ? Number(nextRuns[name] ?? fallback) : 0; const next = Math.max(0, Number(resolve(old)) || 0); if (next) { currentIncluded.add(name); nextRuns[name] = next; } else { currentIncluded.delete(name); delete nextRuns[name]; } }
    return { ...current, [field.name]: options.filter((name) => currentIncluded.has(name)), [countField]: nextRuns };
  });
  const targets = (name) => scoped.has(name) ? scope : [name];
  const increment = (event, name) => {
    if (suppressClick.current?.name === name && performance.now() <= suppressClick.current.until) { suppressClick.current = undefined; return; }
    suppressClick.current = undefined;
    if (event.ctrlKey || event.metaKey) { setScope((current) => current.includes(name) ? current.filter((item) => item !== name) : [...current, name]); return; }
    if (scope.length && !scoped.has(name)) setScope([]);
    changeCounts(targets(name), (old) => old + 1);
  };
  const adjustWithWheel = (event, name) => {
    if (editing) return;
    event.preventDefault(); event.stopPropagation();
    const unit = event.deltaMode === 1 ? 40 : event.deltaMode === 2 ? 100 : 1; const delta = event.deltaY * unit; const direction = Math.sign(delta);
    if (!direction) return;
    if (wheelRef.current.direction && wheelRef.current.direction !== direction) wheelRef.current.amount = 0;
    wheelRef.current.direction = direction; wheelRef.current.amount += Math.abs(delta);
    const steps = Math.floor(wheelRef.current.amount / 80); if (!steps) return;
    wheelRef.current.amount %= 80; changeCounts(targets(name), (old) => old + (direction < 0 ? steps : -steps));
  };
  wheelAction.current = adjustWithWheel;
  useEffect(() => { const root = grid.current; const handle = (event) => { const item = event.target.closest(".case-item"); if (item && root.contains(item)) wheelAction.current(event, item.dataset.case); }; root.addEventListener("wheel", handle, { passive: false }); return () => root.removeEventListener("wheel", handle); }, []);
  const beginEdit = (name) => setEditing({ name, value: String(count(name)) });
  const finishEdit = (commit) => { if (!editing) return; if (commit) changeCounts(targets(editing.name), () => editing.value); setEditing(undefined); };
  const startMarquee = (event, kind) => {
    if (event.button !== 0 || event.target.closest(".case-count")) return;
    const root = event.currentTarget; const box = root.getBoundingClientRect();
    const startedCase = event.target.closest(".case-item")?.dataset.case;
    const origin = { pointerId: event.pointerId, x: event.clientX - box.left, y: event.clientY - box.top, startedOnItem: Boolean(startedCase), startedCase };
    const matches = (pointer) => kind === "mouse" || pointer.pointerId === origin.pointerId;
    const moveEvent = kind === "mouse" ? "mousemove" : "pointermove"; const upEvent = kind === "mouse" ? "mouseup" : "pointerup"; const cancelEvent = kind === "mouse" ? "mouseleave" : "pointercancel";
    const update = (pointer) => {
      if (!matches(pointer)) return;
      const currentBox = root.getBoundingClientRect(); const x = pointer.clientX - currentBox.left; const y = pointer.clientY - currentBox.top;
      const next = { ...origin, left: Math.min(origin.x, x), top: Math.min(origin.y, y), width: Math.abs(x - origin.x), height: Math.abs(y - origin.y) };
      dragRef.current = next; setDrag(next);
    };
    const cleanup = () => { window.removeEventListener(moveEvent, update); window.removeEventListener(upEvent, finish); window.removeEventListener(cancelEvent, cancel); dragRef.current = undefined; setDrag(undefined); };
    const finish = (pointer) => {
      if (!matches(pointer)) return;
      update(pointer); const current = dragRef.current;
      if (current && current.width + current.height > 8) {
        suppressClick.current = origin.startedCase ? { name: origin.startedCase, until: performance.now() + 300 } : undefined;
        const currentBox = root.getBoundingClientRect();
        const selection = { left: currentBox.left + current.left, right: currentBox.left + current.left + current.width, top: currentBox.top + current.top, bottom: currentBox.top + current.top + current.height };
        const hits = [...root.querySelectorAll(".case-item")].filter((item) => { const itemBox = item.getBoundingClientRect(); return itemBox.left < selection.right && itemBox.right > selection.left && itemBox.top < selection.bottom && itemBox.bottom > selection.top; }).map((item) => item.dataset.case);
        setScope(hits);
      } else if (!origin.startedOnItem) setScope([]);
      cleanup();
    };
    const cancel = (pointer) => { if (matches(pointer)) cleanup(); };
    dragRef.current = { ...origin, left: origin.x, top: origin.y, width: 0, height: 0 }; setDrag(dragRef.current);
    window.addEventListener(moveEvent, update); window.addEventListener(upEvent, finish); window.addEventListener(cancelEvent, cancel);
  };
  return <fieldset className="case-picker"><legend>{field.label || "Case"}</legend>{error && <small className="error">{error}</small>}<div className="case-list" ref={grid} onMouseDown={(event) => startMarquee(event, "mouse")} onPointerDown={(event) => event.pointerType === "pen" && startMarquee(event, "pointer")}>{options.map((name) => { const amount = count(name); const isScoped = scoped.has(name); const groupSize = isScoped ? scope.length : 1; return <div className={`case-item ${amount ? "has-count" : ""} ${isScoped ? "scoped" : ""}`} data-case={name} key={name}><button type="button" className="case-main" aria-pressed={isScoped} aria-label={`${name}${amount ? `，${amount} 次` : "，未运行"}${isScoped ? "，已框选" : ""}`} onClick={(event) => increment(event, name)}><span>{name}</span></button>{amount > 0 && (editing?.name === name ? <input className="case-count" data-count-editor aria-label={groupSize > 1 ? `设置所选 ${groupSize} 个 Case 运行次数` : `${name} 运行次数`} autoFocus type="number" min="0" value={editing.value} onChange={(event) => setEditing({ ...editing, value: event.target.value })} onBlur={() => finishEdit(true)} onKeyDown={(event) => { if (event.key === "Enter") finishEdit(true); if (event.key === "Escape") finishEdit(false); }}/> : <button type="button" className="case-count" aria-label={groupSize > 1 ? `设置所选 ${groupSize} 个 Case 运行次数` : `修改 ${name} 运行次数`} onClick={() => beginEdit(name)}>×{amount}</button>)}</div>; })}{drag && <i className="selection-box" style={{ left: drag.left, top: drag.top, width: drag.width, height: drag.height }}/>}</div></fieldset>;
}

function pluginInputs(plugin, values) {
  const names = new Set();
  for (const field of plugin?.fields || []) {
    names.add(field.name);
    if (field.count_field) names.add(field.count_field);
    if (field.default_count_field) names.add(field.default_count_field);
  }
  return Object.fromEntries([...names].filter((name) => Object.prototype.hasOwnProperty.call(values, name)).map((name) => [name, values[name]]));
}

function pathLeaf(value) { const parts = value.split("/"); return parts[parts.length - 1]; }

function InspectionItems({ items, error }) {
  if (error) return <div className="inspection-error" role="alert"><TriangleAlert/><span>{error}</span></div>;
  if (!items.length) return null;
  return <div className="inspection-grid">{items.map((item) => <div className={`inspection-item severity-${item.severity}`} key={item.name}><span>{item.label || item.name}</span><code>{item.value}</code><Hint label={item.message}><span className="inspection-state" tabIndex={item.message ? 0 : -1} aria-label={item.severity === "ok" ? "检查通过" : item.severity}>{item.severity === "error" || item.severity === "warning" ? <TriangleAlert/> : <Check/>}</span></Hint></div>)}</div>;
}

function RunFields({ plugin, filePath, values, setValues, inspectionControllerRef }) {
  const [inspection, setInspection] = useState([]); const [inspectionError, setInspectionError] = useState("");
  const update = (field, raw) => setValues({ ...values, [field.name]: field.type === "integer" ? Number(raw) : field.type === "string-list" ? raw.split(",").map((item) => item.trim()).filter(Boolean) : raw });
  const inputs = useMemo(() => pluginInputs(plugin, values), [plugin, values]);
  useEffect(() => { const controller = new AbortController(); inspectionControllerRef.current = controller; let active = true; const timer = setTimeout(() => api.inspectConfig(filePath, inputs, controller.signal).then((result) => { if (active) { setInspection(result.items); setInspectionError(""); } }).catch((error) => { if (active && error.name !== "AbortError") setInspectionError(error.message); }), 120); return () => { active = false; clearTimeout(timer); controller.abort(); if (inspectionControllerRef.current === controller) inspectionControllerRef.current = undefined; }; }, [filePath, inputs, inspectionControllerRef]);
  return <div className="run-surface"><InspectionItems items={inspection} error={inspectionError}/><div className="run-fields">{plugin?.fields.map((field) => field.type === "case-picker" ? <CasePicker field={field} key={field.name} filePath={filePath} values={values} discoverValues={inputs} setValues={setValues}/> : field.type === "json" ? <details className="advanced-field" key={field.name}><summary>运行参数<i/></summary><label><span>{field.label}</span><textarea value={typeof values[field.name] === "string" ? values[field.name] : JSON.stringify(values[field.name] || {}, null, 2)} onChange={(event) => update(field, event.target.value)}/></label></details> : <label className={`run-field field-${field.type}`} key={field.name}><span>{field.label || field.name}</span><input required={field.required} inputMode={["integer", "seed"].includes(field.type) ? "numeric" : undefined} type={field.type === "integer" ? "number" : "text"} value={Array.isArray(values[field.name]) ? values[field.name].join(", ") : values[field.name] ?? field.default ?? ""} onChange={(event) => update(field, event.target.value)}/>{field.type === "string-list" && <small>用逗号分隔</small>}</label>)}</div></div>;
}

function readConfigMemory() {
  try { return JSON.parse(sessionStorage.getItem("localflow-run-context") || "{}") || {}; } catch { return {}; }
}

function Config({ theme }) {
  const filePathRef = useRef();
  const inspectionControllerRef = useRef();
  const contentRef = useRef("");
  const baseContentRef = useRef("");
  const localVersionsRef = useRef(new Map());
  const [files, setFiles] = useState([]); const [diagnostics, setDiagnostics] = useState({}); const [plugins, setPlugins] = useState([]); const [file, setFile] = useState(); const [selectedPath, setSelectedPath] = useState(); const [clipboard, setClipboard] = useState(); const [content, setContent] = useState(""); const [mode, setMode] = useState("edit"); const [values, setValues] = useState({}); const [notice, setNotice] = useState(""); const [runStatus, setRunStatus] = useState("idle"); const [conflict, setConflict] = useState(); const [createOpen, setCreateOpen] = useState(false); const [createKind, setCreateKind] = useState("file"); const [createPath, setCreatePath] = useState(""); const [createPlugin, setCreatePlugin] = useState(""); const [deleting, setDeleting] = useState(false); const [treeOpen, setTreeOpen] = useState(false); const [treeSize, setTreeSize] = useState({ width: 260, height: 600 }); const treeHost = useRef();
  const reload = useCallback(async () => { const result = await api.workspace(); setFiles(result.items); setDiagnostics(result.diagnostics || {}); return result.items; }, []);
  const open = useCallback(async (path, restore = true) => { const value = await api.workspaceFile(path); const stored = restore ? readConfigMemory().files?.[path] : undefined; const remembered = stored?.version === value.version ? stored : undefined; filePathRef.current = path; contentRef.current = value.content; baseContentRef.current = value.content; setSelectedPath(path); setFile(value); setContent(value.content); setValues(remembered?.values || value.document || {}); setMode(path.startsWith("config/") ? (remembered?.mode || (value.diagnosis?.runnable ? "use" : "edit")) : "edit"); setRunStatus("idle"); setNotice(""); setTreeOpen(false); setConflict(undefined); }, []);
  useEffect(() => { Promise.all([reload(), api.plugins().then((result) => { setPlugins(result.items); setCreatePlugin(result.items[0]?.name || ""); })]).then(([items]) => { const remembered = readConfigMemory().path; const paths = items.filter((item) => item.kind === "file").map((item) => item.path); const target = paths.includes(remembered) ? remembered : paths[0]; if (target) open(target); }).catch((error) => setNotice(error.message)); }, [reload, open]);
  useEffect(() => { if (!file?.path) return; const memory = readConfigMemory(); sessionStorage.setItem("localflow-run-context", JSON.stringify({ ...memory, path: file.path, files: { ...(memory.files || {}), [file.path]: { version: file.version, mode, values } } })); }, [file?.path, file?.version, mode, values]);
  useEffect(() => { filePathRef.current = file?.path; }, [file?.path]);
  useEffect(() => { contentRef.current = content; }, [content]);
  useEffect(() => { if (!notice.startsWith("已")) return; const timer = setTimeout(() => setNotice((current) => current === notice ? "" : current), 2800); return () => clearTimeout(timer); }, [notice]);
  useEffect(() => { if (runStatus !== "accepted") return; const timer = setTimeout(() => setRunStatus("idle"), 1600); return () => clearTimeout(timer); }, [runStatus]);
  useEffect(() => { const observer = new ResizeObserver(([entry]) => setTreeSize({ width: Math.floor(entry.contentRect.width), height: Math.floor(entry.contentRect.height) })); if (treeHost.current) observer.observe(treeHost.current); return () => observer.disconnect(); }, []);
  useEffect(() => { const events = new EventSource("/api/v1/events"); const changed = (event) => { const data = JSON.parse(event.data); const path = `config/${data.path}`; if (localVersionsRef.current.get(path) === data.version) { localVersionsRef.current.delete(path); return; } reload().then((items) => { if (path !== filePathRef.current || !items.some((item) => item.path === path)) return undefined; if (contentRef.current !== baseContentRef.current) { setNotice("文件已在外部变化，请先保存或重新打开"); return undefined; } return open(path).then(() => setNotice("已同步外部修改")); }).catch((error) => setNotice(`同步失败：${error.message}`)); }; const removed = () => reload().then((items) => { if (filePathRef.current && !items.some((item) => item.path === filePathRef.current)) { setFile(undefined); filePathRef.current = undefined; } }); const pluginChanged = (event) => { const data = JSON.parse(event.data); return Promise.all([reload(), api.plugins().then((result) => setPlugins(result.items))]).then(([items]) => { const current = filePathRef.current; const relative = current?.replace(/^plugins\//, ""); if (!current?.startsWith("plugins/") || !data.paths?.includes(relative) || !items.some((item) => item.path === current)) return undefined; if (contentRef.current !== baseContentRef.current) { setNotice("文件已在外部变化，请先保存或重新打开"); return undefined; } return open(current).then(() => setNotice("已同步外部修改")); }); }; events.addEventListener("config.changed", changed); events.addEventListener("config.deleted", removed); events.addEventListener("plugins.changed", pluginChanged); events.addEventListener("config.invalid", (event) => { const data = JSON.parse(event.data); if (`config/${data.path}` === filePathRef.current) setNotice(`配置无效：${data.error}`); }); return () => events.close(); }, [reload, open]);
  const selectedPlugin = plugins.find((item) => item.name === file?.plugin);
  const runDisabled = selectedPlugin?.fields.some((field) => field.required && (values[field.name] == null || values[field.name] === "" || (Array.isArray(values[field.name]) && values[field.name].length === 0)));
  const move = async (source, target) => { const movesOpenFile = filePathRef.current === source || filePathRef.current?.startsWith(`${source}/`); inspectionControllerRef.current?.abort(); if (movesOpenFile) filePathRef.current = target + filePathRef.current.slice(source.length); await api.moveWorkspace(source, target); await reload(); setSelectedPath(target); if (movesOpenFile) await open(filePathRef.current); setNotice("已移动"); };
  const rename = async ({ id, name }) => { const source = id.replace(/^folder:/, ""); if (["config", "plugins"].includes(source)) return; const parent = source.slice(0, source.lastIndexOf("/") + 1); await move(source, `${parent}${name}`); };
  const onMove = async ({ dragIds, parentId }) => { const targetFolder = parentId?.replace(/^folder:/, "") || ""; for (const raw of dragIds) { const source = raw.replace(/^folder:/, ""); await move(source, `${targetFolder}/${pathLeaf(source)}`); } };
  const save = async () => { try { const saved = await api.saveWorkspaceFile(file.path, content, file.version); localVersionsRef.current.set(saved.path, saved.version); await open(saved.path, false); setNotice("已保存"); } catch (error) { if (error.status === 412) { setConflict(await api.workspaceFile(file.path)); setNotice("文件已变化，请比较后选择"); } else setNotice(`保存失败：${error.message}`); } };
  const run = async () => { setRunStatus("submitting"); setNotice(""); try { const result = await api.runConfig(file.path.replace(/^config\//, ""), pluginInputs(selectedPlugin, values)); setRunStatus("accepted"); setNotice(`已加入 ${result.count} 个任务`); } catch (error) { setRunStatus("idle"); setNotice(`运行失败：${error.message}`); } };
  const selectedEntry = files.find((item) => item.path === selectedPath); const selectedFolder = selectedEntry?.kind === "directory" ? selectedPath : selectedPath?.slice(0, selectedPath.lastIndexOf("/"));
  const create = async () => { try { const base = selectedFolder || "config"; let path = createPath.includes("/") ? createPath : `${base}/${createPath}`; if (createKind === "directory") await api.createDirectory(path); else if (path.startsWith("config/")) { const relative = path.replace(/^config\//, ""); const named = /\.(?:ya?ml|json|toml)$/i.test(relative) ? relative : `${relative}.yaml`; const saved = await api.createFile(named, createPlugin); path = `config/${saved.path}`; } else { if (!/\.(?:py|md)$/i.test(path)) path += ".py"; await api.saveWorkspaceFile(path, "", "*"); } setCreateOpen(false); setCreatePath(""); await reload(); setSelectedPath(path); if (createKind === "file") await open(path, false); setNotice("已创建"); } catch (error) { setNotice(`创建失败：${error.message}`); } };
  const remove = async () => { try { await api.deleteWorkspace(selectedPath); setDeleting(false); if (filePathRef.current === selectedPath || filePathRef.current?.startsWith(`${selectedPath}/`)) { setFile(undefined); filePathRef.current = undefined; } await reload(); setSelectedPath(undefined); setNotice("已删除"); } catch (error) { setNotice(`删除失败：${error.message}`); } };
  const place = async () => { if (!clipboard || !selectedFolder) return; const target = `${selectedFolder}/${pathLeaf(clipboard.path)}`; try { if (clipboard.mode === "cut") { await move(clipboard.path, target); setClipboard(undefined); } else { await api.copyWorkspace(clipboard.path, target); await reload(); setSelectedPath(target); setNotice("已粘贴"); } } catch (error) { setNotice(`粘贴失败：${error.message}`); } };
  const keyAction = (event) => { if (!selectedPath || ["INPUT", "TEXTAREA"].includes(event.target.tagName) || event.target.closest(".monaco-editor")) return; const modifier = event.ctrlKey || event.metaKey; if (modifier && ["c", "x", "v"].includes(event.key.toLowerCase())) { event.preventDefault(); if (event.key.toLowerCase() === "v") place(); else setClipboard({ path: selectedPath, mode: event.key.toLowerCase() === "x" ? "cut" : "copy" }); } else if (event.key === "F2") { event.preventDefault(); document.querySelector(`[data-file="${CSS.escape(selectedEntry?.kind === "directory" ? `folder:${selectedPath}` : selectedPath)}"]`)?.dispatchEvent(new MouseEvent("dblclick", { bubbles: true })); } else if (event.key === "Delete" && !selectedEntry?.readonly) { event.preventDefault(); setDeleting(true); } };
  const editorTheme = theme === "dark" ? "localflow-dark" : "vs";
  const editorLanguage = file?.path.endsWith(".py") ? "python" : file?.path.endsWith(".md") ? "markdown" : file?.path.endsWith("json") ? "json" : file?.path.endsWith("toml") ? "ini" : "yaml";
  return <div className="config-explorer" tabIndex="0" onKeyDown={keyAction}>
    <aside className="explorer"><header><span>资源</span><div>
      <button className="icon" aria-label="新建文件" title="新建文件" onClick={() => { setCreateKind("file"); setCreateOpen(true); }}><Plus/></button>
      <button className="icon" aria-label="新建目录" title="新建目录" onClick={() => { setCreateKind("directory"); setCreateOpen(true); }}><FolderPlus/></button>
      <button className="icon" aria-label="复制" title="复制" disabled={!selectedPath} onClick={() => setClipboard({ path: selectedPath, mode: "copy" })}><Copy/></button>
      <button className="icon" aria-label="剪切" title="剪切" disabled={!selectedPath || selectedEntry?.readonly} onClick={() => setClipboard({ path: selectedPath, mode: "cut" })}><Scissors/></button>
      <button className="icon" aria-label="粘贴" title="粘贴" disabled={!clipboard || !selectedFolder} onClick={place}><ClipboardPaste/></button>
      <button className="icon" aria-label="重命名" title="重命名" disabled={!selectedPath || selectedEntry?.readonly} onClick={() => document.querySelector(`[data-file="${CSS.escape(selectedEntry?.kind === "directory" ? `folder:${selectedPath}` : selectedPath)}"]`)?.dispatchEvent(new MouseEvent("dblclick", { bubbles: true }))}><Pencil/></button>
      <button className="icon danger-icon" aria-label="删除" title="删除" disabled={!selectedPath || selectedEntry?.readonly} onClick={() => setDeleting(true)}><Trash2/></button>
    </div></header><div className="tree-host" ref={treeHost}><Tree data={buildTree(files, diagnostics)} width={treeSize.width} height={treeSize.height} rowHeight={32} indent={16} overscanCount={8} openByDefault selection={selectedEntry?.kind === "directory" ? `folder:${selectedPath}` : selectedPath} onSelect={(nodes) => { const node = nodes[0]; if (!node) return; setSelectedPath(node.data.path); if (!node.isInternal) open(node.data.path); }} onRename={rename} onMove={onMove}>{TreeNode}</Tree></div></aside>
    <section className="config-workbench">{notice && <p className="notice" role="status">{notice}</p>}{file ? <><header className="workbench-header"><div><FileCode2/><span>{visibleConfigName(pathLeaf(file.path))}</span></div><div className="workbench-actions">{mode === "edit" && file.diagnosis?.runnable && <button className="secondary" onClick={() => { setContent(file.content); setMode("use"); }}>取消</button>}{mode === "use" && <button className="secondary" onClick={() => setMode("edit")}><FilePenLine/>编辑</button>}{mode === "edit" ? <button className="primary" onClick={save}>保存</button> : <Hint content={runStatus === "submitting" ? "正在创建任务" : runStatus === "accepted" ? "任务已创建" : "运行"}><button className={`primary icon-only run-action ${runStatus}`} aria-label={runStatus === "accepted" ? "任务已创建" : "运行"} data-run-state={runStatus} disabled={runDisabled || runStatus === "submitting"} onClick={run}>{runStatus === "accepted" ? <Check/> : runStatus === "submitting" ? <Activity/> : <Play/>}</button></Hint>}</div></header>{file.diagnosis?.errors?.length > 0 && <div className="config-diagnosis" role="alert"><b>配置有误</b><ul>{file.diagnosis.errors.map((item) => <li key={item}>{item}</li>)}</ul></div>}{mode === "use" ? <div className="use-config"><RunFields key={file.version} plugin={selectedPlugin} filePath={file.path.replace(/^config\//, "")} values={values} setValues={setValues} inspectionControllerRef={inspectionControllerRef}/></div> : conflict ? <div className="conflict"><div><b>最新版本</b><span>你的编辑</span><button onClick={() => { setFile(conflict); setContent(conflict.content); setConflict(undefined); }}>采用最新版本</button></div><DiffEditor height="calc(100vh - 120px)" original={conflict.content} modified={content} language={editorLanguage} theme={editorTheme} options={{ readOnly: true, automaticLayout: true }}/></div> : <Editor height="calc(100vh - 76px)" language={editorLanguage} theme={editorTheme} value={content} onChange={(value) => setContent(value || "")} options={{ minimap: { enabled: false }, automaticLayout: true, padding: { top: 16 } }}/>}</> : <div className="empty-workbench"><FileCode2/></div>}</section>
    {createOpen && <div className="dialog-backdrop"><div role="dialog" aria-modal="true" aria-labelledby="create-title" className="dialog"><header><h2 id="create-title">{createKind === "directory" ? "新建目录" : "新建文件"}</h2><button className="icon" aria-label="关闭" onClick={() => setCreateOpen(false)}><X/></button></header><label><span>名称</span><input autoFocus value={createPath} onChange={(event) => setCreatePath(event.target.value)}/></label>{createKind === "file" && (selectedFolder || "config").startsWith("config") && <label><span>插件</span><select value={createPlugin} onChange={(event) => setCreatePlugin(event.target.value)}>{plugins.map((item) => <option key={item.name} value={item.name}>{item.title}</option>)}</select></label>}<footer><button className="secondary" onClick={() => setCreateOpen(false)}>取消</button><button className="primary" disabled={!createPath.trim()} onClick={create}>创建</button></footer></div></div>}
    {deleting && <div className="dialog-backdrop"><div role="alertdialog" aria-modal="true" className="dialog"><h2>删除 {pathLeaf(selectedPath || "")}？</h2><p>此操作无法撤销。</p><footer><button className="secondary" onClick={() => setDeleting(false)}>取消</button><button className="danger compact" onClick={remove}>删除</button></footer></div></div>}
  </div>;
}

function localInputValue(value) { const date = new Date(value); return new Date(date.getTime() - date.getTimezoneOffset() * 60_000).toISOString().slice(0, 19); }
function SettingsPage({ theme, setTheme, role, onLogin }) {
  const [serverTime, setServerTime] = useState(); const [referenceTime, setReferenceTime] = useState(""); const [notice, setNotice] = useState(""); const [dirty, setDirty] = useState(false); const [editing, setEditing] = useState(false); const [, setTick] = useState(0);
  const [adminKey, setAdminKey] = useState(""); const [loginNotice, setLoginNotice] = useState(""); const [loggingIn, setLoggingIn] = useState(false);
  const loadTime = useCallback(async () => { const state = await api.status(); const value = state.time.wall_clock; setServerTime({ value: new Date(value), observed: Date.now() }); setReferenceTime(localInputValue(value)); }, []);
  useEffect(() => { loadTime().catch((error) => setNotice(`读取失败：${error.message}`)); }, [loadTime]); useEffect(() => { const timer = setInterval(() => setTick((old) => old + 1), 1000); return () => clearInterval(timer); }, []);
  const current = serverTime ? new Date(serverTime.value.getTime() + Date.now() - serverTime.observed) : undefined;
  const displayedTime = editing ? referenceTime : current ? localInputValue(current) : "";
  useEffect(() => { if (!dirty || !referenceTime) return; const timer = setTimeout(async () => { try { await api.adjustTime(new Date(referenceTime).toISOString()); setDirty(false); setEditing(false); await loadTime(); setNotice(""); } catch (error) { setNotice(`校准失败：${error.message}`); } }, 600); return () => clearTimeout(timer); }, [dirty, referenceTime, loadTime]);
  const login = async (event) => { event.preventDefault(); if (!adminKey.trim() || loggingIn) return; setLoggingIn(true); setLoginNotice(""); try { await api.login(adminKey.trim()); setAdminKey(""); await onLogin(); } catch (error) { setLoginNotice(error.status === 401 ? "秘钥不正确" : `登录失败：${error.message}`); } finally { setLoggingIn(false); } };
  return <div className="settings"><section className="settings-panel"><div className="setting-row"><span>主题</span><div className="theme-choice" role="group" aria-label="主题"><button className={theme === "light" ? "active" : ""} aria-pressed={theme === "light"} onClick={() => setTheme("light")}><Sun/>浅色</button><button className={theme === "dark" ? "active" : ""} aria-pressed={theme === "dark"} onClick={() => setTheme("dark")}><Moon/>深色</button></div></div>{role !== "admin" && <form className="setting-row login-row" onSubmit={login}><label htmlFor="web-admin-key">秘钥登录</label><span className="login-control"><span className="secret-entry"><input id="web-admin-key" aria-label="管理员秘钥" type="password" autoComplete="current-password" value={adminKey} onChange={(event) => setAdminKey(event.target.value)}/><button className="primary" type="submit" disabled={!adminKey.trim() || loggingIn}>{loggingIn ? "登录中" : "登录"}</button></span>{loginNotice && <small role="alert">{loginNotice}</small>}</span></form>}{role === "admin" && <label className="setting-row"><span>时间校准</span><span className="time-control"><input aria-label="时间校准" type="datetime-local" step="1" value={displayedTime} onFocus={() => { setReferenceTime(displayedTime); setEditing(true); }} onChange={(event) => { setReferenceTime(event.target.value); setDirty(true); }}/>{notice && <small>{notice}</small>}</span></label>}</section></div>;
}

export default function App() {
  useUiRevision();
  const [page, setPage] = useState("tasks"); const [status, setStatus] = useState(); const [tasks, setTasks] = useState([]); const [opened, setOpened] = useState(); const [fresh, setFresh] = useState(new Set()); const [error, setError] = useState(""); const [theme, setTheme] = useTheme();
  const refresh = useCallback(async () => { try { const [state, result] = await Promise.all([api.status(), api.tasks()]); setStatus(state); setTasks(result.items); setError(""); } catch (reason) { setError(reason.message); } }, []); useEffect(() => { refresh(); const timer = setInterval(refresh, 3000); return () => clearInterval(timer); }, [refresh]);
  useEffect(() => { if (status && status.role !== "admin" && !["tasks", "settings"].includes(page)) setPage("tasks"); }, [status, page]); useEffect(() => { setFresh(new Set(tasks.filter((task) => task.newly_completed).map((task) => task.id))); }, [tasks]);
  const groups = useMemo(() => ({ running: tasks.filter((task) => ["starting", "running", "stopping"].includes(task.state)), queued: tasks.filter((task) => task.state === "queued"), history: tasks.filter((task) => finalStates.has(task.state)) }), [tasks]); const acknowledge = async (id) => { if (status?.role !== "admin") return; setFresh((old) => { const next = new Set(old); next.delete(id); return next; }); try { await api.acknowledge(id); } catch { /* optimistic */ } };
  const navigation = [["tasks", "任务", ListChecks], ...(status?.role === "admin" ? [["config", "运行", Play], ["terminal", "终端", TerminalSquare]] : []), ["settings", "设置", Settings2]]; const definitions = [["running", "正在运行", Activity], ["queued", "等待队列", Clock3], ["history", "历史任务", ListChecks]].filter(([key]) => groups[key].length > 0);
  const moveNavigation = (event, index) => { if (!["ArrowDown", "ArrowUp", "Home", "End"].includes(event.key)) return; event.preventDefault(); const next = event.key === "Home" ? 0 : event.key === "End" ? navigation.length - 1 : (index + (event.key === "ArrowDown" ? 1 : -1) + navigation.length) % navigation.length; setPage(navigation[next][0]); requestAnimationFrame(() => document.getElementById(`nav-${navigation[next][0]}`)?.focus()); };
  const renderTask = (key, task, count = 1) => <TaskItem task={task} count={count} key={task.id} role={status?.role} theme={theme} open={opened === task.id} fresh={key === "history" && fresh.has(task.id)} toggle={() => setOpened((old) => old === task.id ? undefined : task.id)} ack={() => acknowledge(task.id)} interrupt={async () => { await api.interrupt(task.id); refresh(); }}/>;
  return <div className="app-shell"><aside className="top"><nav role="tablist" aria-label="主导航" aria-orientation="vertical">{navigation.map(([id, text, Icon], index) => <button id={`nav-${id}`} role="tab" aria-selected={page === id} aria-controls="page-panel" tabIndex={page === id ? 0 : -1} className={page === id ? "active" : ""} onClick={() => setPage(id)} onKeyDown={(event) => moveNavigation(event, index)} key={id}><Icon/><span>{text}</span></button>)}</nav></aside><div className="app-content">{error && <p className="global-error">{error}</p>}<main id="page-panel" role="tabpanel" aria-labelledby={`nav-${page}`} tabIndex="0">{page === "tasks" && <section className="workspace">{definitions.length === 0 ? <div className="tasks-empty"><ListChecks/><p>暂无任务</p></div> : definitions.map(([key, title, Icon]) => <section className="group" key={key}><h2><Icon/>{title}<span>{groups[key].length}</span></h2><div>{key === "queued" ? <QueueTasks tasks={groups[key]} renderTask={(task, count) => renderTask(key, task, count)}/> : groups[key].map((task) => renderTask(key, task))}</div></section>)}</section>}{status?.role === "admin" && <><div hidden={page !== "config"}><Config theme={theme}/></div>{page === "terminal" && <TerminalPage tasks={tasks} role={status?.role} theme={theme}/>}</>}{page === "settings" && <SettingsPage theme={theme} setTheme={setTheme} role={status?.role} onLogin={refresh}/>}</main></div></div>;
}
