"""A declared resolution must bind real owners, runners and issue evidence."""
import importlib.util
import json
from pathlib import Path

import pytest


def validator():
    source = Path(__file__).parents[1] / "tools/check_feedback_gate.py"
    spec = importlib.util.spec_from_file_location("feedback_gate", source)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.validate_register


@pytest.mark.parametrize("mutation", [None, "owner", "runner", "evidence", "fragment", "unresolved"])
def test_gate_rejects_unbound_resolution_receipts(tmp_path: Path, mutation) -> None:
    (tmp_path / "owner.py").write_text("owner = True")
    (tmp_path / "test_owner.py").write_text("def test_owner(): pass")
    (tmp_path / "receipt.json").write_text(json.dumps({"issues": {"ISSUE": {"result": "passed"}}}))
    issue = {
        "id": "ISSUE", "status": "resolved", "summary": "failure", "expected": "success",
        "actual": "failure", "owner_paths": ["owner.py"], "runner_paths": ["test_owner.py"],
        "entrypoint": {"command": ["pytest", "test_owner.py"]}, "oracle": {"command": ["pytest", "test_owner.py"]},
        "reproduction_attempts": [{"result": "reproduced", "evidence": "baseline"}],
        "resolution_evidence": "receipt.json#ISSUE",
    }
    if mutation == "owner":
        issue["owner_paths"] = ["missing.py"]
    elif mutation == "runner":
        issue["runner_paths"] = ["tools/feedback-reproduction.mjs"]
    elif mutation == "evidence":
        issue["resolution_evidence"] = "absent.json#ISSUE"
    elif mutation == "fragment":
        issue["resolution_evidence"] = "receipt.json#OTHER"
    elif mutation == "unresolved":
        issue["status"] = "reproduced"
    errors = validator()(tmp_path, {"issues": [issue]})
    assert bool(errors) == (mutation is not None)
