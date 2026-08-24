import json
import subprocess
import sys
from pathlib import Path


def test_quality_trace_and_mutant(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    assert (
        subprocess.run(
            [sys.executable, str(root / "tools" / "check_quality.py")], cwd=root
        ).returncode
        == 0
    )
    data = json.loads((root / "quality" / "traceability.json").read_text(encoding="utf-8"))
    data["metrics"].pop()
    mutant = tmp_path / "trace.json"
    mutant.write_text(json.dumps(data), encoding="utf-8")
    rejected = subprocess.run(
        [sys.executable, str(root / "tools" / "check_quality.py"), str(mutant)],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert rejected.returncode == 1
    assert "requirements without metric" in rejected.stderr

    receipt = json.loads(
        (root / "quality" / "evidence" / "browser" / "browser-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    receipt["source_files"]["frontend/src/App.jsx"] = "0" * 64
    bad_receipt = tmp_path / "browser-receipt.json"
    bad_receipt.write_text(json.dumps(receipt), encoding="utf-8")
    tampered = subprocess.run(
        [
            sys.executable,
            str(root / "tools" / "check_quality.py"),
            str(root / "quality" / "traceability.json"),
            str(bad_receipt),
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert tampered.returncode == 1
    assert "browser receipt hash mismatch" in tampered.stderr
