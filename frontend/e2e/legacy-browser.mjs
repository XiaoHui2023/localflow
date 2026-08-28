import fs from "node:fs";
import path from "node:path";
import { Builder, By, logging, until } from "selenium-webdriver";

const browserName = process.env.LOCALFLOW_LEGACY_BROWSER;
const projectName = process.env.LOCALFLOW_LEGACY_PROJECT;
const server = process.env.LOCALFLOW_SELENIUM_URL || "http://127.0.0.1:4444/wd/hub";
const baseUrl = process.env.LOCALFLOW_QA_URL;
const adminKey = process.env.LOCALFLOW_QA_ADMIN_KEY;
if (!browserName || !projectName || !baseUrl || !adminKey) throw new Error("legacy browser QA environment is incomplete");

const capabilities = { browserName, "goog:loggingPrefs": { browser: "ALL" } };
const driver = await new Builder().usingServer(server).withCapabilities(capabilities).build();
let step = "open root";
async function diagnostics() {
  let bootErrors = [];
  let consoleErrors = [];
  let consoleLogSupported = true;
  try { bootErrors = await driver.executeScript("return window.__localflowBootErrors || []"); } catch { /* page may be unavailable */ }
  try {
    const entries = await driver.manage().logs().get(logging.Type.BROWSER);
    consoleErrors = entries.filter((entry) => entry.level.value >= logging.Level.SEVERE.value).map((entry) => entry.message);
  } catch (error) {
    if (/not implemented|unsupported|unknown command|HTTP method not allowed/i.test(String(error))) consoleLogSupported = false;
    else consoleErrors.push(String(error));
  }
  return { bootErrors, consoleErrors, consoleLogSupported };
}
try {
  await driver.get(baseUrl);
  await driver.wait(async () => (await driver.findElements(By.css("#root > *"))).length > 0, 30_000);
  step = "open settings";
  await driver.findElement(By.xpath("//*[@role='tab' and normalize-space()='设置']")).click();
  step = "authenticate";
  const keyInput = await driver.wait(until.elementLocated(By.css("input[aria-label='管理员秘钥']")), 10_000);
  await keyInput.sendKeys(adminKey);
  await driver.findElement(By.xpath("//button[normalize-space()='登录']")).click();
  await driver.wait(async () => (await driver.findElements(By.css("[role='tab']"))).length === 4, 10_000);
  step = "open configuration";
  await driver.findElement(By.xpath("//*[@role='tab' and normalize-space()='运行']")).click();
  const config = await driver.wait(until.elementLocated(By.css("[data-file='config/command/hello-world.yaml']")), 20_000);
  await config.click();
  await driver.findElement(By.xpath("//button[normalize-space()='编辑']")).click();
  await driver.wait(until.elementLocated(By.css(".monaco-editor")), 30_000);
  step = "collect diagnostics";
  const { bootErrors, consoleErrors, consoleLogSupported } = await diagnostics();
  if (bootErrors.length || consoleErrors.length) throw new Error([...bootErrors, ...consoleErrors].join("\n"));
  const evidence = process.env.LOCALFLOW_COMPAT_EVIDENCE;
  const caps = await driver.getCapabilities();
  if (evidence) {
    fs.mkdirSync(evidence, { recursive: true });
    fs.writeFileSync(path.join(evidence, `${projectName}.png`), await driver.takeScreenshot(), "base64");
    fs.writeFileSync(path.join(evidence, `${projectName}.json`), JSON.stringify({
      result: "passed",
      project: projectName,
      browser_name: browserName,
      browser_version: caps.get("browserVersion") || caps.get("version"),
      operating_system: "ubuntu-container",
      base_url: baseUrl,
      source_commit: process.env.GITHUB_SHA || null,
      boot_errors: bootErrors,
      console_errors: consoleErrors,
      console_log_supported: consoleLogSupported,
    }, null, 2));
  }
} catch (error) {
  const observed = await diagnostics();
  throw new Error(`legacy browser failed at ${step}: ${error}\n${JSON.stringify(observed, null, 2)}`);
} finally {
  await driver.quit();
}
