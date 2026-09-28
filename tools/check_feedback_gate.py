"""Fail-closed gate for registered user-feedback reproductions.

The feedback register is deliberately separate from the product tests: a green
test suite cannot silently erase an operator-reported failure or turn a blocked
environment into a release claim.  Release callers must run this checker after
the relevant tests and before packaging.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

READY = "resolved"


def validate_register(root: Path, register: dict) -> list[str]:
    issues = register.get("issues")
    if not isinstance(issues, list) or not issues:
        return ["feedback gate: register must contain a non-empty issues list"]
    errors: list[str] = []
    seen: set[str] = set()
    for index, issue in enumerate(issues):
        if not isinstance(issue, dict):
            errors.append(f"issue[{index}] is not an object")
            continue
        issue_id = issue.get("id")
        if not isinstance(issue_id, str) or not issue_id:
            errors.append(f"issue[{index}] has no id")
            continue
        if issue_id in seen:
            errors.append(f"duplicate issue id: {issue_id}")
        seen.add(issue_id)
        for field in ("summary", "expected", "actual", "owner_paths", "entrypoint", "oracle"):
            if field not in issue:
                errors.append(f"{issue_id}: missing {field}")
        status = issue.get("status")
        if status != READY:
            errors.append(f"{issue_id}: status={status!r}; release requires {READY!r}")
        attempts = issue.get("reproduction_attempts")
        if not isinstance(attempts, list) or not attempts:
            errors.append(f"{issue_id}: no reproduction attempt receipt")
        elif not any(
            isinstance(attempt, dict)
            and attempt.get("result") == "reproduced"
            and attempt.get("evidence")
            for attempt in attempts
        ):
            errors.append(f"{issue_id}: no direct reproduced witness")
        if status == READY and not issue.get("resolution_evidence"):
            errors.append(f"{issue_id}: resolved without resolution_evidence")
        for field in ("owner_paths", "runner_paths"):
            paths = issue.get(field)
            if not isinstance(paths, list) or not paths:
                errors.append(f"{issue_id}: no {field}")
                continue
            for relative in paths:
                path = (root / relative).resolve()
                if not path.is_relative_to(root.resolve()) or not path.is_file():
                    errors.append(f"{issue_id}: unavailable {field} file: {relative}")
        if status == READY and issue.get("resolution_evidence"):
            relative, _, fragment = issue["resolution_evidence"].partition("#")
            path = (root / relative).resolve()
            try:
                if not path.is_relative_to(root.resolve()):
                    raise ValueError("evidence is outside repository")
                evidence = json.loads(path.read_text(encoding="utf-8"))
                if fragment and fragment not in evidence.get("issues", {}):
                    raise ValueError(f"missing issue fragment {fragment}")
            except (OSError, ValueError, TypeError) as exc:
                errors.append(f"{issue_id}: resolution evidence unavailable: {exc}")
    return errors


def main() -> int:
    root = Path(__file__).resolve().parents[1]
    try:
        register = json.loads((root / "quality" / "feedback-issues.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        print(f"feedback gate: cannot read register: {exc}", file=sys.stderr)
        return 2
    errors = validate_register(root, register)
    if errors:
        print("\n".join(errors), file=sys.stderr)
        return 1
    print(f"feedback gate passed: {len(register['issues'])} issues have reproduced and resolved receipts")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
