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
