from __future__ import annotations

import json
import re
from pathlib import Path


def test_operator_interaction_machine_contract() -> None:
    project = Path(__file__).resolve().parents[1]
    contract_path = project / "quality" / "operator-interaction-contract.json"
    contract = json.loads(contract_path.read_text(encoding="utf-8"))
    failures: list[str] = []
    for rule in contract["files"]:
        path = (contract_path.parent / rule["path"]).resolve()
        content = path.read_text(encoding="utf-8")
        for pattern in rule.get("required", []):
            if re.search(pattern, content, re.MULTILINE) is None:
                failures.append(f"{path}: missing /{pattern}/")
        for pattern in rule.get("forbidden", []):
            if re.search(pattern, content, re.MULTILINE) is not None:
                failures.append(f"{path}: forbidden /{pattern}/")
    assert not failures, "\n".join(failures)
