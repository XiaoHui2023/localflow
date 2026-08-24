const API = "/api/v1";
let csrfToken = "";
export async function request(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const response = await fetch(`${API}${path}`, { credentials: "same-origin", ...options, headers: { ...(options.body ? { "Content-Type": "application/json" } : {}), ...(method !== "GET" && csrfToken ? { "X-CSRF-Token": csrfToken } : {}), ...options.headers } });
  if (!response.ok) { const error = new Error(await response.text() || `${response.status}`); error.status = response.status; throw error; }
  return response.status === 204 ? null : response.json();
}
export const api = {
  status: async () => { const result = await request("/system/status"); if (result.role === "admin" && !csrfToken) { const session = await request("/auth/session"); csrfToken = session.csrf_token; } return result; }, tasks: (query = "") => request(`/tasks?limit=200${query ? `&${query}` : ""}`),
  interrupt: (id) => request(`/tasks/${id}/interrupt`, { method: "POST" }), acknowledge: (id) => request(`/tasks/${id}/acknowledgements`, { method: "POST" }),
  login: async (code) => { const result = await request("/auth/local-sessions", { method: "POST", body: JSON.stringify({ code }) }); csrfToken = result.csrf_token; return result; }, templates: () => request("/templates"),
  runTemplate: (name, values) => request("/batches", { method: "POST", body: JSON.stringify({ template: name, values }) }), files: () => request("/config/files"), file: (path) => request(`/config/files/${path}`),
  discoverTemplate: (name, values) => request(`/templates/${name}/discover`, { method: "POST", body: JSON.stringify(values) }),
  saveFile: (path, content, version) => request(`/config/files/${path}`, { method: "PUT", headers: { "If-Match": version }, body: JSON.stringify({ content }) }),
  adjustTime: (reference_time) => request("/system/time-adjustments", { method: "POST", body: JSON.stringify({ reference_time }) }),
};
