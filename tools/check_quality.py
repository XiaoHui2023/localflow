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
            if receipt.get("result") != "passed":
                errors.append("browser receipt result is not passed")
            assertions = set(receipt.get("assertions", []))
            missing_assertions = BROWSER_ASSERTIONS - assertions
            if missing_assertions:
                errors.append(f"browser receipt missing assertions: {sorted(missing_assertions)}")
            for relative, expected in receipt.get("source_files", {}).items():
                source = root / relative
                if not source.is_file() or _source_sha256(source) != expected:
                    errors.append(f"browser receipt hash mismatch: {relative}")
            expected_sources = {
                "frontend/src/App.jsx",
                "frontend/src/main.jsx",
                "frontend/src/index.css",
                "frontend/src/extra.css",
                "frontend/src/case-picker.css",
                "frontend/e2e/localflow.spec.js",
                "frontend/playwright.config.js",
                "frontend/package-lock.json",
                "tools/run_browser_quality.py",
            }
            if set(receipt.get("source_files", {})) != expected_sources:
                errors.append("browser receipt source scope mismatch")
            screenshot_root = receipt_path.parent
            screenshots = receipt.get("screenshots", {})
            if len(screenshots) != 4:
                errors.append("browser receipt must bind four screenshots")
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
