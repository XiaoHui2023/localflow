from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
import time
from pathlib import Path

import pytest


@pytest.fixture
def gate(tmp_path, monkeypatch):
    path = Path(__file__).resolve().parents[1] / "tools/run_delivery_gate.py"
    spec = importlib.util.spec_from_file_location("localflow_delivery_gate", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    monkeypatch.setattr(module, "QUALIFICATION", tmp_path / ".qa/qualification.json")
    inputs = {"src/app.py": "source-before"}
    evidence = {"quality/evidence/browser.json": "evidence-before"}
    monkeypatch.setattr(module, "input_hashes", lambda: inputs.copy())
    monkeypatch.setattr(module, "evidence_hashes", lambda: evidence.copy())
    key = "qualification_commands_windows" if sys.platform == "win32" else "qualification_commands"
    policy = {key: [[sys.executable, "-c", "print('actual-check')"]]}
    module.QUALIFICATION.parent.mkdir()
    return module, policy, inputs, evidence


def test_actual_qualification_then_source_and_evidence_changes(gate):
    module, policy, inputs, evidence = gate
    assert module.qualify(policy) == 0
    module.verify_qualification(policy)
    inputs["src/app.py"] = "source-after"
    with pytest.raises(ValueError, match="source or policy is stale"):
        module.verify_qualification(policy)
    inputs["src/app.py"] = "source-before"
    evidence["quality/evidence/browser.json"] = "evidence-after"
    with pytest.raises(ValueError, match="evidence changed"):
        module.verify_qualification(policy)


def test_failed_requalification_invalidates_previous_success(gate):
    module, policy, _, _ = gate
    assert module.qualify(policy) == 0
    key = next(iter(policy))
    policy[key] = [[sys.executable, "-c", "raise SystemExit(7)"]]
    assert module.qualify(policy) == 7
    assert not module.QUALIFICATION.exists()


@pytest.mark.parametrize("change", ["expired", "future", "command", "log"])
def test_changed_or_expired_qualification_rejected(gate, change):
    module, policy, _, _ = gate
    assert module.qualify(policy) == 0
    record = json.loads(module.QUALIFICATION.read_text())
    if change == "expired":
        record["qualified_at"] = time.time() - 86401
    elif change == "future":
        record["qualified_at"] = time.time() + 60
    elif change == "command":
        record["steps"][0]["argv"] = ["skipped"]
    else:
        (module.ROOT / ".qa/delivery-step-0.log").write_text("changed")
    module.atomic_json(module.QUALIFICATION, record)
    with pytest.raises(ValueError):
        module.verify_qualification(policy)


def test_missing_challenge_rejected_before_evidence(gate, monkeypatch):
    module, policy, _, _ = gate
    monkeypatch.delenv("CODEX_GATE_CHALLENGE", raising=False)
    key = "delivery_command_windows" if sys.platform == "win32" else "delivery_command"
    policy[key] = [sys.executable, "tools/run_delivery_gate.py"]
    with pytest.raises(ValueError, match="managed challenge"):
        module.deliver(policy)


def bootstrap_fixture(tmp_path: Path, *, selected_hash: str = "selected-core") -> Path:
    entry = """from pathlib import Path
import json
def support(root):
    def selection(managed):
        return json.loads((managed/'control/bootstrap-selection.json').read_text()), b''
    def verify(core, expected):
        if core.name != expected:
            raise ValueError('selected core identity mismatch')
    return {'selection': selection, 'verify': verify}
"""
    manifest = {"files": {"codex_gate_hook.py": hashlib.sha256(entry.encode()).hexdigest()}}
    raw = json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()
    directory = tmp_path / "bootstrap-releases" / hashlib.sha256(raw).hexdigest()
    directory.mkdir(parents=True)
    (directory / "bootstrap-manifest.json").write_bytes(raw)
    (directory / "codex_gate_hook.py").write_bytes(entry.encode())
    control = tmp_path / "control"
    control.mkdir()
    (control / "bootstrap-selection.json").write_text(json.dumps({
        "active_root": str(tmp_path / "selected-core"), "active_sha256": selected_hash,
    }))
    return directory


def test_registered_core_preserves_legacy_binding(gate, tmp_path):
    module, _, _, _ = gate
    assert module.registered_core(tmp_path / "legacy-core") == tmp_path / "legacy-core"


def test_registered_bootstrap_uses_its_selected_verified_core(gate, tmp_path):
    module, _, _, _ = gate
    assert module.registered_core(bootstrap_fixture(tmp_path)) == tmp_path / "selected-core"


@pytest.mark.parametrize("fault", ["manifest", "entry", "selection"])
def test_bootstrap_drift_never_falls_back_to_another_core(gate, tmp_path, fault):
    module, _, _, _ = gate
    directory = bootstrap_fixture(tmp_path, selected_hash="wrong" if fault == "selection" else "selected-core")
    if fault == "manifest":
        (directory / "bootstrap-manifest.json").write_text('{"files":{}}')
    elif fault == "entry":
        (directory / "codex_gate_hook.py").write_text("raise AssertionError('must never execute')")
    with pytest.raises(ValueError, match="identity|entry drift"):
        module.registered_core(directory)
