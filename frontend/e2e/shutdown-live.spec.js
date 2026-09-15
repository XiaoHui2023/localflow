import fs from "node:fs";
import path from "node:path";

import { expect, test } from "@playwright/test";

const root = process.env.LOCALFLOW_QA_ROOT;

test("accepted shutdown exits while the real browser page remains open", async ({ page }) => {
  if (!root) throw new Error("LOCALFLOW_QA_ROOT is required");
  const adminKey = fs
    .readFileSync(path.join(root, "secrets", "web-admin-key"), "utf8")
    .trim();
  const afterAcceptance = [];
  let acceptedAt = 0;
  page.on("request", (request) => {
    if (acceptedAt) afterAcceptance.push(request.url());
  });

  await page.goto("/");
  await page.getByRole("tab", { name: "设置" }).click();
  await page.getByLabel("管理员秘钥").fill(adminKey);
  await page.getByRole("button", { name: "登录", exact: true }).click();
  await expect(page.getByRole("button", { name: "退出", exact: true })).toBeVisible();

  await page.getByRole("button", { name: "退出", exact: true }).click();
  const response = page.waitForResponse(
    (candidate) =>
      candidate.url().endsWith("/api/v1/system/shutdown") &&
      candidate.status() === 202,
  );
  await page
    .getByRole("alertdialog")
    .getByRole("button", { name: "退出", exact: true })
    .click();
  await response;
  acceptedAt = Date.now();

  // Keep the document and browser context alive beyond EventSource's normal
  // reconnect delay. A page refresh or browser close would hide the defect.
  await page.waitForTimeout(500);
  afterAcceptance.length = 0;
  await page.waitForTimeout(6_000);
  expect(page.isClosed()).toBe(false);
  expect(afterAcceptance, "the stopped page must not poll or reconnect").toEqual([]);
});
