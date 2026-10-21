const API = "/api/v1";
let csrfToken = "";
const configPath = (path) => path.split("/").map(encodeURIComponent).join("/");
export async function request(path, options = {}) {
  const { signal, timeout = 15000, ...init } = options;
  const controller = new AbortController();
  const abort = () => controller.abort();
  if (signal?.aborted) abort();
  else signal?.addEventListener("abort", abort, { once: true });
  let timedOut = false;
  const timer = setTimeout(() => { timedOut = true; abort(); }, timeout);
  try {
  const method = (options.method || "GET").toUpperCase();
  const response = await fetch(`${API}${path}`, { credentials: "same-origin", cache: "no-store", ...init, signal: controller.signal, headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(method !== "GET" && csrfToken ? { "X-CSRF-Token": csrfToken } : {}), ...options.headers } });
  if (!response.ok) { const error = new Error(await response.text() || `${response.status}`); error.status = response.status; throw error; }
  return response.status === 204 ? null : await response.json();
  } catch (error) {
    if (timedOut) throw new Error("请求超时，请检查服务连接和操作结果");
    throw error;
  } finally {
    clearTimeout(timer);
    signal?.removeEventListener("abort", abort);
  }
}
export const api = {
  status: async (signal) => { const result = await request("/system/status", {signal}); if (result.role === "admin" && !csrfToken) { const session = await request("/auth/session", {signal}); csrfToken = session.csrf_token; } return result; }, tasks: (query = "", signal) => request(`/tasks?limit=200${query ? `&${query}` : ""}`, {signal}),
  interrupt: (id) => request(`/tasks/${id}/interrupt`, { method: "POST" }), acknowledge: (id) => request(`/tasks/${id}/acknowledgements`, { method: "POST" }),
  login: async (key) => { const result = await request("/auth/local-sessions", { method: "POST", body: JSON.stringify({ key }) }); csrfToken = result.csrf_token; return result; }, templates: () => request("/templates"), plugins: () => request("/plugins"),
  runTemplate: (name, values) => request("/batches", { method: "POST", body: JSON.stringify({ template: name, values }) }), files: () => request("/config/files"), file: (path) => request(`/config/files/${configPath(path)}`),
  discoverTemplate: (name, values) => request(`/templates/${name}/discover`, { method: "POST", body: JSON.stringify(values) }),
  discoverConfig: (path, inputs) => request(`/config/files/${configPath(path)}/discover`, { method: "POST", body: JSON.stringify({ inputs }) }),
  recentConfigs: () => request("/config/recent"),
  diagnoseConfig: (path, content, signal) => request(`/config/files/${configPath(path)}/diagnosis`, { method: "POST", body: JSON.stringify({ content }), signal }),
  inspectConfig: (path, inputs, signal) => request(`/config/files/${configPath(path)}/inspection`, { method: "POST", body: JSON.stringify({ inputs }), signal }),
  saveFile: (path, content, version) => request(`/config/files/${configPath(path)}`, { method: "PUT", headers: { "If-Match": version }, body: JSON.stringify({ content }) }),
  createFile: (path, plugin) => request("/config/files", { method: "POST", body: JSON.stringify({ path, plugin }) }),
  moveFile: (path, target, version) => request(`/config/files/${configPath(path)}/move`, { method: "POST", body: JSON.stringify({ target, version }) }),
  deleteFile: (path, version) => request(`/config/files/${configPath(path)}`, { method: "DELETE", headers: { "If-Match": version } }),
  runConfig: (path, inputs) => request(`/config/files/${configPath(path)}/runs`, { method: "POST", body: JSON.stringify({ inputs }) }),
  workspace: () => request("/workspace"), workspaceFile: (path) => request(`/workspace/files/${configPath(path)}`),
  saveWorkspaceFile: (path, content, version) => request(`/workspace/files/${configPath(path)}`, { method: "PUT", headers: { "If-Match": version }, body: JSON.stringify({ content }) }),
  createDirectory: (path) => request("/workspace/directories", { method: "POST", body: JSON.stringify({ path }) }),
  moveWorkspace: (source, target) => request("/workspace/moves", { method: "POST", body: JSON.stringify({ source, target }) }),
  copyWorkspace: (source, target) => request("/workspace/copies", { method: "POST", body: JSON.stringify({ source, target }) }),
  deleteWorkspace: (path) => request(`/workspace/entries/${configPath(path)}`, { method: "DELETE" }),
  terminalInput: (id, data, encoding = "utf-8") => request(`/tasks/${id}/terminal/input`, { method: "POST", body: JSON.stringify({ data, encoding }) }),
  terminalControl: (id, key) => request(`/tasks/${id}/terminal/controls`, { method: "POST", body: JSON.stringify({ key }) }),
  terminalResize: (id, rows, cols) => request(`/tasks/${id}/terminal/resize`, { method: "POST", body: JSON.stringify({ rows, cols }) }),
  searchLog: (id, query) => request(`/tasks/${id}/logs/search?${new URLSearchParams({ query })}`),
  logWindow: (id, values) => request(`/tasks/${id}/logs/window?${new URLSearchParams(values)}`),
  adjustTime: (reference_time) => request("/system/time-adjustments", { method: "POST", body: JSON.stringify({ reference_time }) }),
  shutdown: async () => {
    // Another tab can replace the shared cookie after this page cached its token.
    const session = await request("/auth/session");
    return request("/system/shutdown", { method: "POST", headers: { "X-CSRF-Token": session.csrf_token } });
  },
  openapi: () => request("/openapi"),
  uiRevision: (signal) => request("/system/ui-revision", {signal}),
};
