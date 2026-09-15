import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import zlib from "node:zlib";
import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";
import { assertTooltipInteraction } from "./ui-quality.js";

const evidence = path.resolve("../quality/evidence/browser");
const qaRoot = process.env.LOCALFLOW_QA_ROOT;
const qaPython = process.env.LOCALFLOW_QA_PYTHON;
const resourceContract = JSON.parse(
  fs.readFileSync(path.resolve("../quality/resource-budgets.json"), "utf8"),
);
const currentAdminKey = () =>
  fs.readFileSync(path.join(qaRoot, "secrets", "web-admin-key"), "utf8").trim();

function sha256(file, normalizeText = false) {
  const content = fs.readFileSync(file);
  const value = normalizeText
    ? Buffer.from(content.toString("utf8").replace(/\r\n/g, "\n"))
    : content;
  return crypto.createHash("sha256").update(value).digest("hex");
}

function finalizeBrowserReceipt() {
  const receiptPath = path.join(evidence, "browser-receipt.json");
  const receipt = JSON.parse(fs.readFileSync(receiptPath, "utf8"));
  receipt.completed_at = new Date().toISOString();
  receipt.screenshots = Object.fromEntries(
    fs
      .readdirSync(evidence)
      .filter(
        (name) =>
          name.endsWith(".png") &&
          (name.startsWith("admin-") || name.startsWith("anonymous-")),
      )
      .sort()
      .map((name) => [name, sha256(path.join(evidence, name))]),
  );
  fs.writeFileSync(receiptPath, JSON.stringify(receipt, null, 2));
}

async function browserApi(page, endpoint, options = {}) {
  return page.evaluate(
    async ({ endpoint, options }) => {
      const method = options.method || "GET";
      const headers = {
        ...(options.body ? { "Content-Type": "application/json" } : {}),
      };
      if (method !== "GET") {
        const session = await fetch("/api/v1/auth/session");
        headers["X-CSRF-Token"] = (await session.json()).csrf_token;
      }
      const response = await fetch(`/api/v1${endpoint}`, {
        method,
        headers,
        body: options.body ? JSON.stringify(options.body) : undefined,
      });
      const text = await response.text();
      if (!response.ok) throw new Error(`${response.status}: ${text}`);
      return text ? JSON.parse(text) : null;
    },
    { endpoint, options },
  );
}

async function waitForState(page, taskId, states) {
  await expect
    .poll(async () => (await browserApi(page, `/tasks/${taskId}`)).state, {
      timeout: 20_000,
    })
    .toMatch(new RegExp(`^(${states.join("|")})$`));
}

async function measureWebResources(page, activeWebSockets) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send("Performance.enable", { timeDomain: "threadTicks" });
  await cdp.send("HeapProfiler.collectGarbage");
  await page.waitForTimeout(250);
  await cdp.send("HeapProfiler.collectGarbage");
  const toMap = ({ metrics }) =>
    Object.fromEntries(metrics.map(({ name, value }) => [name, value]));
  const before = toMap(await cdp.send("Performance.getMetrics"));
  let backgroundRequests = 0;
  const countRequest = (request) => {
    if (["fetch", "xhr"].includes(request.resourceType()))
      backgroundRequests += 1;
  };
  page.on("request", countRequest);
  const started = Date.now();
  await page.waitForTimeout(
    resourceContract.measurement.idle_window_seconds * 1000,
  );
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
    renderer_js_heap_mib: Number(
      (after.JSHeapUsedSize / 1024 / 1024).toFixed(3),
    ),
    renderer_idle_cpu_one_core_percent: Number(
      (((after.TaskDuration - before.TaskDuration) / elapsed) * 100).toFixed(3),
    ),
    dom_nodes: dom.nodes,
    dom_documents: dom.documents,
    dom_event_listeners: dom.jsEventListeners,
    idle_background_requests: backgroundRequests,
    idle_websockets: activeWebSockets(),
  };
}

function assertResourceBudget(metrics) {
  for (const [name, limit] of Object.entries(resourceContract.limits)) {
    expect(
      metrics[name],
      `${name}: ${metrics[name]} > ${limit}`,
    ).toBeLessThanOrEqual(limit);
  }
  expect(metrics.task_process_count).toBe(0);
}

test("an open testing page reloads when the frontend revision changes", async ({
  page,
}) => {
  let revisionCalls = 0;
  let mainNavigations = 0;
  page.on("framenavigated", (frame) => {
    if (frame === page.mainFrame()) mainNavigations += 1;
  });
  await page.route("**/api/v1/system/ui-revision", async (route) => {
    revisionCalls += 1;
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ revision: revisionCalls === 1 ? "qa-a" : "qa-b" }),
    });
  });
  await page.goto("/");
  await expect
    .poll(() => mainNavigations, { timeout: 8_000 })
    .toBeGreaterThanOrEqual(2);
});

async function ensureAdminSession(page) {
  const loginKey = page.getByLabel("管理员秘钥");
  if (await loginKey.isVisible()) {
    try {
      await loginKey.fill(currentAdminKey(), { timeout: 2_000 });
    } catch (error) {
      if (!(await loginKey.isVisible())) return;
      throw error;
    }
    const login = page.getByRole("button", { name: "登录", exact: true });
    try {
      await login.click({ timeout: 2_000 });
    } catch (error) {
      if (await loginKey.isVisible()) throw error;
    }
    await expect(loginKey).toHaveCount(0);
  }
}

async function openAdminTaskWorkspace(page) {
  await page.goto("/");
  await page.getByRole("tab", { name: "设置" }).click();
  await ensureAdminSession(page);
  await page.getByRole("tab", { name: "任务" }).click();
  await openRunPanel(page);
  await expect(page.locator(".tree-node").first()).toBeVisible();
}

test("configuration and tasks split only when every pane remains usable", async ({
  page,
}) => {
  await page.setViewportSize({ width: 1200, height: 900 });
  await openAdminTaskWorkspace(page);
  await expect(page.locator("#run-panel")).toBeVisible();
  await expect(page.locator(".task-pane")).toBeHidden();
  const focusedExplorer = await page.locator("#run-panel .explorer").boundingBox();
  const focusedWorkbench = await page
    .locator("#run-panel .config-workbench")
    .boundingBox();
  expect(focusedExplorer.width).toBeGreaterThanOrEqual(290);
  expect(focusedWorkbench.width).toBeGreaterThanOrEqual(520);

  await page.setViewportSize({ width: 1440, height: 900 });
  await expect(page.locator(".task-pane")).toBeVisible();
  const splitExplorer = await page.locator("#run-panel .explorer").boundingBox();
  const splitWorkbench = await page
    .locator("#run-panel .config-workbench")
    .boundingBox();
  const splitTasks = await page.locator(".task-pane").boundingBox();
  expect(splitExplorer.width).toBeGreaterThanOrEqual(300);
  expect(splitWorkbench.width).toBeGreaterThanOrEqual(520);
  expect(splitTasks.width).toBeGreaterThanOrEqual(410);
});

test("resource tree rename is explicit and cancellable", async ({ page }) => {
  await openAdminTaskWorkspace(page);
  const folder = page.locator('[data-file="folder:config/command"]');
  await folder.click();
  await expect(page.getByLabel("名称")).toHaveCount(0);
  await folder.dblclick();
  await expect(page.getByLabel("名称")).toHaveCount(0);

  await page.getByRole("button", { name: "重命名" }).click();
  const rename = page.getByLabel("名称");
  await expect(rename).toBeFocused();
  await rename.fill("should-not-be-applied");
  await rename.press("Escape");
  await expect(rename).toHaveCount(0);
  await expect(folder).toBeVisible();
  await expect(
    page.locator('[data-file="folder:config/should-not-be-applied"]'),
  ).toHaveCount(0);
});

test("nested include changes refresh the open run projection", async ({ page }) => {
  const shared = path.join(qaRoot, "config", "shared");
  const leaf = path.join(shared, "live-leaf.yaml");
  const middle = path.join(shared, "live-middle.yaml");
  const consumer = path.join(qaRoot, "config", "command", "live-consumer.yaml");
  fs.writeFileSync(leaf, "command: echo before-include-refresh\n", "utf8");
  fs.writeFileSync(middle, "!include live-leaf.yaml\n", "utf8");
  fs.writeFileSync(
    consumer,
    [
      "!include ../shared/live-middle.yaml",
      "plugin: command",
      "name: live-consumer",
      "working_directory: .",
      "",
    ].join("\n"),
    "utf8",
  );
  await openAdminTaskWorkspace(page);
  const entry = page.locator('[data-file="config/command/live-consumer.yaml"]');
  await expect(entry).toBeVisible({ timeout: 5_000 });
  await entry.click();
  const command = page.locator(".inspection-item").filter({ hasText: "命令" });
  await expect(command).toContainText("before-include-refresh");
  await page.waitForTimeout(1_300);
  fs.writeFileSync(leaf, "command: echo after-include-refresh\n", "utf8");
  await expect(command).toContainText("after-include-refresh", { timeout: 5_000 });
  await expect(command).not.toContainText("before-include-refresh");
});

test("invalid configuration keeps a debuggable run surface", async ({ page }) => {
  await openAdminTaskWorkspace(page);
  await page.locator('[data-file="config/command/qa-invalid.yaml"]').click();
  const action = page.locator("button.run-action");
  await expect(action).toHaveAccessibleName("配置无效");
  await expect(action).toBeDisabled();
  const debug = page.locator(".configuration-debug");
  await expect(debug).toBeVisible();
  for (const text of ["labels", "working_directory", "command"])
    await expect(debug.locator(".configuration-issues")).toContainText(text);
  for (const text of ["plugin", "labels", "wrong"])
    await expect(debug.locator(".configuration-resolution")).toContainText(text);
  const [debugBox, workbenchBox, bodyBox] = await Promise.all([
    debug.boundingBox(),
    page.locator("#run-panel .config-workbench").boundingBox(),
    debug.locator(".configuration-debug-body").boundingBox(),
  ]);
  expect(debugBox.height).toBeGreaterThan(workbenchBox.height * 0.75);
  expect(bodyBox.height).toBeGreaterThan(debugBox.height * 0.75);
});

test("a clean configuration reopens on its run surface", async ({ page }) => {
  await openAdminTaskWorkspace(page);
  const hello = page.locator('[data-file="config/command/hello-world.yaml"]');
  await hello.click();
  expect(
    await page.evaluate(() =>
      performance.getEntriesByType("resource").some((entry) =>
        entry.name.includes("MonacoEditors"),
      ),
    ),
  ).toBe(false);
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await expect(page.locator(".monaco-editor")).toBeVisible();
  expect(
    await page.evaluate(() =>
      performance.getEntriesByType("resource").some((entry) =>
        entry.name.includes("MonacoEditors"),
      ),
    ),
  ).toBe(true);
  await page.locator('[data-file="config/verification/demo.yaml"]').click();
  await hello.click();
  await expect(page.locator("button.run-action")).toHaveAccessibleName("运行");
  await expect(page.locator(".run-surface")).toBeVisible();
  await expect(page.locator(".monaco-editor")).toHaveCount(0);
});

async function runAcceptance(page) {
  const helloSource = path.join(
    qaRoot,
    "config",
    "command",
    "hello-world.yaml",
  );
  fs.writeFileSync(
    helloSource,
    fs
      .readFileSync(helloSource, "utf8")
      .replace("name: hello-world", "name: hello-world-feedback"),
    "utf8",
  );
  fs.writeFileSync(
    path.join(qaRoot, "config", "verification", "qa-missing-path.yaml"),
    [
      "plugin: verification",
      "case_directory: missing-cases",
      "working_directory: .",
      "command: echo ${case} ${seed}",
      "",
    ].join("\n"),
    "utf8",
  );
  await page.goto("/");
  await page.getByRole("tab", { name: "设置" }).click();
  await ensureAdminSession(page);
  await openRunPanel(page);
  const verificationConfig = page.locator(
    '[data-file="config/verification/demo.yaml"]',
  );
  const caseInspection = page
    .locator(".inspection-item")
    .filter({ hasText: "case-a" });
  await expect(async () => {
    await verificationConfig.click();
    await expect(caseInspection).toBeVisible({ timeout: 2_000 });
  }).toPass({ timeout: 15_000 });
  await expect(page.locator(".inspection-state")).toHaveCount(0);
  await page
    .locator('[data-file="config/verification/qa-missing-path.yaml"]')
    .click();
  const unavailablePath = page
    .locator(".inspection-item")
    .filter({ hasText: "Case 目录" })
    .locator(".inspection-state");
  await expect(unavailablePath).toHaveAttribute("aria-label", "路径不存在");
  await assertTooltipInteraction(page, unavailablePath, "找不到 Case 目录");
  const helloConfig = page.locator(
    '[data-file="config/command/hello-world.yaml"]',
  );
  await helloConfig.click();

  let delayed = false;
  let releaseRunRequest;
  const runRequestGate = new Promise((resolve) => {
    releaseRunRequest = resolve;
  });
  await page.route(
    "**/api/v1/config/files/command/hello-world.yaml/runs",
    async (route) => {
      delayed = true;
      await runRequestGate;
      await route.continue();
    },
    { times: 1 },
  );
  const responsePromise = page.waitForResponse(
    (response) =>
      response
        .url()
        .endsWith("/api/v1/config/files/command/hello-world.yaml/runs") &&
      response.request().method() === "POST",
  );
  const runButton = page.locator("button.run-action");
  await expect(runButton).toHaveAccessibleName("运行");
  await runButton.click();
  await expect.poll(() => delayed).toBeTruthy();
  await expect(runButton).toHaveAttribute("data-run-state", "submitting");
  await expect(runButton).toHaveAccessibleName("提交中");
  await expect(runButton).toBeDisabled();
  releaseRunRequest();
  const response = await responsePromise;
  const accepted = await response.json();
  await expect(runButton).toHaveAttribute("data-run-state", "accepted");
  await expect(runButton).toHaveAccessibleName("已创建");
  await expect(page.locator(".notice[role='status']")).toHaveText(
    `已加入 ${accepted.count} 个任务`,
  );

  const taskId = accepted.task_ids[0];
  await page.getByRole("tab", { name: "任务" }).click();
  const configToggle = page.getByRole("button", { name: "配置", exact: true });
  if ((await configToggle.getAttribute("aria-expanded")) === "true")
    await configToggle.click();
  await expect(configToggle).toHaveAttribute("aria-expanded", "false");
  const row = page.getByRole("button", { name: /hello-world-feedback/ });
  await expect(row).toBeVisible();
  const assertOrderedCells = async () => {
    const cells = await row.locator(":scope > *").evaluateAll((nodes) =>
      nodes
        .map((node) => {
          const box = node.getBoundingClientRect();
          return { left: box.left, right: box.right, width: box.width };
        })
        .filter((box) => box.width > 0),
    );
    for (let index = 1; index < cells.length; index += 1)
      expect(cells[index].left).toBeGreaterThanOrEqual(
        cells[index - 1].right - 1,
      );
  };
  await assertOrderedCells();
  await waitForState(page, taskId, ["succeeded"]);
  await assertOrderedCells();
  const task = await browserApi(page, `/tasks/${taskId}`);
  expect(task.started_at).toBeTruthy();
  expect(fs.existsSync(task.log_path)).toBeTruthy();
  const log = fs.readFileSync(task.log_path, "utf8");
  expect(log).toContain("task.queued");
  expect(log).toContain("task.starting");
  expect(log).toContain("process.started");
  expect(log).toContain("hello world");
  expect(log).toContain("process.exited");
  expect(
    fs
      .readFileSync(path.join(qaRoot, "hello-world.txt"), "utf8")
      .replace(/\r\n/g, "\n"),
  ).toBe("hello world\n");
  await row.click();
  await expect(
    page.locator(".task-item.open .detail-time time"),
  ).not.toHaveText("—");
  await expect(
    page
      .locator(".task-item.open .copy-value")
      .filter({ hasText: task.log_path }),
  ).toBeVisible();
  await expect(
    page.locator(".task-item.open").getByText("终端输出", { exact: true }),
  ).toBeVisible();
}

async function openRunPanel(page) {
  await page.getByRole("tab", { name: "任务" }).click();
  const toggle = page.getByRole("button", { name: "配置", exact: true });
  if ((await toggle.getAttribute("aria-expanded")) === "false") await toggle.click();
  await expect(page.locator("#run-panel")).toBeVisible();
}

test("plugin configuration console remains concise and operable in Edge", async ({
  page,
  browser,
}) => {
  test.setTimeout(300_000);
  fs.mkdirSync(evidence, { recursive: true });
  const consoleErrors = [];
  const validationRejections = [];
  let openWebSockets = 0;
  let terminalAcks = 0;
  page.on("websocket", (socket) => {
    openWebSockets += 1;
    socket.on("framesent", ({ payload }) => {
      try {
        if (JSON.parse(String(payload)).type === "ack") terminalAcks += 1;
      } catch {
        /* binary/user frames are not protocol JSON */
      }
    });
    socket.on("close", () => {
      openWebSockets -= 1;
    });
  });
  page.on("console", (message) => {
    if (
      message.type() === "error" &&
      message.text() !==
        "Failed to load resource: the server responded with a status of 422 (Unprocessable Content)"
    )
      consoleErrors.push(message.text());
  });
  page.on("response", (response) => {
    if (response.status() === 422) validationRejections.push(response.url());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));
  await page.addInitScript(() => {
    const original = Document.prototype.execCommand;
    Document.prototype.execCommand = function execCommand(command, ...args) {
      if (command === "copy") {
        window.__localflowCopiedText =
          document.activeElement?.value || window.getSelection()?.toString();
        return true;
      }
      return original.call(this, command, ...args);
    };
  });
  await page.goto("/");
  expect(await page.evaluate(() => window.isSecureContext)).toBeFalsy();

  await expect(page.locator("html")).toHaveAttribute("data-theme", "light");
  await expect(page.getByRole("tab")).toHaveText(["任务", "设置"]);
  await expect(page.getByRole("button", { name: "配置", exact: true })).toHaveCount(
    0,
  );
  await page.getByRole("tab", { name: "设置" }).click();
  await expect(page.getByLabel("管理员秘钥")).toBeVisible();
  await expect(page.getByText("时间校准", { exact: true })).toHaveCount(0);
  await page.screenshot({
    path: path.join(evidence, "anonymous-settings-login-light.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    ),
  ).toBeLessThanOrEqual(0);
  await page.screenshot({
    path: path.join(evidence, "anonymous-settings-login-mobile.png"),
    fullPage: true,
  });
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.getByLabel("管理员秘钥").fill("wrong-key");
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("alert")).toHaveText("秘钥不正确");
  expect(consoleErrors).toEqual([
    "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
  ]);
  consoleErrors.length = 0;
  await page.getByLabel("管理员秘钥").fill(currentAdminKey());
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByLabel("管理员秘钥")).toHaveCount(0);
  await expect(page.getByRole("tab")).toHaveText(["任务", "终端", "设置"]);
  const navBox = await page.locator(".top").boundingBox();
  expect(navBox.height).toBeLessThanOrEqual(300);
  for (const button of await page.locator(".top nav button").all()) {
    const box = await button.boundingBox();
    expect(box.height).toBeGreaterThanOrEqual(40);
  }
  await expect(page.getByText("LocalFlow", { exact: true })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "刷新" })).toHaveCount(0);
  await page.getByRole("tab", { name: "任务" }).click();
  await expect(page.getByText("暂无任务", { exact: true })).toBeVisible();
  const runPanelToggle = page.getByRole("button", { name: "配置", exact: true });
  await expect(runPanelToggle)
    .toHaveAttribute("aria-expanded", "true");
  await expect(runPanelToggle)
    .toHaveAttribute("aria-controls", "run-panel");
  await expect(runPanelToggle).toHaveText("配置");
  const navigationBox = await page.locator(".top nav").boundingBox();
  const runToggleBox = await runPanelToggle.boundingBox();
  expect(runToggleBox.x).toBeLessThan(124);
  expect(runToggleBox.y).toBeGreaterThanOrEqual(navigationBox.y + navigationBox.height);
  await page.screenshot({
    path: path.join(evidence, "admin-empty-light.png"),
    fullPage: true,
  });

  await page.getByRole("tab", { name: "设置" }).click();
  await expect(page.getByText("时间校准", { exact: true })).toBeVisible();
  await expect(page.getByLabel("时间校准", { exact: true })).not.toHaveValue(
    "",
  );
  const timeLabelBox = await page
    .getByText("时间校准", { exact: true })
    .boundingBox();
  const timeInputBox = await page
    .getByLabel("时间校准", { exact: true })
    .boundingBox();
  expect(
    Math.abs(
      timeLabelBox.y +
        timeLabelBox.height / 2 -
        (timeInputBox.y + timeInputBox.height / 2),
    ),
  ).toBeLessThanOrEqual(2);
  const firstClock = await page
    .getByLabel("时间校准", { exact: true })
    .inputValue();
  await page.waitForTimeout(1100);
  expect(
    await page.getByLabel("时间校准", { exact: true }).inputValue(),
  ).not.toBe(firstClock);
  await expect(page.getByRole("button", { name: /校准|应用/ })).toHaveCount(0);
  await page.screenshot({
    path: path.join(evidence, "admin-settings-compact-light.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "深色" }).click();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.reload();
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  await page.getByRole("tab", { name: "设置" }).click();
  await expect(page.getByLabel("管理员秘钥")).toHaveCount(0);
  await expect(page.getByLabel("时间校准", { exact: true })).toBeVisible();

  const done = await browserApi(page, "/tasks", {
    method: "POST",
    body: {
      name: "qa-finished",
      working_directory: qaRoot,
      command: [qaPython, "-c", "print('qa-finished-output', flush=True)"],
      labels: ["browser"],
      custom: {
        report: "qa://finished",
        artifacts: ["qa://compile.log", "qa://run.log"],
        variable_sources: { report: "internal" },
      },
    },
  });
  await waitForState(page, done.task_id, ["succeeded"]);
  await page.getByRole("tab", { name: "任务" }).click();
  const doneRow = page.getByRole("button", { name: /qa-finished/ });
  const freshDot = doneRow.locator(".fresh-dot");
  await expect(freshDot).toBeVisible({ timeout: 10_000 });
  await expect(freshDot).toHaveAttribute("aria-label", "新完成");
  const freshColors = await freshDot.evaluate((node) => {
    const root = document.documentElement;
    const normalize = (value) => {
      const probe = document.createElement("i");
      probe.style.color = value;
      document.body.appendChild(probe);
      const color = getComputedStyle(probe).color;
      probe.remove();
      return color;
    };
    return {
      actual: getComputedStyle(node).backgroundColor,
      accent: normalize(getComputedStyle(root).getPropertyValue("--accent")),
      danger: normalize(getComputedStyle(root).getPropertyValue("--danger")),
    };
  });
  expect(freshColors.actual).toBe(freshColors.accent);
  expect(freshColors.actual).not.toBe(freshColors.danger);
  await expect(doneRow.locator(":scope > i:not(.fresh-dot)")).toHaveCount(0);
  await doneRow.focus();
  await expect(freshDot).toBeVisible();
  await doneRow.dispatchEvent("click");
  await expect(freshDot).toBeVisible();
  await doneRow.hover();
  await expect(freshDot).toHaveCount(0);
  await expect(page.getByText("qa://finished", { exact: true })).toBeVisible();
  const artifactList = page.getByRole("list", { name: "artifacts" });
  await expect(artifactList.getByRole("listitem")).toHaveCount(2);
  await expect(artifactList.getByText("qa://compile.log", { exact: true })).toBeVisible();
  await expect(artifactList.getByText("qa://run.log", { exact: true })).toBeVisible();
  const artifactGeometry = await artifactList.evaluate((list) => ({
    ownerWidth: list.getBoundingClientRect().width,
    rows: [...list.querySelectorAll("[role='listitem']")].map((row) => ({
      width: row.getBoundingClientRect().width,
      valueWidth: row.querySelector(".copy-value").getBoundingClientRect().width,
    })),
  }));
  for (const row of artifactGeometry.rows) {
    expect(row.width).toBeGreaterThanOrEqual(artifactGeometry.ownerWidth - 1);
    expect(row.valueWidth).toBeGreaterThanOrEqual(artifactGeometry.ownerWidth - 1);
  }
  const detailBox = await page.locator(".task-item.open .detail").boundingBox();
  const rowBox = await doneRow.boundingBox();
  expect(detailBox.y).toBeGreaterThan(rowBox.y);
  const nameBox = await doneRow.locator(".task-name>b").boundingBox();
  const tagBox = await doneRow.locator(".task-name em").boundingBox();
  expect(
    Math.abs(nameBox.y + nameBox.height / 2 - (tagBox.y + tagBox.height / 2)),
  ).toBeLessThanOrEqual(2);
  await expect(doneRow.locator("time")).toBeVisible();
  await expect(page.locator(".task-item.open .detail-time > span")).toHaveText(
    "开始时间",
  );
  await expect(page.locator(".task-item.open .detail-time svg")).toHaveCount(0);
  const detailTime = page.locator(".task-item.open .detail-time time");
  await expect(detailTime).toBeVisible();
  await expect(detailTime).toHaveAttribute("datetime", /.+/);
  await expect(detailTime).toHaveAttribute("title", /.+/);
  await expect(page.locator(".task-item.open .detail-time button")).toHaveCount(
    0,
  );
  await expect(page.getByText(done.task_id, { exact: true })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "详情" })).toHaveCount(0);
  await expect(
    page.locator(".task-item.open").getByRole("tab", { name: "终端" }),
  ).toHaveCount(0);
  await expect(page.getByText("退出码", { exact: true })).toHaveCount(0);
  await expect(page.getByText("source", { exact: true })).toHaveCount(0);
  await expect(page.getByText("variable_sources", { exact: true })).toHaveCount(
    0,
  );
  const assertCompactDetail = async () => {
    const detail = page.locator(".task-item.open .detail");
    const details = detail.locator(".details");
    const article = detail.locator("..");
    const currentRow = article.locator(".task-row");
    const [
      detailGeometry,
      detailsGeometry,
      articleGeometry,
      currentRowGeometry,
    ] = await Promise.all([
      detail.boundingBox(),
      details.boundingBox(),
      article.boundingBox(),
      currentRow.boundingBox(),
    ]);
    expect(
      detailGeometry.y +
        detailGeometry.height -
        (detailsGeometry.y + detailsGeometry.height),
    ).toBeLessThanOrEqual(12);
    expect(
      articleGeometry.height -
        currentRowGeometry.height -
        detailGeometry.height,
    ).toBeLessThanOrEqual(1);
  };
  await assertCompactDetail();
  await runPanelToggle.click();
  await expect(runPanelToggle).toHaveAttribute("aria-expanded", "false");
  await page.setViewportSize({ width: 760, height: 800 });
  await assertCompactDetail();
  await page.setViewportSize({ width: 390, height: 844 });
  await assertCompactDetail();
  await page.setViewportSize({ width: 1440, height: 960 });
  await runPanelToggle.click();
  await expect(runPanelToggle).toHaveAttribute("aria-expanded", "true");
  const reportValue = page
    .locator(".task-item.open .copy-value")
    .filter({ hasText: "qa://finished" });
  const reportShell = reportValue.locator("..");
  const beforeCopy = await reportValue.boundingBox();
  await reportValue.hover();
  const hoverBorder = await reportValue.evaluate(
    (node) => getComputedStyle(node).borderColor,
  );
  const accent = await page
    .locator("html")
    .evaluate((node) =>
      getComputedStyle(node).getPropertyValue("--accent").trim(),
    );
  expect(hoverBorder).not.toBe(accent);
  await reportValue.click();
  await expect(reportShell).toHaveAttribute("data-copied", "true");
  await expect(reportValue.locator(".copy-affordance")).toHaveCount(0);
  const afterCopy = await reportValue.boundingBox();
  expect(afterCopy).toEqual(beforeCopy);
  expect(await page.evaluate(() => window.__localflowCopiedText)).toBe(
    "qa://finished",
  );
  const codeStyles = await page
    .locator(".task-item.open .copy-value code")
    .evaluateAll((nodes) =>
      nodes.map((node) => getComputedStyle(node).whiteSpace),
    );
  expect(new Set(codeStyles)).toEqual(new Set(["nowrap"]));
  await doneRow.click();
  await expect(page.getByText("qa://finished", { exact: true })).toHaveCount(0);

  const liveCode = `import time; print('qa-terminal-ready', flush=True); time.sleep(12); print('qa-terminal-fresh', flush=True); time.sleep(168) # ${"long-command-".repeat(36)}`;
  const live = await browserApi(page, "/tasks", {
    method: "POST",
    body: {
      name: "qa-terminal",
      working_directory: qaRoot,
      command: [qaPython, "-c", liveCode],
      labels: ["browser", "terminal"],
      mutex_keys: ["qa:queue-lock"],
    },
  });
  await waitForState(page, live.task_id, ["running"]);
  await page.locator("#nav-terminal").click();
  const liveTerminalEntry = page
    .locator(".terminal-page .terminal-entry")
    .filter({ hasText: "qa-terminal" });
  await expect(liveTerminalEntry).toHaveAttribute("data-terminal-state", "running");
  await expect(liveTerminalEntry.locator(".terminal-entry-state")).toHaveCount(0);
  await expect(liveTerminalEntry.locator("svg")).toHaveCount(0);
  const terminalRailWidth = await page.locator(".terminal-page > aside").evaluate(
    (node) => node.getBoundingClientRect().width,
  );
  expect(terminalRailWidth).toBeGreaterThanOrEqual(248);
  expect(terminalRailWidth).toBeLessThanOrEqual(320);
  await expect(liveTerminalEntry.locator(".terminal-entry-label")).toHaveText([
    "browser",
    "terminal",
  ]);
  await expect(
    page.locator(".terminal-page .terminal-entry-activity"),
  ).toHaveCount(0);
  const selectedActivity = page.locator(".terminal-selection-activity");
  await expect(selectedActivity).toBeVisible();
  await expect(selectedActivity).toHaveText(/^\d+[smhd]$/);
  await expect(selectedActivity).toHaveAttribute(
    "aria-label",
    /^距最后输出 \d+[smhd]$/,
  );
  await expect(selectedActivity).toHaveAttribute(
    "datetime",
    /T.*(?:Z|\+00:00)$/,
  );
  await expect(selectedActivity).toHaveAttribute("title", /最后输出：/);
  const firstOutputTimestamp = await selectedActivity.getAttribute("datetime");
  await expect(liveTerminalEntry.locator(".terminal-unread")).toHaveCount(0);
  const activeTerminalGroup = page.locator(
    '.terminal-entry-group[data-terminal-group="active"]',
  );
  const historyTerminalGroup = page.locator(
    '.terminal-entry-group[data-terminal-group="history"]',
  );
  await expect(activeTerminalGroup.locator(":scope > header")).toContainText(
    "运行中",
  );
  await expect(historyTerminalGroup.locator(":scope > header")).toContainText(
    "历史",
  );
  expect((await activeTerminalGroup.boundingBox()).y).toBeLessThan(
    (await historyTerminalGroup.boundingBox()).y,
  );
  await expect(page.locator(".terminal-page .xterm")).toBeVisible();
  await expect(page.locator(".terminal-page .xterm-rows")).toContainText(
    "qa-terminal-ready",
  );
  const copyRow = page
    .locator(".terminal-page .xterm-rows > div")
    .filter({ hasText: "qa-terminal-ready" })
    .last();
  const copyRowBox = await copyRow.boundingBox();
  await page.mouse.move(copyRowBox.x + 3, copyRowBox.y + copyRowBox.height / 2);
  await page.mouse.down();
  await page.mouse.move(copyRowBox.x + 180, copyRowBox.y + copyRowBox.height / 2);
  await page.mouse.up();
  await page.keyboard.press("Control+c");
  await expect
    .poll(() => page.evaluate(() => window.__localflowCopiedText))
    .toContain("qa-terminal-ready");
  await expect(page.locator(".terminal-page .xterm-rows")).not.toContainText(
    "[终端已连接]",
  );
  await expect(page.locator(".terminal-page .xterm-rows")).not.toContainText(
    "terminal resize rejected",
  );
  await expect.poll(() => terminalAcks).toBeGreaterThan(0);
  const terminalHost = page.locator(
    ".terminal-page .terminal-shell > .terminal",
  );
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    ),
  ).toBeLessThanOrEqual(0);
  const wideColumns = Number(await terminalHost.getAttribute("data-columns"));
  expect(wideColumns).toBeGreaterThan(40);
  expect((await terminalHost.boundingBox()).height).toBeGreaterThan(700);
  await page.setViewportSize({ width: 760, height: 800 });
  await expect
    .poll(async () => Number(await terminalHost.getAttribute("data-columns")))
    .toBeLessThan(wideColumns);
  expect(
    Number(await terminalHost.getAttribute("data-columns")),
  ).toBeGreaterThan(20);
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    ),
  ).toBeLessThanOrEqual(0);
  await page.setViewportSize({ width: 390, height: 844 });
  await expect
    .poll(async () => Number(await terminalHost.getAttribute("data-columns")))
    .toBeGreaterThan(10);
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    ),
  ).toBeLessThanOrEqual(0);
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.getByRole("button", { name: "在终端中查找" }).click();
  await page.getByLabel("终端搜索").fill("ready");

  // A marker represents unread output only. Existing and merely-running
  // terminals stay quiet; a background terminal gets a marker after its log
  // grows, and selecting it acknowledges the marker.
  const finishedTerminalEntry = page
    .locator(".terminal-page .terminal-entry")
    .filter({ hasText: "qa-finished" });
  await finishedTerminalEntry.click();
  await expect(liveTerminalEntry.locator(".terminal-unread")).toHaveCount(0);
  await expect(liveTerminalEntry.locator(".terminal-unread")).toBeVisible({
    timeout: 18_000,
  });
  await expect(liveTerminalEntry.locator(".terminal-unread")).toHaveAttribute(
    "aria-label",
    "有新终端输出",
  );
  await liveTerminalEntry.click();
  await expect(liveTerminalEntry.locator(".terminal-unread")).toHaveCount(0);
  await expect
    .poll(() => selectedActivity.getAttribute("datetime"))
    .not.toBe(firstOutputTimestamp);
  await page.screenshot({
    path: path.join(evidence, "admin-terminal-dark.png"),
    fullPage: true,
  });
  const queuedIds = [];
  for (let index = 0; index < 2; index += 1) {
    const queued = await browserApi(page, "/tasks", {
      method: "POST",
      body: {
        name: "qa-duplicate",
        working_directory: qaRoot,
        command: [qaPython, "-c", "print('queued')"],
        labels: ["queue-duplicate"],
        mutex_keys: ["qa:queue-lock"],
      },
    });
    queuedIds.push(queued.task_id);
  }
  await page.locator("#nav-tasks").click();
  await expect(
    page.getByRole("button", { name: /qa-duplicate/ }),
  ).toContainText("×2");
  await expect(page.locator(".queue-cluster-row")).toHaveCount(0);
  for (let index = 2; index < 21; index += 1) {
    const queued = await browserApi(page, "/tasks", {
      method: "POST",
      body: {
        name: `qa-queued-${index}`,
        working_directory: qaRoot,
        command: [qaPython, "-c", "print('queued')"],
        labels: [`queue-${index % 3}`],
        mutex_keys: ["qa:queue-lock"],
      },
    });
    queuedIds.push(queued.task_id);
  }
  const duplicateCluster = page
    .locator(".queue-cluster-row")
    .filter({ hasText: "queue-duplicate" });
  await expect(duplicateCluster).toBeVisible();
  await duplicateCluster.click();
  await expect(
    page.getByRole("button", { name: /qa-duplicate/ }),
  ).toContainText("×2");
  const queueCluster = page
    .locator(".queue-cluster-row")
    .filter({ hasText: "queue-1" });
  await expect(queueCluster).toBeVisible();
  await expect(queueCluster).toHaveAttribute("aria-expanded", "false");
  await queueCluster.click();
  await expect(queueCluster).toHaveAttribute("aria-expanded", "true");
  await expect(
    page.locator(".queue-cluster.open .queue-cluster-items .task-row").first(),
  ).toBeVisible();
  for (const taskId of queuedIds)
    await browserApi(page, `/tasks/${taskId}/interrupt`, { method: "POST" });
  await page.locator("#nav-tasks").click();
  const liveRow = page.getByRole("button", { name: /qa-terminal/ });
  await liveRow.click();
  await expect(page.locator(".task-item.open .terminal")).toHaveCount(0);
  const stopAction = page.getByRole("button", { name: "中止任务" });
  expect(
    await stopAction.evaluate((node) => getComputedStyle(node).borderTopWidth),
  ).toBe("0px");
  expect(await stopAction.locator("svg").count()).toBe(1);
  const detail = page.locator(".task-item.open .detail");
  const details = detail.locator(".details");
  const detailGeometry = await detail.boundingBox();
  const detailsGeometry = await details.boundingBox();
  expect(
    detailGeometry.y +
      detailGeometry.height -
      (detailsGeometry.y + detailsGeometry.height),
  ).toBeLessThanOrEqual(12);
  const longValue = page
    .locator(".task-item.open .copy-value")
    .filter({ hasText: "time.sleep(168)" });
  expect(
    await longValue.evaluate((node) => node.scrollWidth > node.clientWidth),
  ).toBeTruthy();
  await page.screenshot({
    path: path.join(evidence, "admin-task-inline-dark.png"),
    fullPage: true,
  });
  const stoppingResponse = page.waitForResponse(
    (response) =>
      response.url().endsWith(`/tasks/${live.task_id}/interrupt`) &&
      response.request().method() === "POST",
  );
  await stopAction.click();
  expect((await (await stoppingResponse).json()).state).toBe("stopping");
  await waitForState(page, live.task_id, ["cancelled", "failed"]);
  await page.locator("#nav-terminal").click();
  const historyTerminal = page
    .locator(".terminal-page .terminal-entry")
    .filter({ hasText: "qa-terminal" });
  await expect(historyTerminal).toBeVisible();
  await historyTerminal.click();
  await expect(page.getByText("只读历史", { exact: true })).toHaveCount(0);
  await expect(page.locator(".terminal-selection-activity")).toHaveCount(0);
  await expect(page.locator(".terminal-actions")).toHaveCount(0);
  await expect(page.locator(".terminal-page .xterm-rows")).toContainText(
    "qa-terminal-ready",
  );
  const historyCopyRow = page
    .locator(".terminal-page .xterm-rows > div")
    .filter({ hasText: "qa-terminal-ready" })
    .last();
  const historyCopyBox = await historyCopyRow.boundingBox();
  await page.mouse.move(
    historyCopyBox.x + 3,
    historyCopyBox.y + historyCopyBox.height / 2,
  );
  await page.mouse.down();
  await page.mouse.move(
    historyCopyBox.x + 180,
    historyCopyBox.y + historyCopyBox.height / 2,
  );
  await page.mouse.up();
  await expect(page.getByRole("button", { name: "复制选中" })).toBeVisible();
  await page.evaluate(() => {
    window.__localflowCopiedText = "";
  });
  await page.keyboard.press("Control+c");
  await expect
    .poll(() => page.evaluate(() => window.__localflowCopiedText))
    .toContain("qa-terminal-ready");
  await page.getByRole("button", { name: "复制选中" }).click();
  await expect(page.getByRole("button", { name: "已复制" })).toBeVisible();
  await expect(page.locator(".terminal-page .xterm-rows")).not.toContainText(
    "[只读回放已连接]",
  );
  await page.locator(".terminal-page .xterm").click();
  await page.keyboard.press("Control+f");
  await expect(page.getByLabel("终端搜索")).toBeFocused();
  expect(
    await page.locator(".terminal-find").evaluate((node) => {
      const background = getComputedStyle(node).backgroundColor;
      return background !== "transparent" && background !== "rgba(0, 0, 0, 0)";
    }),
  ).toBeTruthy();
  await page.getByLabel("终端搜索").fill("qa-terminal-ready");
  await expect(page.locator(".terminal-find output")).toContainText(/\d+\/\d+/);
  await page.getByRole("button", { name: "检索全部日志" }).click();
  await expect(page.locator(".terminal-search-results")).toContainText("qa-terminal-ready");
  await page.getByRole("button", { name: "区分大小写" }).click();
  await expect(page.getByRole("button", { name: "区分大小写" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByRole("button", { name: "上一个匹配" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "下一个匹配" })).toBeEnabled();
  await expect(page.getByRole("button", { name: "跳到终端开头" })).toBeVisible();
  await expect(page.getByRole("button", { name: "跳到终端末尾" })).toBeVisible();

  const simulation = await browserApi(
    page,
    "/config/files/verification/demo.yaml/runs",
    {
      method: "POST",
      body: {
        inputs: { cases: ["case-a"], case_runs: { "case-a": 1 }, seed: "" },
      },
    },
  );
  await waitForState(page, simulation.task_ids[0], ["succeeded", "failed"]);
  const simulationTask = await browserApi(
    page,
    `/tasks/${simulation.task_ids[0]}`,
  );
  expect(simulationTask.name).toBe("case-a");
  expect(Number.isInteger(simulationTask.custom.seed)).toBeTruthy();
  expect(simulationTask.custom["自定义文本"]).toEqual([
    "Case: case-a",
    `Seed: ${simulationTask.custom.seed}`,
  ]);
  await page.locator("#nav-tasks").click();
  const simulationRow = page
    .locator(".task-row")
    .filter({ hasText: "case-a" })
    .first();
  await simulationRow.click();
  const simulationDetail = page.locator(".task-item.open .details");
  await expect(
    simulationDetail.getByText("随机种子", { exact: true }),
  ).toHaveCount(0);
  await expect(
    simulationDetail.getByText("运行日志", { exact: true }),
  ).toHaveCount(0);
  await expect(
    simulationDetail.getByText("自定义文本", { exact: true }),
  ).toHaveCount(0);
  const taskCustomTexts = simulationDetail.locator(
    '.copy-field[data-custom-text="true"]',
  );
  await expect(taskCustomTexts).toHaveCount(2);
  const caseCustomText = taskCustomTexts
    .locator(".copy-value")
    .filter({ hasText: "Case: case-a" });
  await caseCustomText.click();
  expect(await page.evaluate(() => window.__localflowCopiedText)).toBe(
    "Case: case-a",
  );
  await simulationRow.click();

  await openRunPanel(page);
  await expect(page.locator(".tree-node").first()).toBeVisible();
  await expect(page.locator(".config-workbench")).toBeVisible();
  const wideTasks = await page.locator(".task-pane").boundingBox();
  const wideRun = await page.locator("#run-panel").boundingBox();
  expect(wideRun.x + wideRun.width).toBeLessThanOrEqual(wideTasks.x + 1);
  expect(Math.abs(wideTasks.y - wideRun.y)).toBeLessThanOrEqual(1);
  const workbenchName = await page.locator(".workbench-context > span").boundingBox();
  const workbenchActions = await page.locator(".workbench-actions").boundingBox();
  expect(workbenchActions.x - (workbenchName.x + workbenchName.width)).toBeLessThanOrEqual(32);
  await expect(page.locator(".workbench-actions")).toContainText("编辑");
  await expect(page.locator(".workbench-actions")).toContainText("运行");
  const selectedConfigName = await page
    .locator(".workbench-context > span")
    .textContent();
  await page.setViewportSize({ width: 1000, height: 900 });
  await expect(page.locator("#run-panel")).toBeVisible();
  await expect(page.locator(".task-pane")).toBeHidden();
  const focusedRun = await page.locator("#run-panel").boundingBox();
  const focusedContent = await page.locator(".app-content").boundingBox();
  expect(focusedRun.x).toBeCloseTo(focusedContent.x, 0);
  expect(focusedRun.width).toBeCloseTo(focusedContent.width, 0);
  await runPanelToggle.click();
  await expect(page.locator("#run-panel")).toBeHidden();
  await expect(page.locator(".task-pane")).toBeVisible();
  const revealedTasks = await page.locator(".task-pane").boundingBox();
  expect(revealedTasks.x).toBeCloseTo(focusedContent.x, 0);
  expect(revealedTasks.width).toBeCloseTo(focusedContent.width, 0);
  await runPanelToggle.focus();
  await runPanelToggle.press("Enter");
  await expect(page.locator("#run-panel")).toBeVisible();
  await expect(page.locator(".task-pane")).toBeHidden();
  await expect(page.locator(".workbench-context > span")).toHaveText(
    selectedConfigName,
  );
  await page.setViewportSize({ width: 760, height: 900 });
  await expect(page.locator("#run-panel")).toBeVisible();
  await expect(page.locator(".task-pane")).toBeHidden();
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
  await page.setViewportSize({ width: 390, height: 844 });
  const narrowExplorer = await page.locator("#run-panel .explorer").boundingBox();
  const narrowConfig = await page.locator("#run-panel .config-workbench").boundingBox();
  expect(narrowExplorer.y + narrowExplorer.height).toBeLessThanOrEqual(narrowConfig.y + 1);
  expect(await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth)).toBeLessThanOrEqual(0);
  await page.setViewportSize({ width: 1440, height: 960 });
  await expect.poll(() => openWebSockets).toBe(0);
  const activeTasks = await browserApi(
    page,
    "/tasks?state=queued&state=running&state=stopping",
  );
  expect(activeTasks.items).toHaveLength(0);
  const resourceMetrics = {
    ...JSON.parse(process.env.LOCALFLOW_QA_SERVER_RESOURCES),
    ...(await measureWebResources(page, () => openWebSockets)),
    terminal_ack_frames: terminalAcks,
  };
  assertResourceBudget(resourceMetrics);
  await expect(page.locator('[data-file="folder:config"]')).toHaveCount(0);
  await expect(page.locator('[data-file="folder:plugins"]')).toHaveCount(0);
  await expect(page.locator('[data-file^="plugins/"]')).toHaveCount(0);
  await expect(
    page.locator('[data-file="config/command/hello-world.yaml"]'),
  ).toHaveAttribute("data-config-state", "file");
  await expect(
    page.locator('[data-file="config/command/hello-world.yaml"]'),
  ).toHaveAttribute("aria-label", /配置文件/);
  await page.locator('[data-file="folder:config/command"]').click();
  await page.getByRole("button", { name: "新建文件" }).click();
  await page.getByLabel("名称").fill("qa-command");
  await expect(page.getByRole("dialog").locator("select")).toHaveCount(0);
  await page.getByRole("button", { name: "创建" }).click();
  await expect(
    page.locator('[data-file="config/command/qa-command.yaml"]'),
  ).toBeVisible();
  expect(fs.readFileSync(path.join(qaRoot, "config", "command", "qa-command.yaml"), "utf8")).toBe("");
  const saveButton = page.getByRole("button", { name: "保存", exact: true });
  await expect(saveButton).toBeDisabled();
  const blankEditor = page.locator(".monaco-editor").first();
  await blankEditor.locator(".view-lines").click({ position: { x: 24, y: 12 } });
  await page.keyboard.insertText("broken: *missing");
  await expect(blankEditor.locator(".view-lines")).toContainText("broken: *missing");
  await expect(page.locator(".problems-panel")).toBeVisible();
  await expect(page.locator(".monaco-editor .squiggly-error")).toBeVisible();
  await expect(page.locator(".problems-panel code")).toContainText(/\d+:\d+/);
  await expect(saveButton).toBeEnabled();
  await saveButton.click();
  await expect(page.getByRole("status")).toContainText("已保存");
  await expect(saveButton).toBeDisabled();
  expect(fs.readFileSync(path.join(qaRoot, "config", "command", "qa-command.yaml"), "utf8")).toContain("broken: *missing");
  await blankEditor.locator("textarea").press("Control+a");
  await page.keyboard.insertText("valid: true");
  await expect(page.locator(".problems-panel")).toHaveCount(0);
  await expect(page.locator(".monaco-editor .squiggly-error")).toHaveCount(0);
  await expect(saveButton).toBeEnabled();
  await saveButton.click();
  await expect(saveButton).toBeDisabled();
  fs.writeFileSync(
    path.join(qaRoot, "config", "command", "qa-command.yaml"),
    "valid: external-clean\n",
  );
  await expect(blankEditor.locator(".view-lines")).toContainText(
    "valid: external-clean",
    { timeout: 5_000 },
  );
  await expect(page.getByRole("status")).toContainText("已同步外部修改");
  fs.writeFileSync(
    path.join(qaRoot, "config", "command", "qa-command.yaml"),
    "broken: [\n",
  );
  await expect(blankEditor.locator(".view-lines")).toContainText("broken: [", {
    timeout: 5_000,
  });
  await expect(page.locator(".problems-panel")).toBeVisible();
  await expect(page.locator(".monaco-editor .squiggly-error")).toBeVisible();
  await blankEditor.locator("textarea").press("Control+a");
  await page.keyboard.insertText("valid: true");
  await saveButton.click();
  await expect(saveButton).toBeDisabled();
  await blankEditor.locator("textarea").press("Control+a");
  await page.keyboard.insertText("valid: false\nunsaved: keep-me");
  const dirtyFile = page.locator('[data-file="config/command/qa-command.yaml"]');
  await expect(dirtyFile).toHaveAttribute("aria-label", /未保存/);
  await expect(dirtyFile.locator(".tree-dirty")).toBeVisible();
  fs.writeFileSync(
    path.join(qaRoot, "config", "command", "qa-command.yaml"),
    "valid: external-during-draft\n",
  );
  await expect(page.getByRole("status")).toContainText("文件已在外部变化", {
    timeout: 5_000,
  });
  await expect(blankEditor.locator(".view-lines")).toContainText(
    "unsaved: keep-me",
  );
  fs.writeFileSync(
    path.join(qaRoot, "config", "command", "qa-command.yaml"),
    "valid: true",
  );
  await page.locator('[data-file="config/command/hello-world.yaml"]').click();
  await page.locator('[data-file="config/command/qa-command.yaml"]').click();
  await expect(blankEditor.locator(".view-lines")).toContainText("unsaved: keep-me");
  await expect(saveButton).toBeEnabled();
  await blankEditor.locator("textarea").press("Control+a");
  await page.keyboard.insertText("valid: final");
  await expect(saveButton).toBeEnabled();
  await saveButton.click();
  await expect(dirtyFile).not.toHaveAttribute("aria-label", /未保存/);
  await expect(dirtyFile.locator(".tree-dirty")).toHaveCount(0);
  await page.getByRole("button", { name: "收藏配置" }).click();
  await expect
    .poll(() =>
      page.evaluate(() =>
        JSON.parse(localStorage.getItem("localflow-favorite-configs") || "[]"),
      ),
    )
    .toContain("config/command/qa-command.yaml");
  await page.getByRole("button", { name: "重命名" }).click();
  const rename = page.locator(".tree-node input");
  await expect(rename).toBeVisible();
  await rename.fill("qa-renamed");
  await rename.press("Enter");
  await expect(
    page.locator('[data-file="config/command/qa-renamed.yaml"]'),
  ).toBeVisible();
  await expect
    .poll(() =>
      page.evaluate(() =>
        JSON.parse(localStorage.getItem("localflow-favorite-configs") || "[]"),
      ),
    )
    .toEqual(expect.arrayContaining(["config/command/qa-renamed.yaml"]));
  expect(
    await page.evaluate(() =>
      JSON.parse(localStorage.getItem("localflow-favorite-configs") || "[]"),
    ),
  ).not.toContain("config/command/qa-command.yaml");
  await page.getByRole("button", { name: "删除", exact: true }).click();
  await expect(page.getByRole("alertdialog")).toBeVisible();
  await page
    .getByRole("alertdialog")
    .getByRole("button", { name: "删除" })
    .click();
  await expect(page.getByText("qa-renamed", { exact: true })).toHaveCount(0);
  await expect
    .poll(() =>
      page.evaluate(() =>
        JSON.parse(localStorage.getItem("localflow-favorite-configs") || "[]"),
      ),
    )
    .not.toContain("config/command/qa-renamed.yaml");
  await page.locator('[data-file="config/command/qa-invalid.yaml"]').click();
  await expect(page.locator(".config-diagnosis")).toHaveCount(0);
  await expect(page.locator(".configuration-debug")).toContainText("labels");
  await expect(page.locator("button.run-action")).toBeDisabled();
  await page.getByRole("button", { name: "编辑", exact: true }).click();
  await page.locator('[data-file="config/shared/qa-defaults.yaml"]').click();
  await expect(
    page.getByRole("button", { name: "配置无效", exact: true }),
  ).toBeDisabled();
  await page.locator('[data-file="config/verification/demo.yaml"]').click();
  await expect(page.getByText("smoke", { exact: true })).toBeVisible();
  await expect(page.locator('[data-case="case-a"]')).toBeVisible();
  await expect(page.locator(".inspection-item")).toContainText([
    "工作目录",
    "命令",
    "Case",
    "编译日志",
    "运行日志",
    "标签",
  ]);
  await expect(page.locator(".inspection-item.severity-error")).toHaveCount(0);
  await expect(page.locator(".inspection-state")).toHaveCount(0);
  const labelInspection = page.locator(".inspection-item").filter({ hasText: "标签" });
  await expect(labelInspection.locator(".inspection-token")).toHaveText([
    "verification",
  ]);
  await expect(labelInspection.locator(".copy-value")).toHaveCount(0);
  const compileLogList = page
    .locator(".inspection-item")
    .filter({ hasText: "编译日志" })
    .locator(".inspection-code-list");
  await expect(compileLogList.locator(".copy-value")).toHaveCount(2);
  await expect(compileLogList.locator("code")).toHaveText([
    /\$\{case\}\.compile\.log$/,
    /\$\{case\}\.lint\.log$/,
  ]);
  const compileLogGeometry = await compileLogList.evaluate((list) => {
    const owner = list.getBoundingClientRect();
    return {
      ownerWidth: owner.width,
      rows: [...list.querySelectorAll(".copy-field")].map((row) => {
        const rowBox = row.getBoundingClientRect();
        const valueBox = row.querySelector(".copy-value").getBoundingClientRect();
        return { rowWidth: rowBox.width, valueWidth: valueBox.width };
      }),
    };
  });
  expect(compileLogGeometry.rows).toHaveLength(2);
  expect(
    compileLogGeometry.rows.every(
      ({ rowWidth, valueWidth }) =>
        rowWidth >= compileLogGeometry.ownerWidth - 1 &&
        valueWidth >= compileLogGeometry.ownerWidth - 1,
    ),
  ).toBeTruthy();
  const inspectionBeforeCaseInput = await page.locator(".inspection-grid").innerText();
  await expect(page.getByText("Shell", { exact: true })).toHaveCount(0);
  const previewCustomText = page
    .locator('.inspection-item[data-custom-text="true"]')
    .filter({ hasText: "Case: ${case}" })
    .locator(".copy-value");
  await expect(
    page.locator('.inspection-item[data-custom-text="true"] > span:first-child'),
  ).toHaveCount(0);
  await expect(previewCustomText).toBeVisible();
  await expect(previewCustomText.locator(".copy-affordance")).toHaveCount(0);
  await previewCustomText.click();
  await expect(previewCustomText.locator(".copy-affordance")).toHaveCount(0);
  expect(await page.evaluate(() => window.__localflowCopiedText)).toBe(
    "Case: ${case}",
  );
  await expect(page.getByLabel("搜索 Case")).toHaveCount(0);
  await expect(page.locator(".case-count output")).toHaveCount(0);
  await expect(page.locator(".case-step.decrease")).toHaveCount(0);
  await expect(page.locator(".case-step.increase")).toHaveCount(0);
  await expect(
    page.getByRole("button", { name: "运行", exact: true }),
  ).toBeDisabled();
  await expect(page.getByLabel("随机种子")).toHaveValue("");
  await expect(page.locator(".workbench-context").getByText("demo.yaml", { exact: true })).toBeVisible();
  const caseListBox = await page.locator(".case-list").boundingBox();
  const caseBoxes = await page.locator(".case-item").evaluateAll((nodes) =>
    nodes.map((node) => {
      const box = node.getBoundingClientRect();
      return { width: box.width, height: box.height, x: box.x, y: box.y };
    }),
  );
  expect(
    caseBoxes.every(
      (box) => box.height <= 40 && box.width / caseListBox.width >= 0.95,
    ),
  ).toBeTruthy();
  expect(new Set(caseBoxes.map((box) => Math.round(box.x))).size).toBe(1);
  expect(new Set(caseBoxes.map((box) => Math.round(box.y))).size).toBe(
    caseBoxes.length,
  );
  const firstCaseMain = page.locator(".case-main").first();
  const idleCaseBorder = await page
    .locator(".case-item")
    .first()
    .evaluate((node) => getComputedStyle(node).borderColor);
  await firstCaseMain.focus();
  const focusedCaseBorder = await page
    .locator(".case-item")
    .first()
    .evaluate((node) => getComputedStyle(node).borderColor);
  expect(focusedCaseBorder).not.toBe(idleCaseBorder);
  await expect(page.locator(".case-count output")).toHaveCount(0);
  const caseTransitions = await page
    .locator(".case-item")
    .first()
    .evaluate((node) =>
      getComputedStyle(node)
        .transitionDuration.split(",")
        .map(
          (value) =>
            Number.parseFloat(value) * (value.includes("ms") ? 0.001 : 1),
        ),
    );
  expect(Math.max(...caseTransitions)).toBeLessThanOrEqual(0.1);
  await page.screenshot({
    path: path.join(evidence, "admin-run-verification-empty-dark.png"),
    fullPage: true,
  });
  const caseA = page.locator('[data-case="case-a"]');
  await caseA.hover();
  await page.mouse.wheel(0, -100);
  await expect(caseA.locator(".case-count output")).toHaveCount(0);
  await page.mouse.wheel(0, 100);
  await expect(caseA.locator(".case-count output")).toHaveCount(0);
  const caseB = page.locator('[data-case="case-b"]');
  const increaseB = caseB.getByRole("button", { name: /增加 case-b 次数/ });
  await increaseB.click();
  await expect(caseB.locator(".case-count output")).toHaveText("1");
  await expect.poll(() => page.locator(".inspection-grid").innerText()).toBe(
    inspectionBeforeCaseInput,
  );
  await caseB.locator(".case-count output").click();
  await expect(caseB.locator(".case-count output")).toHaveText("2");
  await caseB.getByRole("button", { name: "减少 case-b 次数" }).click();
  await expect(caseB.locator(".case-count output")).toHaveText("1");
  await expect(
    page.locator('.inspection-item[data-custom-text="true"] .copy-value'),
  ).toHaveText(["Case: ${case}", "Seed: ${seed}"]);
  await page.waitForTimeout(720);
  await expect(caseB.locator(".case-count output")).toHaveText("1");
  await expect(caseB.getByRole("button", { name: "减少 case-b 次数" })).toBeVisible();
  const increaseBBox = await increaseB.boundingBox();
  await page.mouse.move(
    increaseBBox.x + increaseBBox.width / 2,
    increaseBBox.y + increaseBBox.height / 2,
  );
  await page.mouse.down();
  await page.waitForTimeout(780);
  await page.mouse.up();
  const heldCount = Number(await caseB.locator(".case-count output").textContent());
  expect(heldCount).toBeGreaterThanOrEqual(3);
  expect(heldCount).toBeLessThanOrEqual(6);
  const persistentRunToggle = page.getByRole("button", { name: "配置", exact: true });
  await persistentRunToggle.click();
  await expect(page.locator("#run-panel")).toBeHidden();
  await expect(persistentRunToggle).toHaveAttribute("aria-expanded", "false");
  await persistentRunToggle.click();
  await expect(persistentRunToggle).toHaveAttribute("aria-expanded", "true");
  await expect(page.locator('[data-case="case-b"] .case-count output')).toHaveText(String(heldCount));
  await page.getByRole("tab", { name: "设置" }).click();
  await openRunPanel(page);
  await expect(
    page.locator('[data-file="config/verification/demo.yaml"]'),
  ).toHaveClass(/selected/);
  await expect(page.locator('[data-case="case-b"] .case-count output')).toHaveText(String(heldCount));
  for (let index = 0; index < heldCount; index += 1)
    await page.getByRole("button", { name: "减少 case-b 次数" }).click();
  await expect(page.locator(".case-count output")).toHaveCount(0);
  await expect(page.locator(".case-step.decrease")).toHaveCount(0);
  const caseGrid = await page.locator(".case-list").boundingBox();
  await page.mouse.move(caseGrid.x + 4, caseGrid.y + 4);
  await page.mouse.down();
  await page.mouse.move(
    caseGrid.x + caseGrid.width - 4,
    caseGrid.y + caseGrid.height - 4,
    { steps: 8 },
  );
  await page.mouse.up();
  await expect(page.locator('.case-main[aria-pressed="true"]')).toHaveCount(3);
  await expect(page.locator(".case-count output")).toHaveCount(0);
  const groupIncrease = page.getByRole("button", { name: /增加 case-a 次数.*应用到已框选 Case/ });
  await groupIncrease.click();
  await groupIncrease.click();
  await groupIncrease.click();
  await groupIncrease.click();
  await expect(page.locator(".case-count output")).toHaveText(["4", "4", "4"]);
  await page.screenshot({
    path: path.join(evidence, "admin-run-verification-scope-dark.png"),
    fullPage: true,
  });
  await page.locator(".workbench-header>div:first-child").click();
  await expect(page.locator('.case-main[aria-pressed="true"]')).toHaveCount(0);
  await expect(page.getByRole("toolbar", { name: /Case/ })).toHaveCount(0);
  await page.screenshot({
    path: path.join(evidence, "admin-run-verification-dark.png"),
    fullPage: true,
  });
  const actionHeights = await page
    .locator(".workbench-actions button")
    .evaluateAll((items) =>
      items.map((item) => item.getBoundingClientRect().height),
    );
  expect(
    actionHeights.every((height) => height >= 34 && height <= 38),
  ).toBeTruthy();
  const runButton = page.getByRole("button", { name: "运行", exact: true });
  await expect(runButton).toBeVisible();
  await expect(runButton).toContainText("运行");
  const runBox = await runButton.boundingBox();
  expect(runBox.width).toBeGreaterThan(runBox.height);
  await page.locator('[data-file="config/generic-picker/demo.yaml"]').click();
  await expect(page.locator('[data-case="case-a"]')).toBeVisible();
  await page.getByRole("button", { name: /增加 case-a 次数/ }).click();
  await page.getByRole("button", { name: /增加 case-a 次数/ }).click();
  await expect(page.locator('[data-case="case-a"] .case-count output')).toHaveText("2");
  const genericRunResponse = page.waitForResponse(
    (response) =>
      response
        .url()
        .endsWith("/api/v1/config/files/generic-picker/demo.yaml/runs") &&
      response.request().method() === "POST",
  );
  await page.getByRole("button", { name: "运行", exact: true }).click();
  expect((await genericRunResponse).json()).resolves.toMatchObject({
    count: 2,
  });
  await expect(page.locator(".case-count output")).toHaveCount(0);
  await page.locator('[data-file="config/command/hello-world.yaml"]').click();
  await expect(page.getByRole("button", { name: "编辑" })).toBeVisible();
  const headerBeforeNotice = await page
    .locator(".workbench-header")
    .boundingBox();
  const explorerBeforeNotice = await page.locator(".explorer").boundingBox();
  await page.getByRole("button", { name: "运行", exact: true }).click();
  const configNotice = page.getByText(/已加入 1 个任务/);
  await expect(configNotice).toBeVisible();
  await expect(configNotice).toHaveCSS("position", "fixed");
  expect(await page.locator(".workbench-header").boundingBox()).toEqual(
    headerBeforeNotice,
  );
  expect(await page.locator(".explorer").boundingBox()).toEqual(
    explorerBeforeNotice,
  );
  await expect(configNotice).toHaveCount(0, { timeout: 5_000 });
  const rememberedFolder = page.locator('[data-file="folder:config/verification"]');
  await rememberedFolder.click();
  await expect(page.locator('[data-file="config/verification/demo.yaml"]')).toHaveCount(0);
  await expect.poll(() => page.evaluate(() =>
    localStorage.getItem("localflow-explorer-collapsed"),
  )).toContain("folder:config/verification");
  await page.getByRole("tab", { name: "终端" }).click();
  await page.getByRole("tab", { name: "任务" }).click();
  await openRunPanel(page);
  await expect(page.locator('[data-file="config/verification/demo.yaml"]')).toHaveCount(0);
  await page.locator('[data-file="folder:config/verification"]').click();
  await expect(page.locator('[data-file="config/verification/demo.yaml"]')).toBeVisible();
  await page.screenshot({
    path: path.join(evidence, "admin-config-explorer-dark.png"),
    fullPage: true,
  });
  await page.getByRole("tab", { name: "任务" }).click();
  await expect(page.getByRole("button", { name: /hello-world/ })).toBeVisible({
    timeout: 20_000,
  });
  const helloTask = page
    .locator(".task-item")
    .filter({ has: page.locator(".task-name b", { hasText: "hello-world" }) })
    .first();
  await helloTask.locator(".task-row").click();
  const displayedCommand = helloTask.locator('.copy-field').filter({ hasText: "命令" });
  await expect(displayedCommand.locator("code")).not.toBeEmpty();
  await expect(displayedCommand).not.toContainText("/bin/");
  await expect(displayedCommand).not.toContainText(" -ic ");
  await expect(displayedCommand).not.toContainText("cd ");

  await expect(page.getByRole("tab", { name: "插件" })).toHaveCount(0);
  await expect(page.getByRole("tab", { name: "API" })).toHaveCount(0);
  const violations = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .analyze();
  expect(
    violations.violations.filter((item) =>
      ["serious", "critical"].includes(item.impact),
    ),
    JSON.stringify(violations.violations, null, 2),
  ).toEqual([]);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("tab", { name: "任务" }).click();
  expect(
    await page.evaluate(
      () =>
        document.documentElement.scrollWidth -
        document.documentElement.clientWidth,
    ),
  ).toBeLessThanOrEqual(0);
  await page.getByRole("tab", { name: "任务" }).press("ArrowDown");
  await expect(page.getByRole("tab", { name: "终端" })).toBeFocused();
  await page.screenshot({
    path: path.join(evidence, "admin-mobile-390.png"),
    fullPage: true,
  });
  expect(consoleErrors, consoleErrors.join("\n")).toEqual([]);
  expect(
    validationRejections.filter(
      (url) =>
        !url.endsWith(
          "/api/v1/config/files/command/qa-invalid.yaml/inspection",
        ),
    ),
  ).toEqual([]);

  await runAcceptance(page);
  await page.setViewportSize({ width: 1440, height: 960 });
  await page.getByRole("tab", { name: "设置" }).click();
  const settingsBeforeDialog = await page.locator(".settings-panel").boundingBox();
  const exitTrigger = page.getByRole("button", { name: "退出", exact: true });
  await exitTrigger.click();
  const shutdownDialog = page.getByRole("alertdialog");
  await expect(shutdownDialog).toBeVisible();
  await expect(shutdownDialog).toContainText("退出 LocalFlow？");
  await expect(shutdownDialog.getByRole("button", { name: "取消" })).toBeFocused();
  expect(await page.locator(".settings-panel").boundingBox()).toEqual(
    settingsBeforeDialog,
  );
  await page.keyboard.press("Escape");
  await expect(shutdownDialog).toHaveCount(0);
  await expect(exitTrigger).toBeFocused();

  let shutdownRequests = 0;
  await page.route("**/api/v1/system/shutdown", async (route) => {
    shutdownRequests += 1;
    await route.fulfill({
      status: 202,
      contentType: "application/json",
      body: JSON.stringify({ status: "stopping" }),
    });
  });
  await exitTrigger.click();
  await shutdownDialog.getByRole("button", { name: "退出", exact: true }).click();
  await expect(
    shutdownDialog.getByRole("button", { name: "正在退出", exact: true }),
  ).toBeDisabled();
  expect(shutdownRequests).toBe(1);
  await page.screenshot({
    path: path.join(evidence, "admin-shutdown-confirmation.png"),
    fullPage: true,
  });
  const repository = path.resolve("..");
  const boundFiles = [
    "frontend/index.html",
    "frontend/public/compat-boot.js",
    "frontend/public/theme-boot.js",
    "frontend/src/App.jsx",
    "frontend/src/MonacoEditors.jsx",
    "frontend/src/Tooltip.jsx",
    "frontend/src/api.js",
    "frontend/src/main.jsx",
    "frontend/src/index.css",
    "frontend/src/extra.css",
    "frontend/src/round6.css",
    "frontend/src/round7.css",
    "frontend/src/case-picker.css",
    "frontend/e2e/ui-quality.js",
    "frontend/e2e/localflow.spec.js",
    "frontend/e2e/compatibility.spec.js",
    "frontend/e2e/shutdown-live.spec.js",
    "frontend/e2e/legacy-browser.mjs",
    "frontend/playwright.config.js",
    "frontend/vite.config.js",
    "frontend/package.json",
    "frontend/package-lock.json",
    "quality/resource-budgets.json",
    "tools/check_quality.py",
    "tools/run_browser_quality.py",
    "tools/run_linux_browser_quality.py",
    "tests_target/test_browser_shutdown.py",
  ];
  const sourceFiles = Object.fromEntries(
    boundFiles.map((relative) => [
      relative,
      sha256(path.join(repository, relative), true),
    ]),
  );
  const screenshots = Object.fromEntries(
    fs
      .readdirSync(evidence)
      .filter(
        (name) =>
          name.endsWith(".png") &&
          (name.startsWith("admin-") || name.startsWith("anonymous-")),
      )
      .sort()
      .map((name) => [name, sha256(path.join(evidence, name))]),
  );
  const initialEntry = fs
    .readdirSync(path.resolve("dist/assets"))
    .find((name) => /^index-legacy-.*\.js$/.test(name));
  if (!initialEntry) throw new Error("built legacy application entry is missing");
  const bundleMetrics = {
    initial_legacy_entry_gzip_mib: Number(
      (
        zlib.gzipSync(fs.readFileSync(path.resolve("dist/assets", initialEntry)), {
          level: 9,
        }).length /
        1024 /
        1024
      ).toFixed(3),
    ),
  };
  fs.writeFileSync(
    path.join(evidence, "browser-receipt.json"),
    JSON.stringify(
      {
        completed_at: new Date().toISOString(),
        browser: "Microsoft Edge",
        browser_version: browser.version(),
        base_url: process.env.LOCALFLOW_QA_URL,
        result: "passed",
        source_files: sourceFiles,
        screenshots,
        resource_contract: resourceContract,
        resource_metrics: resourceMetrics,
        bundle_metrics: bundleMetrics,
        assertions: [
          "testing-ui-revision-auto-reload",
          "secret-login-required",
          "secret-login-error",
          "login-control-disappears",
          "persistent-browser-session",
          "nav-order",
          "removed-plugin-api-destinations",
          "compact-content-height-nav",
          "nav-target-size",
          "theme-memory",
          "run-context-memory",
          "aligned-settings-rows",
          "live-time-calibration-control",
          "single-time-calibration",
          "shutdown-alert-dialog",
          "shutdown-cancel-focus-restore",
          "shutdown-no-layout-shift",
          "shutdown-single-submit",
          "inline-toggle-detail",
          "dedicated-terminal",
          "xterm-fit-search",
          "terminal-xterm-write-ack",
          "explorer-create-rename-delete",
          "explorer-directory-copy-cut-paste",
          "explorer-external-plugin-sync",
          "explorer-plugin-neutral-icon",
          "explorer-generated-file-exclusion",
          "explorer-icon-only-state",
          "shared-fragment-semantic-icon",
          "neutral-config-filenames",
          "hidden-config-extensions",
          "opened-invalid-inline-diagnosis",
          "config-opens-in-use-mode",
          "plugin-config-discovery",
          "run-fields-only",
          "plugin-case-field-mapping",
          "case-empty-default",
          "case-wheel-noop",
          "case-row-increment",
          "case-delayed-press-repeat",
          "config-root-only",
          "config-free-save-inline-syntax",
          "config-external-valid-invalid-live-sync",
          "config-external-change-preserves-dirty-draft",
          "config-adaptive-focused-pane",
          "config-one-action-task-reveal",
          "config-default-expanded",
          "config-dirty-save",
          "config-quick-history",
          "config-code-list-full-width",
          "common-config-path-identity",
          "terminal-bounded-archive-search",
          "terminal-output-freshness",
          "case-marquee-scope-only",
          "case-group-relative-edit",
          "case-group-fixed-edit",
          "case-scope-dismissal",
          "case-single-column-full-width",
          "case-focus-visible-fast-feedback",
          "blank-seed",
          "verification-concise-task-detail",
          "terminal-grouped-unread-output",
          "required-run-field-gate",
          "icon-only-run",
          "uniform-control-geometry",
          "nonblocking-expiring-status",
          "config-use",
          "plugin-arbitrary-status",
          "idle-web-resource-budget",
          "compact-copyable-task-detail",
          "task-detail-array-lines",
          "task-detail-start-time-label",
          "monaco-deferred-bundle",
          "neutral-scroll-copy-feedback",
          "unboxed-stop-action",
          "direct-config-file-actions",
          "terminal-responsive-fit",
          "terminal-fill-layout",
          "terminal-readonly-history-search",
          "tooltip-portal-clipping-pixel-layer",
          "run-submitting-accepted-duplicate-lock",
          "task-row-state-geometry",
          "hello-world-log-lifecycle",
          "start-time-log-path",
          "wcag-a-aa",
          "mobile-no-overflow",
        ],
      },
      null,
      2,
    ),
  );
});

test("common configurations use complete paths and preserve context", async ({
  page,
}) => {
  await openAdminTaskWorkspace(page);
  const resourceTab = page.getByRole("tab", { name: "资源", exact: true });
  const quickTab = page.getByRole("tab", { name: "常用", exact: true });
  await expect(page.locator(".top .config-source-tab")).toHaveCount(0);
  await expect(page.locator(".explorer .config-source-tabs")).toContainText(
    "资源常用",
  );
  await expect(resourceTab).toHaveAttribute("aria-selected", "true");
  await expect(quickTab).toHaveAttribute("aria-selected", "false");

  await page.locator('[data-file="config/command/hello-world.yaml"]').click();
  await page.locator(".run-action").click();
  await expect(page.locator(".run-action")).toContainText("已创建");
  const favorite = page.getByRole("button", { name: "收藏配置" });
  await expect(favorite).toHaveAttribute("aria-pressed", "false");
  await favorite.click();
  await expect(
    page.getByRole("button", { name: "取消收藏" }),
  ).toHaveAttribute("aria-pressed", "true");
  expect(
    await page.evaluate(() =>
      JSON.parse(localStorage.getItem("localflow-favorite-configs") || "[]"),
    ),
  ).toContain("config/command/hello-world.yaml");

  await quickTab.click();
  await expect(quickTab).toHaveAttribute("aria-selected", "true");
  await expect(
    page.locator('#config-source-panel[data-explorer-view="quick"]'),
  ).toBeVisible();
  await expect(page.getByRole("heading", { name: "已收藏" })).toBeVisible();
  const pinned = page.getByRole("list", { name: "已收藏" });
  const pinnedPath = pinned.getByRole("button", {
    name: "config/command/hello-world.yaml",
    exact: true,
  });
  await expect(pinnedPath).toBeVisible();
  await expect(pinnedPath).toHaveText("config/command/hello-world.yaml");
  await expect(pinnedPath.locator("strong, small, em")).toHaveCount(0);
  const pinnedGeometry = await pinnedPath.evaluate((button) => ({
    clientWidth: button.clientWidth,
    scrollWidth: button.scrollWidth,
    clientHeight: button.clientHeight,
    scrollHeight: button.scrollHeight,
  }));
  expect(pinnedGeometry.scrollWidth).toBeLessThanOrEqual(
    pinnedGeometry.clientWidth,
  );
  expect(pinnedGeometry.scrollHeight).toBeLessThanOrEqual(
    pinnedGeometry.clientHeight,
  );
  await expect(page.getByRole("button", { name: "新建文件" })).toHaveCount(0);

  await page.route(
    "**/api/v1/workspace/files/config/command/hello-world.yaml",
    (route) => route.fulfill({ status: 404, body: "configuration moved" }),
  );
  await pinnedPath.click();
  await expect(page.getByRole("heading", { name: "已收藏" })).toHaveCount(0);
  expect(
    await page.evaluate(() =>
      JSON.parse(localStorage.getItem("localflow-favorite-configs") || "[]"),
    ),
  ).not.toContain("config/command/hello-world.yaml");
  await expect(page.locator(".config-workbench")).toBeVisible();
  await expect(page.getByText("打开失败", { exact: false })).toHaveCount(0);
  await page.unroute(
    "**/api/v1/workspace/files/config/command/hello-world.yaml",
  );
  await page.getByRole("button", { name: "收藏配置" }).click();
  await expect(page.getByRole("heading", { name: "已收藏" })).toBeVisible();

  await page.reload();
  await expect(
    page.getByRole("tab", { name: "常用", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "常用", exact: true }).press("ArrowLeft");
  await expect(
    page.getByRole("tab", { name: "资源", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await page.getByRole("tab", { name: "资源", exact: true }).press("End");
  await expect(
    page.getByRole("tab", { name: "常用", exact: true }),
  ).toHaveAttribute("aria-selected", "true");
  await expect(page.getByRole("list", { name: "已收藏" })).toContainText(
    "hello-world",
  );
  await page.getByRole("button", { name: "取消收藏" }).click();
  await expect(page.getByRole("heading", { name: "已收藏" })).toHaveCount(0);
  await expect(page.getByRole("list", { name: "最近使用" })).toContainText(
    "hello-world",
  );
  await page.screenshot({
    path: path.join(evidence, "admin-common-configurations-light.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "配置", exact: true }).click();
  await expect(
    page.getByRole("tab", { name: "常用", exact: true }),
  ).not.toBeVisible();
  finalizeBrowserReceipt();
});

test("terminal to task navigation preserves the workbench within a paint budget", async ({
  page,
}) => {
  await openAdminTaskWorkspace(page);
  await page.locator('[data-file="config/command/hello-world.yaml"]').click();
  await page.locator(".config-explorer").evaluate((node) => {
    node.dataset.qaPreserved = "true";
  });
  const treeBefore = await page.locator(".tree-host").boundingBox();
  await page.getByRole("tab", { name: "终端" }).click();
  await expect(page.locator(".task-workspace")).toBeHidden();
  const duration = await page.evaluate(
    () =>
      new Promise((resolve) => {
        const started = performance.now();
        document.getElementById("nav-tasks").click();
        requestAnimationFrame(() =>
          requestAnimationFrame(() => resolve(performance.now() - started)),
        );
      }),
  );
  expect(duration).toBeLessThan(
    resourceContract.interaction_limits.terminal_to_tasks_next_paint_ms,
  );
  await expect(page.locator('.config-explorer[data-qa-preserved="true"]')).toBeVisible();
  await expect(page.locator(".terminal-page")).toHaveCount(0);
  const treeAfter = await page.locator(".tree-host").boundingBox();
  expect(Math.abs(treeAfter.width - treeBefore.width)).toBeLessThanOrEqual(1);
  expect(Math.abs(treeAfter.height - treeBefore.height)).toBeLessThanOrEqual(1);
  const receiptPath = path.join(evidence, "browser-receipt.json");
  const receipt = JSON.parse(fs.readFileSync(receiptPath, "utf8"));
  receipt.interaction_metrics = {
    ...(receipt.interaction_metrics || {}),
    terminal_to_tasks_next_paint_ms: Number(duration.toFixed(3)),
  };
  if (!receipt.assertions.includes("task-route-next-paint"))
    receipt.assertions.push("task-route-next-paint");
  fs.writeFileSync(receiptPath, JSON.stringify(receipt, null, 2));
});

test("a sourced task shows its environment file in task details", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("tab", { name: "设置" }).click();
  await ensureAdminSession(page);
  const sourcePath = path.join(qaRoot, "browser-source.sh");
  fs.writeFileSync(sourcePath, "export BROWSER_SOURCE=visible\n");
  const created = await browserApi(page, "/tasks", {
    method: "POST",
    body: {
      name: "browser-source-visibility",
      working_directory: qaRoot,
      source: [sourcePath],
      command: "echo $BROWSER_SOURCE",
    },
  });
  const detail = await browserApi(page, `/tasks/${created.task_id}`);
  expect(path.isAbsolute(detail.source_files[0])).toBe(true);
  await page.getByRole("tab", { name: "任务" }).click();
  const row = page.locator(".task-item").filter({ hasText: "browser-source-visibility" });
  await expect(row).toBeVisible();
  await row.locator(".task-row").click();
  const sources = row.locator(".task-list-field").filter({ hasText: "加载环境" });
  await expect(sources).toContainText(detail.source_files[0]);
  await expect.poll(async () => (await browserApi(page, `/tasks/${created.task_id}`)).state).toMatch(
    /^(failed|succeeded)$/,
  );
  const receiptPath = path.join(evidence, "browser-receipt.json");
  const receipt = JSON.parse(fs.readFileSync(receiptPath, "utf8"));
  if (!receipt.assertions.includes("task-source-detail"))
    receipt.assertions.push("task-source-detail");
  fs.writeFileSync(receiptPath, JSON.stringify(receipt, null, 2));
});
