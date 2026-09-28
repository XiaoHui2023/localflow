import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

const root = process.env.LOCALFLOW_QA_ROOT;
const python = process.env.LOCALFLOW_QA_PYTHON;

async function login(page) {
  await page.goto("/");
  await page.evaluate(async (key) => {
    await fetch("/api/v1/auth/local-sessions", {
      method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ key }),
    });
  }, fs.readFileSync(path.join(root, "secrets/web-admin-key"), "utf8").trim());
  await page.reload();
}

async function createTask(page, name, program) {
  return page.evaluate(async ({ root, python, name, program }) => {
    const session = await (await fetch("/api/v1/auth/session")).json();
    return (await fetch("/api/v1/tasks", {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token },
      body: JSON.stringify({ name, working_directory: root, command: [python, "-u", "-c", program] }),
    })).json();
  }, { root, python, name, program });
}

async function detail(page, id) {
  return page.evaluate(async (id) => (await (await fetch(`/api/v1/tasks/${id}`)).json()), id);
}

for (const repeat of [0, 1]) {
  test(`dense archive reaches its first output without a scrollback gap ${repeat}`, async ({ page }) => {
    test.setTimeout(90_000);
    await page.goto("/");
    await page.evaluate(async (key) => {
      await fetch("/api/v1/auth/local-sessions", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ key }),
      });
    }, fs.readFileSync(path.join(root, "secrets/web-admin-key"), "utf8").trim());
    await page.reload();
    const task = await page.evaluate(async ({ root, python, repeat }) => {
      const session = await (await fetch("/api/v1/auth/session")).json();
      const response = await fetch("/api/v1/tasks", {
        method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token },
        body: JSON.stringify({
          name: `dense-${repeat}`, working_directory: root,
          command: [python, "-u", "-c", "import sys;sys.stdout.write(''.join('dense-%06d\\n' % i for i in range(40000)))"],
        }),
      });
      return response.json();
    }, { root, python, repeat });
    await expect.poll(async () => page.evaluate(async (id) => (
      await (await fetch(`/api/v1/tasks/${id}`)).json()
    ).ended_at, task.task_id)).toBeTruthy();
    await page.waitForTimeout(2200);
    await page.locator("#nav-terminal").click();
    await page.getByRole("button", { name: `dense-${repeat}`, exact: false }).first().click();
    await expect(page.locator(".terminal.hydrated")).toBeVisible();
    let found = false;
    for (let attempt = 0; attempt < 25; attempt += 1) {
      const viewport = page.locator(".terminal-page .xterm-viewport");
      await viewport.evaluate((node) => { node.scrollTop = 0; node.dispatchEvent(new Event("scroll")); });
      await page.waitForTimeout(180);
      await expect(page.locator(".terminal.hydrated")).toBeVisible();
      if ((await page.locator(".terminal-page .xterm-rows").innerText()).includes("dense-000000")) {
        found = true; break;
      }
    }
    expect(found, "first output must be reachable by continuous upward browsing").toBe(true);
    const terminal = page.locator(".terminal.hydrated");
    let previousEnd = Number(await terminal.getAttribute("data-window-end"));
    let reachedTail = false;
    for (let attempt = 0; attempt < 25; attempt += 1) {
      await page.locator(".terminal-page .xterm-viewport").evaluate((node) => {
        node.scrollTop = node.scrollHeight; node.dispatchEvent(new Event("scroll"));
      });
      await page.waitForTimeout(180);
      await expect(terminal).toBeVisible();
      const start = Number(await terminal.getAttribute("data-window-start"));
      const end = Number(await terminal.getAttribute("data-window-end"));
      expect(start, "forward loading must overlap the previous effective end").toBeLessThanOrEqual(previousEnd);
      expect(end).toBeGreaterThanOrEqual(previousEnd);
      previousEnd = end;
      if ((await page.locator(".terminal-page .xterm-rows").innerText()).includes("dense-039999")) {
        reachedTail = true; break;
      }
    }
    expect(reachedTail, "continuous downward browsing reaches the final output").toBe(true);
    const downloaded = await page.request.get(`/api/v1/tasks/${task.task_id}/logs/download`);
    const stored = fs.readFileSync(path.join(root, ".localflow", "logs", task.task_id, "output.log"));
    expect(await downloaded.body()).toEqual(stored);
    expect(downloaded.headers()["x-localflow-output-complete"]).toBe("true");
    await page.getByRole("button", { name: "在终端中查找", exact: true }).click();
    await page.getByRole("textbox", { name: "终端搜索" }).fill("dense-000001");
    await page.getByRole("button", { name: "完整查找", exact: true }).click();
    await page.locator(".terminal-search-results li button").first().click();
    await expect(terminal).toBeVisible();
    await expect(page.locator(".terminal-page .xterm-rows")).toContainText("dense-000001");
    // Selecting an archive hit closes the finder and gives the terminal focus.
    await expect(page.getByRole("textbox", { name: "终端搜索" })).toHaveCount(0);
    const oldColumns = Number(await terminal.getAttribute("data-columns"));
    await page.setViewportSize({ width: 650, height: 960 });
    await expect.poll(async () => Number(await terminal.getAttribute("data-columns"))).toBeLessThan(oldColumns);
    await expect(terminal).toBeVisible();
    expect((await downloaded.body()).includes(Buffer.from("dense-000000"))).toBe(true);
  });
}

test("live append preserves a historical reading range and the raw tail", async ({ page }) => {
  await login(page);
  const created = await createTask(page, "history-live", "import sys;sys.stdout.write(''.join('live-%06d\\n' % i for i in range(40000)));sys.stdout.flush();input();print('LATEST-AFTER-HISTORY',flush=True)");
  await expect.poll(async () => (await detail(page, created.task_id)).log_size).toBeGreaterThan(500000);
  await page.waitForTimeout(2200);
  await page.locator("#nav-terminal").click();
  await page.getByRole("button", { name: "history-live", exact: true }).click();
  const terminal = page.locator(".terminal.hydrated");
  await expect(terminal).toBeVisible();
  const tailStart = Number(await terminal.getAttribute("data-window-start"));
  await page.locator(".terminal-page .xterm-viewport").evaluate((node) => {
    node.scrollTop = 0; node.dispatchEvent(new Event("scroll"));
  });
  await expect.poll(async () => Number(await terminal.getAttribute("data-window-start"))).toBeLessThan(tailStart);
  const historicalEnd = Number(await terminal.getAttribute("data-window-end"));
  await page.evaluate(async (id) => {
    const session = await (await fetch("/api/v1/auth/session")).json();
    await fetch(`/api/v1/tasks/${id}/terminal/input`, {
      method: "POST", headers: { "Content-Type": "application/json", "X-CSRF-Token": session.csrf_token },
      body: JSON.stringify({ data: "continue\n" }),
    });
  }, created.task_id);
  await expect.poll(async () => (await detail(page, created.task_id)).ended_at).toBeTruthy();
  await page.waitForTimeout(2200);
  await expect(terminal).toBeVisible();
  expect(Number(await terminal.getAttribute("data-window-end"))).toBe(historicalEnd);
  await expect(page.locator(".terminal-page .xterm-rows")).not.toContainText("LATEST-AFTER-HISTORY");
  const download = await page.request.get(`/api/v1/tasks/${created.task_id}/logs/download`);
  expect((await download.body()).includes(Buffer.from("LATEST-AFTER-HISTORY"))).toBe(true);
});

test("socket failures have a bounded retry budget and retain the saved output", async ({ page }) => {
  await login(page);
  const created = await createTask(page, "connection-retry", "print('SAVED-BEFORE-DISCONNECT')");
  await expect.poll(async () => (await detail(page, created.task_id)).ended_at).toBeTruthy();
  await page.waitForTimeout(2200);
  // Fault injection checks the close/retry owner; it is not a natural defect witness.
  await page.evaluate((taskId) => {
    const NativeSocket = window.WebSocket;
    window.__qaReconnects = 0;
    window.WebSocket = class extends NativeSocket {
      constructor(url, protocols) {
        super(url, protocols);
        if (url.includes(`${taskId}/terminal`)) {
          window.__qaReconnects += 1;
          this.addEventListener("open", () => {
            setTimeout(() => this.close(4001, "QA transient failure"), 100);
          });
        }
      }
    };
  }, created.task_id);
  await page.locator("#nav-terminal").click();
  await page.getByRole("button", { name: "connection-retry", exact: true }).click();
  await expect.poll(() => page.evaluate(() => window.__qaReconnects)).toBe(4);
  await expect(page.locator(".terminal-output-warning")).toContainText("连接已关闭");
  await page.waitForTimeout(1500);
  expect(await page.evaluate(() => window.__qaReconnects)).toBe(4);
  const download = await page.request.get(`/api/v1/tasks/${created.task_id}/logs/download`);
  expect((await download.body()).includes(Buffer.from("SAVED-BEFORE-DISCONNECT"))).toBe(true);
});
