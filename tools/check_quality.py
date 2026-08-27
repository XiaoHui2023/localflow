from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path

FIELDS = {
    "metric",
    "requirement",
    "owner",
    "test",
    "oracle",
    "mutant",
    "evidence",
    "status",
    "claim_scope",
}
STATUSES = {"passed", "partial", "blocked"}
BROWSER_ASSERTIONS = {
    "secret-login-required",
    "secret-login-error",
    "login-control-disappears",
    "persistent-browser-session",
    "nav-order",
    "theme-memory",
    "run-context-memory",
    "inline-toggle-detail",
    "dedicated-terminal",
    "xterm-fit-search",
    "explorer-create-rename-delete",
    "config-use",
    "plugin-arbitrary-status",
    "removed-plugin-api-destinations",
    "wcag-a-aa",
    "mobile-no-overflow",
    "explorer-icon-only-state",
    "shared-fragment-semantic-icon",
    "neutral-config-filenames",
    "hidden-config-extensions",
    "opened-invalid-inline-diagnosis",
    "config-opens-in-use-mode",
    "nonblocking-expiring-status",
    "testing-ui-revision-auto-reload",
    "plugin-config-discovery",
    "run-fields-only",
    "plugin-case-field-mapping",
    "case-empty-default",
    "case-hover-wheel",
    "case-click-increment",
    "case-count-progressive-editor",
    "case-marquee-scope-only",
    "case-group-relative-edit",
    "case-group-fixed-edit",
    "case-scope-dismissal",
    "blank-seed",
    "verification-seed-task-detail",
    "required-run-field-gate",
    "uniform-control-geometry",
    "icon-only-run",
    "aligned-settings-rows",
    "idle-web-resource-budget",
    "compact-copyable-task-detail",
    "neutral-scroll-copy-feedback",
    "unboxed-stop-action",
    "case-intrinsic-compact-grid",
    "direct-config-file-actions",
    "terminal-responsive-fit",
    "terminal-fill-layout",
}
REQUIRED_SCREENSHOTS = {
    "anonymous-settings-login-light.png",
    "anonymous-settings-login-mobile.png",
    "admin-config-explorer-dark.png",
    "admin-empty-light.png",
    "admin-mobile-390.png",
    "admin-run-verification-dark.png",
    "admin-run-verification-empty-dark.png",
    "admin-run-verification-scope-dark.png",
    "admin-settings-compact-light.png",
    "admin-task-inline-dark.png",
    "admin-terminal-dark.png",
}


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _source_sha256(path: Path) -> str:
    """Hash text evidence with a Git-portable LF representation."""
    normalized = path.read_text(encoding="utf-8").replace("\r\n", "\n")
    return hashlib.sha256(normalized.encode()).hexdigest()


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    trace_path = (
        Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root / "quality" / "traceability.json"
    )
    receipt_path = (
        Path(sys.argv[2]).resolve()
        if len(sys.argv) > 2
        else root / "quality" / "evidence" / "browser" / "browser-receipt.json"
    )
    trace = json.loads(trace_path.read_text(encoding="utf-8"))
    requirements = set(
        re.findall(r"RQ-\d{3}", (root / "docs" / "requirements.md").read_text(encoding="utf-8"))
    )
    metrics = trace.get("metrics", [])
    errors: list[str] = []
    seen: set[str] = set()
    covered: set[str] = set()
    for index, item in enumerate(metrics):
        missing = FIELDS - item.keys()
        if missing:
            errors.append(f"metric[{index}] missing: {sorted(missing)}")
        metric = item.get("metric", "")
        if metric in seen:
            errors.append(f"duplicate metric: {metric}")
        seen.add(metric)
        covered.update(item.get("requirement", []))
        status = item.get("status")
        if status not in STATUSES:
            errors.append(f"metric[{index}] invalid status: {status}")
        for path_field in ("test", "evidence"):
            raw_path = item.get(path_field, "")
            path = root / raw_path
            if not raw_path or not path.exists():
                errors.append(f"metric[{index}] missing {path_field} path: {raw_path}")
        if status == "passed" and "no-" in item.get("claim_scope", ""):
            errors.append(f"metric[{index}] passed status exceeds claim scope")
    omitted = requirements - covered
    unknown = covered - requirements
    if omitted:
        errors.append(f"requirements without metric: {sorted(omitted)}")
    if unknown:
        errors.append(f"unknown requirements: {sorted(unknown)}")
    browser_passed = any(
        item.get("metric") == "QM-008" and item.get("status") == "passed" for item in metrics
    )
    if browser_passed:
        if not receipt_path.is_file():
            errors.append(f"missing browser receipt: {receipt_path}")
        else:
            receipt = json.loads(receipt_path.read_text(encoding="utf-8"))
            resource_contract = json.loads(
                (root / "quality" / "resource-budgets.json").read_text(encoding="utf-8")
            )
            if receipt.get("result") != "passed":
                errors.append("browser receipt result is not passed")
            assertions = set(receipt.get("assertions", []))
            missing_assertions = BROWSER_ASSERTIONS - assertions
            if missing_assertions:
                errors.append(f"browser receipt missing assertions: {sorted(missing_assertions)}")
            if receipt.get("resource_contract") != resource_contract:
                errors.append("browser receipt resource contract mismatch")
            resource_metrics = receipt.get("resource_metrics", {})
            for name, limit in resource_contract["limits"].items():
                value = resource_metrics.get(name)
                if not isinstance(value, (int, float)) or isinstance(value, bool):
                    errors.append(f"browser receipt missing resource metric: {name}")
                elif value > limit:
                    errors.append(f"browser resource budget exceeded: {name}={value} > {limit}")
            if resource_metrics.get("task_process_count") != 0:
                errors.append("browser resource sample included task processes")
            for relative, expected in receipt.get("source_files", {}).items():
                source = root / relative
                if not source.is_file() or _source_sha256(source) != expected:
                    errors.append(f"browser receipt hash mismatch: {relative}")
            expected_sources = {
                "frontend/index.html",
                "frontend/public/compat-boot.js",
                "frontend/public/theme-boot.js",
                "frontend/src/App.jsx",
                "frontend/src/api.js",
                "frontend/src/main.jsx",
                "frontend/src/index.css",
                "frontend/src/extra.css",
                "frontend/src/round6.css",
                "frontend/src/case-picker.css",
                "frontend/e2e/localflow.spec.js",
                "frontend/e2e/compatibility.spec.js",
                "frontend/e2e/legacy-browser.mjs",
                "frontend/playwright.config.js",
                "frontend/vite.config.js",
                "frontend/package-lock.json",
                "quality/resource-budgets.json",
                "tools/check_quality.py",
                "tools/run_browser_quality.py",
                "tools/run_linux_browser_quality.py",
            }
            if set(receipt.get("source_files", {})) != expected_sources:
                errors.append("browser receipt source scope mismatch")
            screenshot_root = receipt_path.parent
            screenshots = receipt.get("screenshots", {})
            if set(screenshots) != REQUIRED_SCREENSHOTS:
                errors.append("browser receipt screenshot scope mismatch")
            for name, expected in screenshots.items():
                screenshot = screenshot_root / name
                if not screenshot.is_file() or _sha256(screenshot) != expected:
                    errors.append(f"browser screenshot hash mismatch: {name}")
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"quality trace valid: {len(metrics)} metrics, {len(requirements)} requirements")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
