import { expect } from "@playwright/test";

async function surfaceReport(surface, inset) {
  return surface.evaluate((node, safeInset) => {
    const rect = node.getBoundingClientRect();
    const points = [
      [rect.left + Math.min(safeInset, rect.width / 2), rect.top + Math.min(safeInset, rect.height / 2)],
      [rect.right - Math.min(safeInset, rect.width / 2), rect.top + Math.min(safeInset, rect.height / 2)],
      [rect.left + rect.width / 2, rect.top + rect.height / 2],
      [rect.left + Math.min(safeInset, rect.width / 2), rect.bottom - Math.min(safeInset, rect.height / 2)],
      [rect.right - Math.min(safeInset, rect.width / 2), rect.bottom - Math.min(safeInset, rect.height / 2)],
    ];
    const paintedOnTop = points.every(([x, y]) => {
      const top = document.elementsFromPoint(x, y)[0];
      return top === node || node.contains(top);
    });
    const clippingAncestors = [];
    for (let current = node.parentElement; current && current !== document.body; current = current.parentElement) {
      const style = getComputedStyle(current);
      if ([style.overflow, style.overflowX, style.overflowY].some((value) => ["hidden", "clip", "scroll", "auto"].includes(value))) clippingAncestors.push(current.tagName.toLowerCase());
    }
    return {
      rect: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom, width: rect.width, height: rect.height },
      viewport: { width: innerWidth, height: innerHeight },
      paintedOnTop,
      clippingAncestors,
      focusableChildren: node.querySelectorAll("a[href],button,input,select,textarea,[tabindex]:not([tabindex='-1'])").length,
      role: node.getAttribute("role"),
      zIndex: getComputedStyle(node).zIndex,
    };
  }, inset);
}

export async function assertFloatingSurface(surface, { inset = 3, viewportPadding = 4 } = {}) {
  await expect(surface).toBeVisible();
  const report = await surfaceReport(surface, inset);
  expect(report.role).toBe("tooltip");
  expect(report.rect.width).toBeGreaterThan(0);
  expect(report.rect.height).toBeGreaterThan(0);
  expect(report.rect.left).toBeGreaterThanOrEqual(viewportPadding);
  expect(report.rect.top).toBeGreaterThanOrEqual(viewportPadding);
  expect(report.rect.right).toBeLessThanOrEqual(report.viewport.width - viewportPadding);
  expect(report.rect.bottom).toBeLessThanOrEqual(report.viewport.height - viewportPadding);
  expect(report.clippingAncestors).toEqual([]);
  expect(report.focusableChildren).toBe(0);
  expect(Number(report.zIndex)).toBeGreaterThan(0);
  expect(report.paintedOnTop).toBeTruthy();
  return report;
}

export async function assertTooltipInteraction(page, trigger, expectedText) {
  await trigger.hover();
  const before = await trigger.boundingBox();
  const pageWidthBefore = await page.evaluate(() => document.documentElement.scrollWidth);
  let surface = page.getByRole("tooltip").filter({ hasText: expectedText });
  const report = await assertFloatingSurface(surface);

  await page.evaluate((rect) => {
    const obstacle = document.createElement("div");
    obstacle.dataset.tooltipObstacle = "true";
    obstacle.style.cssText = `position:fixed;left:${rect.left}px;top:${rect.top}px;width:${rect.width}px;height:${rect.height}px;z-index:40;background:#f00;pointer-events:auto`;
    document.body.appendChild(obstacle);
  }, report.rect);
  expect((await surfaceReport(surface, 3)).paintedOnTop).toBeTruthy();
  await page.locator("[data-tooltip-obstacle]").evaluate((node) => node.remove());

  await page.keyboard.press("Escape");
  await expect(surface).toHaveCount(0);
  await trigger.evaluate((node) => node.focus({ preventScroll: true }));
  surface = page.getByRole("tooltip").filter({ hasText: expectedText });
  await assertFloatingSurface(surface);
  const describedBy = await trigger.getAttribute("aria-describedby");
  expect(describedBy).toBeTruthy();
  expect(await surface.getAttribute("id")).toBe(describedBy);
  expect(await trigger.boundingBox()).toEqual(before);
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBe(pageWidthBefore);
  await page.keyboard.press("Escape");
  await expect(surface).toHaveCount(0);
}
