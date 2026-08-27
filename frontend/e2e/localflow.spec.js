import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const evidence = path.resolve("../quality/evidence/browser");
const qaRoot = process.env.LOCALFLOW_QA_ROOT;
const qaPython = process.env.LOCALFLOW_QA_PYTHON;
const resourceContract = JSON.parse(fs.readFileSync(path.resolve("../quality/resource-budgets.json"), "utf8"));

function sha256(file, normalizeText = false) {
  const content = fs.readFileSync(file); const value = normalizeText ? Buffer.from(content.toString("utf8").replace(/\r\n/g, "\n")) : content;
  return crypto.createHash("sha256").update(value).digest("hex");
}

async function browserApi(page, endpoint, options = {}) {
  return page.evaluate(async ({ endpoint, options }) => {
    const method = options.method || "GET"; const headers = { ...(options.body ? { "Content-Type": "application/json" } : {}) };
    if (method !== "GET") { const session = await fetch("/api/v1/auth/session"); headers["X-CSRF-Token"] = (await session.json()).csrf_token; }
    const response = await fetch(`/api/v1${endpoint}`, { method, headers, body: options.body ? JSON.stringify(options.body) : undefined }); const text = await response.text();
    if (!response.ok) throw new Error(`${response.status}: ${text}`); return text ? JSON.parse(text) : null;
  }, { endpoint, options });
}

async function waitForState(page, taskId, states) {
  await expect.poll(async () => (await browserApi(page, `/tasks/${taskId}`)).state, { timeout: 20_000 }).toMatch(new RegExp(`^(${states.join("|")})$`));
}

async function measureWebResources(page, activeWebSockets) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Performance.enable", { timeDomain: "threadTicks" });
  await cdp.send("HeapProfiler.collectGarbage");
  await page.waitForTimeout(250);
  await cdp.send("HeapProfiler.collectGarbage");
  const toMap = ({ metrics }) => Object.fromEntries(metrics.map(({ name, value }) => [name, value]));
  const before = toMap(await cdp.send("Performance.getMetrics"));
  let backgroundRequests = 0;
  const countRequest = (request) => { if (["fetch", "xhr"].includes(request.resourceType())) backgroundRequests += 1; };
  page.on("request", countRequest);
  const started = Date.now();
  await page.waitForTimeout(resourceContract.measurement.idle_window_seconds * 1000);
  const elapsed = (Date.now() - started) / 1000;
  page.off("request", countRequest);
  await cdp.send("HeapProfiler.collectGarbage");
  await page.waitForTimeout(250);
  await cdp.send("HeapProfiler.collectGarbage");
  const after = toMap(await cdp.send("Performance.getMetrics"));
  const dom = await cdp.send("Memory.getDOMCounters");
  await cdp.detach();
  return {
    idle_window_seconds: Number(elapsed.toFixed(3)),
    renderer_js_heap_mib: Number((after.JSHeapUsedSize / 1024 / 1024).toFixed(3)),
    renderer_idle_cpu_one_core_percent: Number((((after.TaskDuration - before.TaskDuration) / elapsed) * 100).toFixed(3)),
    dom_nodes: dom.nodes,
    dom_documents: dom.documents,
    dom_event_listeners: dom.jsEventListeners,
    idle_background_requests: backgroundRequests,
    idle_websockets: activeWebSockets(),
  };
}

function assertResourceBudget(metrics) {
  for (const [name, limit] of Object.entries(resourceContract.limits)) {
    expect(metrics[name], `${name}: ${metrics[name]} > ${limit}`).toBeLessThanOrEqual(limit);
  }
  expect(metrics.task_process_count).toBe(0);
}

test("an open testing page reloads when the frontend revision changes", async ({ page }) => {
  let revisionCalls = 0; let mainNavigations = 0;
  page.on("framenavigated", (frame) => { if (frame === page.mainFrame()) mainNavigations += 1; });
  await page.route("**/api/v1/system/ui-revision", async (route) => {
    revisionCalls += 1;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ revision: revisionCalls === 1 ? "qa-a" : "qa-b" }) });
  });
  await page.goto("/");
  await expect.poll(() => mainNavigations, { timeout: 8_000 }).toBeGreaterThanOrEqual(2);
});

test("plugin configuration console remains concise and operable in Edge", async ({ page, browser }) => {
  fs.mkdirSync(evidence, { recursive: true }); const consoleErrors = [];
  let openWebSockets = 0;
  page.on("websocket", (socket) => { openWebSockets += 1; socket.on("close", () => { openWebSockets -= 1; }); });
  page.on("console", (message) => { if (message.type() === "error") consoleErrors.push(message.text()); }); page.on("pageerror", (error) => consoleErrors.push(error.message));
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"], { origin: new URL(process.env.LOCALFLOW_QA_URL).origin });
  await page.goto("/");

  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.getByRole("tab")).toHaveText(["任务", "设置"]);
  await expect(page.getByRole("tab", { name: "运行" })).toHaveCount(0);
  await page.getByRole("tab", { name: "设置" }).click();
  await expect(page.getByLabel("管理员秘钥")).toBeVisible();
  await expect(page.getByText("时间校准", { exact: true })).toHaveCount(0);
  await page.screenshot({ path: path.join(evidence, "anonymous-settings-login-light.png"), fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
  await page.screenshot({ path: path.join(evidence, "anonymous-settings-login-mobile.png"), fullPage: true });
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.getByLabel("管理员秘钥").fill("wrong-key");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("秘钥不正确");
  expect(consoleErrors).toEqual(["Failed to load resource: the server responded with a status of 401 (Unauthorized)"]);
  consoleErrors.length = 0;
  await page.getByLabel("管理员秘钥").fill(process.env.LOCALFLOW_QA_ADMIN_KEY);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByLabel("管理员秘钥")).toHaveCount(0);
  await expect(page.getByRole("tab")).toHaveText(["任务", "运行", "终端", "设置"]);
  const navBox = await page.locator(".top").boundingBox(); expect(navBox.height).toBeLessThanOrEqual(300);
  for (const button of await page.locator(".top nav button").all()) { const box = await button.boundingBox(); expect(box.height).toBeGreaterThanOrEqual(40); }
  await expect(page.getByText("LocalFlow", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "刷新" })).toHaveCount(0);
  await page.getByRole("tab", { name: "任务" }).click();
  await expect(page.getByText("暂无任务", { exact: true })).toBeVisible();
  await page.screenshot({ path: path.join(evidence, "admin-empty-light.png"), fullPage: true });

  await page.getByRole("tab", { name: "设置" }).click();
  await expect(page.getByText("时间校准", { exact: true })).toBeVisible();
  await expect(page.getByLabel("时间校准", { exact: true })).not.toHaveValue("");
  const timeLabelBox = await page.getByText("时间校准", { exact: true }).boundingBox(); const timeInputBox = await page.getByLabel("时间校准", { exact: true }).boundingBox(); expect(Math.abs((timeLabelBox.y + timeLabelBox.height / 2) - (timeInputBox.y + timeInputBox.height / 2))).toBeLessThanOrEqual(2);
  const firstClock = await page.getByLabel("时间校准", { exact: true }).inputValue(); await page.waitForTimeout(1100); expect(await page.getByLabel("时间校准", { exact: true }).inputValue()).not.toBe(firstClock);
  await expect(page.getByRole("button", { name: /校准|应用/ })).toHaveCount(0);
  await page.screenshot({ path: path.join(evidence, "admin-settings-compact-light.png"), fullPage: true });
  await page.getByRole("button", { name: "深色" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload(); await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("tab", { name: "设置" }).click(); await expect(page.getByLabel("管理员秘钥")).toHaveCount(0); await expect(page.getByLabel("时间校准", { exact: true })).toBeVisible();

  const done = await browserApi(page, "/tasks", { method: "POST", body: { name: "qa-finished", working_directory: qaRoot, command: [qaPython, "-c", "print('qa-finished-output', flush=True)"], labels: ["browser"], custom: { report: "qa://finished", variable_sources: { report: "internal" } } } });
  await waitForState(page, done.task_id, ["succeeded"]); await page.getByRole("tab", { name: "任务" }).click();
  const doneRow = page.getByRole("button", { name: /qa-finished/ }); const freshDot = doneRow.locator(".fresh-dot"); await expect(freshDot).toBeVisible({ timeout: 10_000 }); await expect(freshDot).toHaveAttribute("aria-label", "新完成"); await expect(doneRow.locator(':scope > i:not(.fresh-dot)')).toHaveCount(0);
  await doneRow.focus(); await expect(freshDot).toBeVisible(); await doneRow.dispatchEvent("click"); await expect(freshDot).toBeVisible(); await doneRow.hover(); await expect(freshDot).toHaveCount(0);
  await expect(page.getByText("qa://finished", { exact: true })).toBeVisible(); const detailBox = await page.locator(".task-item.open .detail").boundingBox(); const rowBox = await doneRow.boundingBox(); expect(detailBox.y).toBeGreaterThan(rowBox.y);
  const nameBox = await doneRow.locator(".task-name>b").boundingBox(); const tagBox = await doneRow.locator(".task-name em").boundingBox(); expect(Math.abs((nameBox.y + nameBox.height / 2) - (tagBox.y + tagBox.height / 2))).toBeLessThanOrEqual(2);
  await expect(doneRow.locator("time")).toBeVisible(); await expect(page.locator(".task-item.open .detail-time")).toContainText("开始时间"); await expect(page.locator(".task-item.open .detail-time time")).toBeVisible(); await expect(page.locator(".task-item.open .detail-time button")).toHaveCount(0); await expect(page.getByText(done.task_id, { exact: true })).toHaveCount(0); await expect(page.getByRole("tab", { name: "详情" })).toHaveCount(0); await expect(page.locator(".task-item.open").getByRole("tab", { name: "终端" })).toHaveCount(0); await expect(page.getByText("退出码", { exact: true })).toHaveCount(0); await expect(page.getByText("source", { exact: true })).toHaveCount(0); await expect(page.getByText("variable_sources", { exact: true })).toHaveCount(0);
  const assertCompactDetail = async () => { const detail = page.locator(".task-item.open .detail"); const details = detail.locator(".details"); const article = detail.locator(".."); const currentRow = article.locator(".task-row"); const [detailGeometry, detailsGeometry, articleGeometry, currentRowGeometry] = await Promise.all([detail.boundingBox(), details.boundingBox(), article.boundingBox(), currentRow.boundingBox()]); expect(detailGeometry.y + detailGeometry.height - (detailsGeometry.y + detailsGeometry.height)).toBeLessThanOrEqual(12); expect(articleGeometry.height - currentRowGeometry.height - detailGeometry.height).toBeLessThanOrEqual(1); };
  await assertCompactDetail(); await page.setViewportSize({ width: 760, height: 800 }); await assertCompactDetail(); await page.setViewportSize({ width: 390, height: 844 }); await assertCompactDetail(); await page.setViewportSize({ width: 1440, height: 960 });
  const reportValue = page.locator(".task-item.open .copy-value").filter({ hasText: "qa://finished" }); const reportShell = reportValue.locator(".."); const beforeCopy = await reportValue.boundingBox(); await reportValue.hover(); const hoverBorder = await reportValue.evaluate((node) => getComputedStyle(node).borderColor); const accent = await page.locator("html").evaluate((node) => getComputedStyle(node).getPropertyValue("--accent").trim()); expect(hoverBorder).not.toBe(accent); await reportValue.click(); await expect(reportShell).toHaveAttribute("data-copied", "true"); await expect(reportShell.locator(".copy-confirm")).toBeVisible(); const afterCopy = await reportValue.boundingBox(); expect(afterCopy).toEqual(beforeCopy); expect(await page.evaluate(() => navigator.clipboard.readText())).toBe("qa://finished");
  const codeStyles = await page.locator(".task-item.open .copy-value code").evaluateAll((nodes) => nodes.map((node) => getComputedStyle(node).whiteSpace)); expect(new Set(codeStyles)).toEqual(new Set(["nowrap"]));
  await doneRow.click(); await expect(page.getByText("qa://finished", { exact: true })).toHaveCount(0);

  const liveCode = `import time; print('qa-terminal-ready', flush=True); time.sleep(30) # ${"long-command-".repeat(36)}`;
  const live = await browserApi(page, "/tasks", { method: "POST", body: { name: "qa-terminal", working_directory: qaRoot, command: [qaPython, "-c", liveCode], mutex_keys: ["qa:queue-lock"] } });
  await waitForState(page, live.task_id, ["running"]); await page.locator("#nav-terminal").click(); await expect(page.locator(".terminal-page .xterm")).toBeVisible(); await expect(page.locator(".terminal-page .xterm-rows")).toContainText("qa-terminal-ready"); await expect(page.locator(".terminal-page .xterm-rows")).not.toContainText("terminal resize rejected");
  const terminalHost = page.locator(".terminal-page .terminal-shell > .terminal"); expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0); const wideColumns = Number(await terminalHost.getAttribute("data-columns")); expect(wideColumns).toBeGreaterThan(40); expect((await terminalHost.boundingBox()).height).toBeGreaterThan(700);
  await page.setViewportSize({ width: 760, height: 800 }); await expect.poll(async () => Number(await terminalHost.getAttribute("data-columns"))).toBeLessThan(wideColumns); expect(Number(await terminalHost.getAttribute("data-columns"))).toBeGreaterThan(20); expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
  await page.setViewportSize({ width: 390, height: 844 }); await expect.poll(async () => Number(await terminalHost.getAttribute("data-columns"))).toBeGreaterThan(10); expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
  await page.setViewportSize({ width: 1440, height: 960 }); await page.getByRole("button", { name: "在终端中查找" }).click(); await page.getByLabel("终端搜索").fill("ready"); await page.screenshot({ path: path.join(evidence, "admin-terminal-dark.png"), fullPage: true });
  const queuedIds = [];
  for (let index = 0; index < 2; index += 1) { const queued = await browserApi(page, "/tasks", { method: "POST", body: { name: "qa-duplicate", working_directory: qaRoot, command: [qaPython, "-c", "print('queued')"], labels: ["queue-duplicate"], mutex_keys: ["qa:queue-lock"] } }); queuedIds.push(queued.task_id); }
  await page.locator("#nav-tasks").click(); await expect(page.getByRole("button", { name: /qa-duplicate/ })).toContainText("×2"); await expect(page.locator(".queue-cluster-row")).toHaveCount(0);
  for (let index = 2; index < 21; index += 1) { const queued = await browserApi(page, "/tasks", { method: "POST", body: { name: `qa-queued-${index}`, working_directory: qaRoot, command: [qaPython, "-c", "print('queued')"], labels: [`queue-${index % 3}`], mutex_keys: ["qa:queue-lock"] } }); queuedIds.push(queued.task_id); }
  const duplicateCluster = page.locator(".queue-cluster-row").filter({ hasText: "queue-duplicate" }); await expect(duplicateCluster).toBeVisible(); await duplicateCluster.click(); await expect(page.getByRole("button", { name: /qa-duplicate/ })).toContainText("×2"); const queueCluster = page.locator(".queue-cluster-row").filter({ hasText: "queue-1" }); await expect(queueCluster).toBeVisible(); await expect(queueCluster).toHaveAttribute("aria-expanded", "false"); await queueCluster.click(); await expect(queueCluster).toHaveAttribute("aria-expanded", "true"); await expect(page.locator(".queue-cluster.open .queue-cluster-items .task-row").first()).toBeVisible();
  for (const taskId of queuedIds) await browserApi(page, `/tasks/${taskId}/interrupt`, { method: "POST" });
  await page.locator("#nav-tasks").click(); const liveRow = page.getByRole("button", { name: /qa-terminal/ }); await liveRow.click(); await expect(page.locator(".task-item.open .terminal")).toHaveCount(0); const stopAction = page.getByRole("button", { name: "中止任务" }); expect(await stopAction.evaluate((node) => getComputedStyle(node).borderTopWidth)).toBe("0px"); expect(await stopAction.locator("svg").count()).toBe(1); const detail = page.locator(".task-item.open .detail"); const details = detail.locator(".details"); const detailGeometry = await detail.boundingBox(); const detailsGeometry = await details.boundingBox(); expect(detailGeometry.y + detailGeometry.height - (detailsGeometry.y + detailsGeometry.height)).toBeLessThanOrEqual(12); const longValue = page.locator(".task-item.open .copy-value").filter({ hasText: "time.sleep(30)" }); expect(await longValue.evaluate((node) => node.scrollWidth > node.clientWidth)).toBeTruthy(); await page.screenshot({ path: path.join(evidence, "admin-task-inline-dark.png"), fullPage: true }); const stoppingResponse = page.waitForResponse((response) => response.url().endsWith(`/tasks/${live.task_id}/interrupt`) && response.request().method() === "POST"); await stopAction.click(); expect((await (await stoppingResponse).json()).state).toBe("stopping"); await waitForState(page, live.task_id, ["cancelled", "failed"]);

  const simulation = await browserApi(page, "/config/files/tasks/verification-demo.yaml/runs", { method: "POST", body: { inputs: { cases: ["case-a"], case_runs: { "case-a": 1 }, seed: "" } } });
  await waitForState(page, simulation.task_ids[0], ["succeeded", "failed"]); const simulationTask = await browserApi(page, `/tasks/${simulation.task_ids[0]}`); expect(simulationTask.name).toBe("case-a"); expect(Number.isInteger(simulationTask.custom.seed)).toBeTruthy();
  await page.locator("#nav-tasks").click(); const simulationRow = page.locator(".task-row").filter({ hasText: "case-a" }).first(); await simulationRow.click(); const simulationDetail = page.locator(".task-item.open .details"); await expect(simulationDetail.getByText("随机种子", { exact: true })).toBeVisible(); await expect(simulationDetail.getByText(String(simulationTask.custom.seed), { exact: true })).toBeVisible(); await simulationRow.click();

  await page.getByRole("tab", { name: "运行" }).click(); await expect(page.locator(".tree-node").first()).toBeVisible(); await expect(page.locator(".monaco-editor")).toBeVisible({ timeout: 20_000 });
  await expect.poll(() => openWebSockets).toBe(0);
  const activeTasks = await browserApi(page, "/tasks?state=queued&state=running&state=stopping"); expect(activeTasks.items).toHaveLength(0);
  const resourceMetrics = { ...JSON.parse(process.env.LOCALFLOW_QA_SERVER_RESOURCES), ...await measureWebResources(page, () => openWebSockets) };
  assertResourceBudget(resourceMetrics);
  await expect(page.locator('[data-file="server.yaml"]')).toHaveAttribute("data-config-state", "generic");
  await expect(page.locator('[data-file="shared/task-defaults.yaml"]')).toHaveAttribute("data-config-state", "fragment");
  await expect(page.locator('[data-file="tasks/random-number.yaml"]')).toHaveAttribute("data-config-state", "task");
  await expect(page.locator('[data-file="shared/task-defaults.yaml"]')).toHaveAttribute("aria-label", /共享片段/);
  await expect(page.locator('[data-file="tasks/qa-invalid.yaml"]')).toHaveAttribute("data-config-state", "invalid");
  await expect(page.locator('[data-file="tasks/qa-invalid.yaml"]')).toHaveAttribute("aria-label", /配置有误/);
  const filenameColors = await page.locator('[data-file="shared/task-defaults.yaml"]>span:last-child, [data-file="tasks/random-number.yaml"]>span:last-child, [data-file="tasks/qa-invalid.yaml"]>span:last-child').evaluateAll((items) => items.map((item) => getComputedStyle(item).color)); expect(new Set(filenameColors).size).toBe(1);
  await page.getByRole("button", { name: "新建" }).click(); await page.getByLabel("名称").fill("qa-marker"); await page.getByLabel("插件").selectOption("marker"); await page.getByRole("button", { name: "创建" }).click(); await expect(page.locator('[data-file="tasks/qa-marker.yaml"]')).toBeVisible();
  await page.getByRole("button", { name: "重命名" }).click(); const rename = page.locator(".tree-node input"); await expect(rename).toBeVisible(); await rename.fill("qa-renamed"); await rename.press("Enter"); await expect(page.locator('[data-file="tasks/qa-renamed.yaml"]')).toBeVisible();
  await page.getByRole("button", { name: "删除", exact: true }).click(); await expect(page.getByRole("alertdialog")).toBeVisible(); await page.getByRole("alertdialog").getByRole("button", { name: "删除" }).click(); await expect(page.getByText("qa-renamed", { exact: true })).toHaveCount(0);
  await page.locator('[data-file="tasks/qa-invalid.yaml"]').click(); await expect(page.locator(".config-diagnosis")).toContainText("labels"); await expect(page.getByRole("button", { name: "运行", exact: true })).toHaveCount(0);
  await page.locator('[data-file="shared/task-defaults.yaml"]').click(); await expect(page.getByRole("button", { name: "运行", exact: true })).toHaveCount(0);
  await page.locator('[data-file="tasks/verification-demo.yaml"]').click(); await expect(page.getByText("smoke", { exact: true })).toBeVisible(); await expect(page.getByText("case-a", { exact: true })).toBeVisible(); await expect(page.getByText(/Case 路径|命令|互斥键/)).toHaveCount(0); await expect(page.getByLabel("搜索 Case")).toHaveCount(0); await expect(page.locator(".case-count")).toHaveCount(0); await expect(page.getByRole("button", { name: "运行", exact: true })).toBeDisabled(); await expect(page.getByLabel("随机种子")).toHaveValue(""); await expect(page.getByText(/\.ya?ml|\.json|\.toml/i)).toHaveCount(0); const caseBoxes = await page.locator(".case-item").evaluateAll((nodes) => nodes.map((node) => { const box = node.getBoundingClientRect(); return { width: box.width, height: box.height, x: box.x, y: box.y }; })); expect(caseBoxes.every((box) => box.height <= 40 && box.width >= 200)).toBeTruthy(); expect(new Set(caseBoxes.map((box) => Math.round(box.x))).size).toBeGreaterThanOrEqual(2); expect(new Set(caseBoxes.map((box) => Math.round(box.y))).size).toBeLessThanOrEqual(2); await page.screenshot({ path: path.join(evidence, "admin-run-verification-empty-dark.png"), fullPage: true });
  const caseA = page.locator('[data-case="case-a"]'); await caseA.hover(); await page.mouse.wheel(0, -100); await expect(caseA.locator(".case-count")).toHaveText("×1"); await page.mouse.wheel(0, 100); await expect(caseA.locator(".case-count")).toHaveCount(0);
  await page.getByRole("button", { name: "case-b，未运行" }).click(); await page.getByRole("button", { name: "case-b，1 次" }).click(); await expect(page.locator('[data-case="case-b"] .case-count')).toHaveText("×2");
  await page.getByRole("tab", { name: "设置" }).click(); await page.getByRole("tab", { name: "运行" }).click(); await expect(page.locator('[data-file="tasks/verification-demo.yaml"]')).toHaveClass(/selected/); await expect(page.locator('[data-case="case-b"] .case-count')).toHaveText("×2");
  await page.locator('[data-case="case-b"] .case-count').click(); await page.getByLabel("case-b 运行次数").fill("0"); await page.getByLabel("case-b 运行次数").press("Enter"); await expect(page.locator(".case-count")).toHaveCount(0);
  const caseGrid = await page.locator(".case-list").boundingBox(); await page.mouse.move(caseGrid.x + 4, caseGrid.y + 4); await page.mouse.down(); await page.mouse.move(caseGrid.x + caseGrid.width - 4, caseGrid.y + caseGrid.height - 4, { steps: 8 }); await page.mouse.up(); await expect(page.locator('.case-main[aria-pressed="true"]')).toHaveCount(3); await expect(page.locator(".case-count")).toHaveCount(0); await page.locator('[data-case="case-b"]').hover(); await page.mouse.wheel(0, -100); await expect(page.locator(".case-count")).toHaveText(["×1", "×1", "×1"]); await page.getByRole("button", { name: "case-b，1 次，已框选" }).click(); await expect(page.locator(".case-count")).toHaveText(["×2", "×2", "×2"]); await page.locator('[data-case="case-b"] .case-count').click(); const groupCount = page.getByRole("spinbutton", { name: "设置所选 3 个 Case 运行次数" }); await groupCount.fill("4"); await groupCount.press("Enter"); await expect(page.locator(".case-count")).toHaveText(["×4", "×4", "×4"]); await page.screenshot({ path: path.join(evidence, "admin-run-verification-scope-dark.png"), fullPage: true }); await page.locator(".workbench-header>div:first-child").click(); await expect(page.locator('.case-main[aria-pressed="true"]')).toHaveCount(0); await expect(page.getByRole("toolbar", { name: /Case/ })).toHaveCount(0);
  await page.screenshot({ path: path.join(evidence, "admin-run-verification-dark.png"), fullPage: true });
  const actionHeights = await page.locator(".workbench-actions button").evaluateAll((items) => items.map((item) => item.getBoundingClientRect().height)); expect(actionHeights.every((height) => height >= 34 && height <= 38)).toBeTruthy();
  const runBox = await page.getByRole("button", { name: "运行", exact: true }).boundingBox(); expect(Math.abs(runBox.width - runBox.height)).toBeLessThanOrEqual(1);
  await page.locator('[data-file="tasks/generic-picker.yaml"]').click(); await expect(page.getByText("case-a", { exact: true })).toBeVisible(); await page.getByRole("button", { name: "case-a，未运行" }).click(); await page.getByRole("button", { name: "case-a，1 次" }).click(); await expect(page.locator('[data-case="case-a"] .case-count')).toHaveText("×2"); const genericRunResponse = page.waitForResponse((response) => response.url().endsWith("/api/v1/config/files/tasks/generic-picker.yaml/runs") && response.request().method() === "POST"); await page.getByRole("button", { name: "运行", exact: true }).click(); expect((await genericRunResponse).json()).resolves.toMatchObject({ count: 2 });
  await page.locator('[data-file="tasks/marker-warning.yaml"]').click(); await expect(page.getByRole("button", { name: "编辑" })).toBeVisible(); await expect(page.locator(".use-config p")).toHaveCount(0); await expect(page.locator(".diagnosis-valid, .diagnosis-invalid")).toHaveCount(0); await page.getByRole("button", { name: "运行", exact: true }).click(); const configNotice = page.getByText(/已加入 1 个任务/); await expect(configNotice).toBeVisible(); await expect(configNotice).toHaveCSS("position", "static"); await expect(configNotice).toHaveCount(0, { timeout: 5_000 });
  await page.screenshot({ path: path.join(evidence, "admin-config-explorer-dark.png"), fullPage: true });
  await page.getByRole("tab", { name: "任务" }).click(); const markerRow = page.getByRole("button", { name: /警告示例/ }); await expect(markerRow).toContainText("需要关注", { timeout: 20_000 });

  await expect(page.getByRole("tab", { name: "插件" })).toHaveCount(0); await expect(page.getByRole("tab", { name: "API" })).toHaveCount(0);
  const violations = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze(); expect(violations.violations.filter((item) => ["serious", "critical"].includes(item.impact)), JSON.stringify(violations.violations, null, 2)).toEqual([]);

  await page.setViewportSize({ width: 390, height: 844 }); await page.getByRole("tab", { name: "任务" }).click(); expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0); await page.getByRole("tab", { name: "任务" }).press("ArrowDown"); await expect(page.getByRole("tab", { name: "运行" })).toBeFocused();
  await page.screenshot({ path: path.join(evidence, "admin-mobile-390.png"), fullPage: true }); expect(consoleErrors, consoleErrors.join("\n")).toEqual([]);

  const repository = path.resolve(".."); const boundFiles = ["frontend/index.html", "frontend/public/theme-boot.js", "frontend/src/App.jsx", "frontend/src/api.js", "frontend/src/main.jsx", "frontend/src/index.css", "frontend/src/extra.css", "frontend/src/round6.css", "frontend/src/case-picker.css", "frontend/e2e/localflow.spec.js", "frontend/playwright.config.js", "frontend/package-lock.json", "quality/resource-budgets.json", "tools/check_quality.py", "tools/run_browser_quality.py"];
  const sourceFiles = Object.fromEntries(boundFiles.map((relative) => [relative, sha256(path.join(repository, relative), true)])); const screenshots = Object.fromEntries(fs.readdirSync(evidence).filter((name) => name.endsWith(".png") && (name.startsWith("admin-") || name.startsWith("anonymous-"))).sort().map((name) => [name, sha256(path.join(evidence, name))]));
  fs.writeFileSync(path.join(evidence, "browser-receipt.json"), JSON.stringify({ completed_at: new Date().toISOString(), browser: "Microsoft Edge", browser_version: browser.version(), base_url: process.env.LOCALFLOW_QA_URL, result: "passed", source_files: sourceFiles, screenshots, resource_contract: resourceContract, resource_metrics: resourceMetrics, assertions: ["testing-ui-revision-auto-reload", "secret-login-required", "secret-login-error", "login-control-disappears", "persistent-browser-session", "nav-order", "removed-plugin-api-destinations", "compact-content-height-nav", "nav-target-size", "theme-memory", "run-context-memory", "aligned-settings-rows", "live-time-calibration-control", "single-time-calibration", "inline-toggle-detail", "dedicated-terminal", "xterm-fit-search", "explorer-create-rename-delete", "explorer-icon-only-state", "shared-fragment-semantic-icon", "neutral-config-filenames", "hidden-config-extensions", "opened-invalid-inline-diagnosis", "config-opens-in-use-mode", "plugin-config-discovery", "run-fields-only", "plugin-case-field-mapping", "case-empty-default", "case-hover-wheel", "case-click-increment", "case-count-progressive-editor", "case-marquee-scope-only", "case-group-relative-edit", "case-group-fixed-edit", "case-scope-dismissal", "case-intrinsic-compact-grid", "blank-seed", "verification-seed-task-detail", "required-run-field-gate", "icon-only-run", "uniform-control-geometry", "nonblocking-expiring-status", "config-use", "plugin-arbitrary-status", "idle-web-resource-budget", "compact-copyable-task-detail", "neutral-scroll-copy-feedback", "unboxed-stop-action", "direct-config-file-actions", "terminal-responsive-fit", "terminal-fill-layout", "wcag-a-aa", "mobile-no-overflow"] }, null, 2));
});
