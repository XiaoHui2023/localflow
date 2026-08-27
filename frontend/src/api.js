const API = "/api/v1";
let csrfToken = "";
const configPath = (path) => path.split("/").map(encodeURIComponent).join("/");
export async function request(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const response = await fetch(`${API}${path}`, { credentials: "same-origin", cache: "no-store", ...options, headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(method !== "GET" && csrfToken ? { "X-CSRF-Token": csrfToken } : {}), ...options.headers } });
  if (!response.ok) { const error = new Error(await response.text() || `${response.status}`); error.status = response.status; throw error; }
  return response.status === 204 ? null : response.json();
}
export const api = {
  status: async () => { const result = await request("/system/status"); if (result.role === "admin" && !csrfToken) { const session = await request("/auth/session"); csrfToken = session.csrf_token; } return result; }, tasks: (query = "") => request(`/tasks?limit=200${query ? `&${query}` : ""}`),
  interrupt: (id) => request(`/tasks/${id}/interrupt`, { method: "POST" }), acknowledge: (id) => request(`/tasks/${id}/acknowledgements`, { method: "POST" }),
  login: async (key) => { const result = await request("/auth/local-sessions", { method: "POST", body: JSON.stringify({ key }) }); csrfToken = result.csrf_token; return result; }, templates: () => request("/templates"), plugins: () => request("/plugins"),
  runTemplate: (name, values) => request("/batches", { method: "POST", body: JSON.stringify({ template: name, values }) }), files: () => request("/config/files"), file: (path) => request(`/config/files/${configPath(path)}`),
  discoverTemplate: (name, values) => request(`/templates/${name}/discover`, { method: "POST", body: JSON.stringify(values) }),
  discoverConfig: (path, inputs) => request(`/config/files/${configPath(path)}/discover`, { method: "POST", body: JSON.stringify({ inputs }) }),
  saveFile: (path, content, version) => request(`/config/files/${configPath(path)}`, { method: "PUT", headers: { "If-Match": version }, body: JSON.stringify({ content }) }),
  createFile: (path, plugin) => request("/config/files", { method: "POST", body: JSON.stringify({ path, plugin }) }),
  moveFile: (path, target, version) => request(`/config/files/${configPath(path)}/move`, { method: "POST", body: JSON.stringify({ target, version }) }),
  deleteFile: (path, version) => request(`/config/files/${configPath(path)}`, { method: "DELETE", headers: { "If-Match": version } }),
  runConfig: (path, inputs) => request(`/config/files/${configPath(path)}/runs`, { method: "POST", body: JSON.stringify({ inputs }) }),
  terminalInput: (id, data, encoding = "utf-8") => request(`/tasks/${id}/terminal/input`, { method: "POST", body: JSON.stringify({ data, encoding }) }),
  terminalControl: (id, key) => request(`/tasks/${id}/terminal/controls`, { method: "POST", body: JSON.stringify({ key }) }),
  terminalResize: (id, rows, cols) => request(`/tasks/${id}/terminal/resize`, { method: "POST", body: JSON.stringify({ rows, cols }) }),
  adjustTime: (reference_time) => request("/system/time-adjustments", { method: "POST", body: JSON.stringify({ reference_time }) }),
  openapi: () => request("/openapi"),
  uiRevision: () => request("/system/ui-revision"),
};
