export async function fetchStatus() {
  const res = await fetch("/api/status");
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}

export async function fetchConfig() {
  const res = await fetch("/api/config");
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}

export async function postRun(body = {}) {
  const res = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}

export async function fetchProgress() {
  const res = await fetch("/api/progress");
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}

export async function fetchResult() {
  const res = await fetch("/api/result");
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}

export async function fetchAutomations() {
  const res = await fetch("/api/automations");
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}

export async function fetchScripts() {
  const res = await fetch("/api/scripts");
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}

export async function fetchScript(id) {
  const res = await fetch(`/api/scripts/${encodeURIComponent(id)}`);
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}

export async function fetchScriptTerminal(id) {
  const res = await fetch(`/api/scripts/${encodeURIComponent(id)}/terminal`);
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}

export async function patchScriptVariables(id, body) {
  const res = await fetch(`/api/scripts/${encodeURIComponent(id)}/variables`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}

export async function fetchBlueprints(scriptId) {
  const query = scriptId ? `?script_id=${encodeURIComponent(scriptId)}` : "";
  const res = await fetch(`/api/blueprints${query}`);
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}

export async function createBlueprint(body) {
  const res = await fetch("/api/blueprints", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}

export async function fetchBlueprint(id) {
  const res = await fetch(`/api/blueprints/${encodeURIComponent(id)}`);
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}

export async function deleteBlueprint(id) {
  const res = await fetch(`/api/blueprints/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}

export async function postBlueprintRun(id) {
  const res = await fetch(`/api/blueprints/${encodeURIComponent(id)}/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: "{}",
  });
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}

export async function fetchRunHistory(scriptId) {
  const query = scriptId ? `?script_id=${encodeURIComponent(scriptId)}` : "";
  const res = await fetch(`/api/history${query}`);
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}

export async function fetchRunHistoryRecord(id) {
  const res = await fetch(`/api/history/${encodeURIComponent(id)}`);
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}

export async function postScriptCancel(id, body = {}) {
  const res = await fetch(`/api/scripts/${encodeURIComponent(id)}/cancel`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}

export async function postScriptStart(id, body = {}) {
  const res = await fetch(`/api/scripts/${encodeURIComponent(id)}/start`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    throw new Error(`status ${res.status}`);
  }
  return res.json();
}
