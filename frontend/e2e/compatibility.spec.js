import fs from "node:fs";
import path from "node:path";
import { expect, test } from "@playwright/test";

async function api(page, endpoint, options = {}) {
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
      const body = await response.text();
      if (!response.ok) throw new Error(`${response.status}: ${body}`);
      return body ? JSON.parse(body) : null;
    },
    { endpoint, options },
  );
}

async function waitForState(page, taskId, states) {
  await expect
    .poll(async () => (await api(page, `/tasks/${taskId}`)).state, {
      timeout: 20_000,
    })
    .toMatch(new RegExp(`^(${states.join("|")})$`));
}

test("Ubuntu browser can operate the released web console", async ({
  page,
  browser,
  browserName,
}, testInfo) => {
  const errors = [];
  const failedRequests = [];
  let eventResponses = 0;
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("response", (response) => {
    if (response.url().endsWith("/api/v1/events") && response.status() === 200)
      eventResponses += 1;
  });
  page.on("requestfailed", (request) => {
    const reason = request.failure()?.errorText || "unknown failure";
    const expectedEventClose =
      request.url().endsWith("/api/v1/events") && /ABORT/i.test(reason);
    if (!expectedEventClose)
      failedRequests.push(`${request.method()} ${request.url()}: ${reason}`);
  });
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

  await page.goto("/", { waitUntil: "networkidle" });
  expect(await page.evaluate(() => window.isSecureContext)).toBeFalsy();
  expect(await page.evaluate(() => window.__localflowBootErrors || [])).toEqual(
    [],
  );
  await expect(page.locator("#root")).not.toBeEmpty();
  await expect(page.getByRole("tab")).toHaveText(["任务", "设置"]);
  await page.getByRole("tab", { name: "设置" }).click();
  await page.getByLabel("管理员秘钥").fill(process.env.LOCALFLOW_QA_ADMIN_KEY);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("tab")).toHaveText([
    "任务",
    "终端",
    "设置",
  ]);

  await page.getByRole("tab", { name: "任务" }).click();
  const runPanelToggle = page.getByRole("button", { name: "运行配置" });
  await expect(runPanelToggle).toHaveAttribute("aria-expanded", "false");
  await runPanelToggle.click();
  await expect(runPanelToggle).toHaveAttribute("aria-expanded", "true");
  await expect(
    page.locator('[data-file="config/command/hello-world.yaml"]'),
  ).toBeVisible();
  await page.locator('[data-file="config/command/hello-world.yaml"]').click();
  await page.getByRole("button", { name: "编辑" }).click();
  await expect(page.locator(".monaco-editor")).toBeVisible({ timeout: 20_000 });

  const finished = await api(page, "/tasks", {
    method: "POST",
    body: {
      name: `${browserName}-compat-finished`,
      working_directory: process.env.LOCALFLOW_QA_ROOT,
      command: [
        process.env.LOCALFLOW_QA_PYTHON,
        "-c",
        "print('browser-compat-ok', flush=True)",
      ],
      labels: ["browser-compat"],
      custom: { report: "qa://ubuntu-browser" },
    },
  });
  await waitForState(page, finished.task_id, ["succeeded"]);
  await page.getByRole("tab", { name: "任务" }).click();
  const finishedRow = page.getByRole("button", {
    name: new RegExp(`${browserName}-compat-finished`),
  });
  await finishedRow.click();
  const copyValue = page
    .locator(".task-item.open .copy-value")
    .filter({ hasText: "qa://ubuntu-browser" });
  await copyValue.click();
  await expect(copyValue.locator("..")).toHaveAttribute("data-copied", "true");
  expect(await page.evaluate(() => window.__localflowCopiedText)).toBe(
    "qa://ubuntu-browser",
  );

  const live = await api(page, "/tasks", {
    method: "POST",
    body: {
      name: `${browserName}-compat-terminal`,
      working_directory: process.env.LOCALFLOW_QA_ROOT,
      command: [
        process.env.LOCALFLOW_QA_PYTHON,
        "-c",
        "import time; print('terminal-compat-ready', flush=True); time.sleep(30)",
      ],
      labels: ["browser-compat"],
    },
  });
  await waitForState(page, live.task_id, ["running"]);
  await page.getByRole("tab", { name: "终端" }).click();
  await expect(page.locator(".terminal-page .xterm-rows")).toContainText(
    "terminal-compat-ready",
    { timeout: 20_000 },
  );
  await api(page, `/tasks/${live.task_id}/interrupt`, { method: "POST" });
  await waitForState(page, live.task_id, ["cancelled", "failed"]);
  await page.getByRole("tab", { name: "终端" }).click();
  const historyTerminal = page
    .locator(".terminal-page > aside > button")
    .filter({ hasText: `${browserName}-compat-terminal` });
  await expect(historyTerminal).toBeVisible();
  await historyTerminal.click();
  await expect(page.getByText("只读历史", { exact: true })).toBeVisible();
  await expect(page.locator(".terminal-actions")).toHaveCount(0);
  await expect(page.locator(".terminal-page .xterm-rows")).toContainText(
    "terminal-compat-ready",
  );

  await page.getByRole("tab", { name: "设置" }).click();
  await expect(page.getByLabel("时间校准", { exact: true })).toBeVisible();
  const exitButton = page.getByRole("button", { name: "退出", exact: true });
  await exitButton.click();
  const shutdownDialog = page.getByRole("alertdialog");
  await expect(shutdownDialog).toContainText("退出 LocalFlow？");
  await expect(shutdownDialog.getByRole("button", { name: "取消" })).toBeFocused();
  await page.keyboard.press("Escape");
  await expect(shutdownDialog).toHaveCount(0);
  await expect(exitButton).toBeFocused();
  expect(eventResponses).toBeGreaterThan(0);
  expect(await page.evaluate(() => window.__localflowBootErrors || [])).toEqual(
    [],
  );
  const evidence = process.env.LOCALFLOW_COMPAT_EVIDENCE;
  if (evidence) {
    fs.mkdirSync(evidence, { recursive: true });
    await page.screenshot({
      path: path.join(evidence, `${testInfo.project.name}.png`),
      fullPage: true,
    });
    fs.writeFileSync(
      path.join(evidence, `${testInfo.project.name}.json`),
      JSON.stringify(
        {
          result: "passed",
          project: testInfo.project.name,
          browser_name: browserName,
          browser_version: browser.version(),
          operating_system: process.platform,
          base_url: process.env.LOCALFLOW_QA_URL,
          source_commit: process.env.GITHUB_SHA || null,
          console_errors: errors,
          failed_requests: failedRequests,
        },
        null,
        2,
      ),
    );
  }
  expect(failedRequests, failedRequests.join("\n")).toEqual([]);
  expect(errors, errors.join("\n")).toEqual([]);
});
