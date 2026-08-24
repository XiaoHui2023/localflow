import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

const evidence = path.resolve("../quality/evidence/browser");
const qaRoot = process.env.LOCALFLOW_QA_ROOT;
const qaPython = process.env.LOCALFLOW_QA_PYTHON;
const loginCode = process.env.LOCALFLOW_QA_LOGIN_CODE;

function sha256(file) {
  return crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex");
}

async function browserApi(page, endpoint, options = {}) {
  return page.evaluate(async ({ endpoint, options }) => {
    const method = options.method || "GET";
    const headers = { ...(options.body ? { "Content-Type": "application/json" } : {}) };
    if (method !== "GET") {
      const session = await fetch("/api/v1/auth/session");
      if (!session.ok) throw new Error(`session ${session.status}`);
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
  }, { endpoint, options });
}

async function waitForState(page, taskId, states) {
  await expect.poll(async () => {
    const task = await browserApi(page, `/tasks/${taskId}`);
    return task.state;
  }, { timeout: 20_000 }).toMatch(new RegExp(`^(${states.join("|")})$`));
}

test("read-only and administrator workflows remain usable in a real browser", async ({ page, browser }) => {
  fs.mkdirSync(evidence, { recursive: true });
  const browserVersion = browser.version();
  const consoleErrors = [];
  page.on("console", (message) => {
    if (message.type() === "error") consoleErrors.push(message.text());
  });
  page.on("pageerror", (error) => consoleErrors.push(error.message));

  await page.goto("/");
  await expect(page.getByRole("heading", { name: "任务中心" })).toBeVisible();
  await expect(page.locator(".role")).toContainText("摘要只读");
  await expect(page.getByRole("button", { name: "运行模板" })).toHaveCount(0);
  await expect(page.getByRole("button", { name: "配置" })).toHaveCount(0);

  const login = page.getByRole("textbox", { name: "管理员登录码" });
  await login.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("代码无效")).toBeVisible();
  expect(consoleErrors).toEqual([
    "Failed to load resource: the server responded with a status of 401 (Unauthorized)",
  ]);
  consoleErrors.length = 0;
  await login.fill(loginCode);
  await page.keyboard.press("Enter");
  await expect(page.locator(".role")).toContainText("管理员");
  await expect(page.getByRole("button", { name: "运行模板" })).toBeVisible();
  await expect(page.getByRole("button", { name: "配置" })).toBeVisible();

  const fast = await browserApi(page, "/tasks", {
    method: "POST",
    body: {
      name: "qa-finished",
      working_directory: qaRoot,
      command: [qaPython, "-c", "print('qa-finished-output', flush=True)"],
      labels: ["browser", "finished"],
      custom: { report: "qa://finished" },
    },
  });
  await waitForState(page, fast.task_id, ["succeeded"]);
  await page.getByRole("button", { name: "刷新" }).click();
  const finishedRow = page.getByRole("button", { name: /qa-finished/ });
  await expect(finishedRow).toContainText("新完成");
  await finishedRow.focus();
  await expect(finishedRow).not.toContainText("新完成");
  await finishedRow.click();
  await expect(page.getByRole("heading", { name: "qa-finished" })).toBeVisible();
  await expect(page.getByText("qa://finished", { exact: true })).toBeVisible();
  await expect(page.locator(".details pre").first()).toContainText("qa-finished-output");
  await page.screenshot({ path: path.join(evidence, "admin-task-detail.png"), fullPage: true });

  const longTask = await browserApi(page, "/tasks", {
    method: "POST",
    body: {
      name: "qa-terminal",
      working_directory: qaRoot,
      command: [qaPython, "-c", "import time; print('qa-terminal-ready', flush=True); time.sleep(30)"],
      labels: ["browser", "terminal"],
    },
  });
  await waitForState(page, longTask.task_id, ["running"]);
  await page.getByRole("button", { name: "刷新" }).click();
  await page.getByRole("button", { name: /qa-terminal/ }).click();
  await page.getByRole("button", { name: "终端" }).click();
  await expect(page.locator(".terminal .xterm")).toBeVisible();
  await expect(page.locator(".xterm-rows")).toContainText("终端已连接");
  await expect(page.locator(".xterm-rows")).toContainText("qa-terminal-ready");
  await page.getByRole("button", { name: "详情" }).click();
  await page.getByRole("button", { name: "温和中断" }).click();
  await waitForState(page, longTask.task_id, ["cancelled", "failed"]);

  await page.getByRole("button", { name: "运行模板" }).click();
  await expect(page.getByRole("heading", { name: "运行模板" })).toBeVisible();
  await expect(page.getByText("declarative", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: /verification/ }).click();
  await page.getByLabel("Case 目录").fill(path.join(qaRoot, "qa-cases"));
  await page.getByRole("button", { name: "扫描目录" }).click();
  await expect(page.getByText("case-a", { exact: true })).toBeVisible();
  await expect(page.getByText("case-b", { exact: true })).toBeVisible();
  await page.getByLabel("搜索 case").fill("case-a");
  await page.getByRole("button", { name: "全选当前结果" }).click();
  await expect(page.getByRole("checkbox")).toBeChecked();
  await page.screenshot({ path: path.join(evidence, "admin-template-cases.png"), fullPage: true });

  await page.getByRole("button", { name: "配置", exact: true }).click();
  await expect(page.getByRole("heading", { name: "配置文件" })).toBeVisible();
  await expect(page.locator(".monaco-editor")).toBeVisible({ timeout: 20_000 });
  await page.getByLabel("新配置文件路径").fill("qa/browser.yaml");
  await page.getByRole("button", { name: "新建" }).click();
  await expect(page.getByText("配置文件已创建")).toBeVisible();
  await page.screenshot({ path: path.join(evidence, "admin-config-monaco.png"), fullPage: true });

  const violations = await new AxeBuilder({ page }).withTags(["wcag2a", "wcag2aa"]).analyze();
  const serious = violations.violations.filter((item) => ["serious", "critical"].includes(item.impact));
  expect(serious, JSON.stringify(serious, null, 2)).toEqual([]);

  await page.getByRole("button", { name: "任务中心" }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.getByRole("heading", { name: "任务中心" })).toBeVisible();
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  expect(overflow).toBeLessThanOrEqual(0);
  const navigationButtonHeights = await page.locator(".top nav button").evaluateAll(
    (buttons) => buttons.map((button) => button.getBoundingClientRect().height),
  );
  expect(Math.max(...navigationButtonHeights)).toBeLessThanOrEqual(50);
  await page.screenshot({ path: path.join(evidence, "admin-mobile-390.png"), fullPage: true });

  expect(consoleErrors, consoleErrors.join("\n")).toEqual([]);
  const repository = path.resolve("..");
  const boundFiles = [
    "frontend/src/App.jsx",
    "frontend/src/main.jsx",
    "frontend/src/index.css",
    "frontend/src/extra.css",
    "frontend/src/case-picker.css",
    "frontend/e2e/localflow.spec.js",
    "frontend/playwright.config.js",
    "frontend/package-lock.json",
    "tools/run_browser_quality.py",
  ];
  const sourceFiles = Object.fromEntries(
    boundFiles.map((relative) => [relative, sha256(path.join(repository, relative))]),
  );
  const screenshots = Object.fromEntries(
    fs.readdirSync(evidence)
      .filter((name) => name.endsWith(".png") && name.startsWith("admin-"))
      .sort()
      .map((name) => [name, sha256(path.join(evidence, name))]),
  );
  fs.writeFileSync(path.join(evidence, "browser-receipt.json"), JSON.stringify({
    completed_at: new Date().toISOString(),
    browser: "Microsoft Edge",
    browser_version: browserVersion,
    base_url: process.env.LOCALFLOW_QA_URL,
    result: "passed",
    source_files: sourceFiles,
    screenshots,
    assertions: [
      "anonymous-summary-readonly",
      "keyboard-login-and-admin-navigation",
      "newly-completed-acknowledgement",
      "admin-detail-projection",
      "xterm-live-output-and-interrupt",
      "verification-case-discovery-selection",
      "monaco-config-create",
      "wcag-a-aa-no-serious-or-critical",
      "390px-no-horizontal-overflow",
      "390px-single-line-navigation",
      "no-browser-console-errors",
    ],
  }, null, 2));
});
