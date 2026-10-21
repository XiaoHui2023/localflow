"""Run complete qualification separately; managed delivery checks its freshness.

Use --qualify after changing inputs. The default mode requires managed-hook
challenge variables and never fabricates them. No browser build is performed by
the short delivery phase. A failed or interrupted qualification invalidates the
previous qualification immediately.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import time
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
QUALIFICATION = ROOT / ".qa/delivery-qualification.json"


def digest(value: object) -> str:
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()).hexdigest()


def input_hashes() -> dict[str, str]:
    files = subprocess.check_output(
        ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard"], cwd=ROOT
    ).decode().split("\0")
    return {
        relative: hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        for relative in sorted(set(files))
        if relative and not relative.startswith("quality/evidence/") and (ROOT / relative).is_file()
    }


def evidence_hashes() -> dict[str, str]:
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((ROOT / "quality/evidence").rglob("*"))
        if path.is_file() and "test-results" not in path.parts and path.suffix != ".log"
    }


def atomic_json(path: Path, value: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    temporary.replace(path)


def qualify(policy: dict) -> int:
    QUALIFICATION.unlink(missing_ok=True)
    original = input_hashes()
    commands = policy["qualification_commands_windows" if os.name == "nt" else "qualification_commands"]
    steps = []
    for index, argv in enumerate(commands):
        log = ROOT / f".qa/delivery-step-{index}.log"
        with log.open("wb") as output:
            result = subprocess.run(argv, cwd=ROOT, stdout=output, stderr=subprocess.STDOUT, timeout=1800)
        if result.returncode:
            print(f"qualification failed: {argv}; see {log}", file=sys.stderr)
            return result.returncode
        steps.append({"argv": argv, "exit_code": 0, "log_sha256": hashlib.sha256(log.read_bytes()).hexdigest()})
    if input_hashes() != original:
        raise ValueError("qualification inputs changed while checks ran")
    atomic_json(QUALIFICATION, {
        "schema_version": 1, "status": "qualified", "platform": sys.platform,
        "qualified_at": time.time(), "policy_sha256": digest(policy),
        "inputs": original, "evidence": evidence_hashes(), "steps": steps,
    })
    print("full qualification passed; managed delivery still requires a fresh challenge")
    return 0


def verify_qualification(policy: dict) -> None:
    record = json.loads(QUALIFICATION.read_text(encoding="utf-8"))
    commands = policy["qualification_commands_windows" if os.name == "nt" else "qualification_commands"]
    if record.get("status") != "qualified" or record.get("platform") != sys.platform:
        raise ValueError("qualification missing or belongs to another platform")
    age = time.time() - record["qualified_at"]
    if not 0 <= age <= 86400:
        raise ValueError("qualification expired")
    if record.get("policy_sha256") != digest(policy) or record.get("inputs") != input_hashes():
        raise ValueError("qualification source or policy is stale")
    if record.get("evidence") != evidence_hashes():
        raise ValueError("qualification evidence changed")
    steps = record.get("steps", [])
    if [step.get("argv") for step in steps] != commands:
        raise ValueError("qualification command scope mismatch")
    for index, step in enumerate(steps):
        log = ROOT / f".qa/delivery-step-{index}.log"
        if step.get("exit_code") != 0 or hashlib.sha256(log.read_bytes()).hexdigest() != step.get("log_sha256"):
            raise ValueError("qualification failed or log changed")


def registered_core(runtime: Path) -> Path:
    """Resolve both legacy direct registration and the verified bootstrap layer."""
    manifest_path = runtime / "bootstrap-manifest.json"
    if not manifest_path.is_file():
        return runtime
    raw = manifest_path.read_bytes()
    if not 0 < len(raw) <= 1024 * 1024:
        raise ValueError("bounded bootstrap manifest required")
    manifest = json.loads(raw)
    if not isinstance(manifest, dict) or not isinstance(manifest.get("files"), dict):
        raise ValueError("invalid registered bootstrap manifest")
    canonical = json.dumps(manifest, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True).encode()
    if hashlib.sha256(canonical).hexdigest() != runtime.name:
        raise ValueError("registered bootstrap identity drift")
    entry = runtime / "codex_gate_hook.py"
    if hashlib.sha256(entry.read_bytes()).hexdigest() != manifest["files"].get(entry.name):
        raise ValueError("registered bootstrap entry drift")
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location("_localflow_registered_bootstrap", entry)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    # Use the registered verifier and selector; never guess a source checkout,
    # latest release, or alternative core when the selected binding is invalid.
    registry = module.support(runtime)
    selection, _raw = registry["selection"](runtime.parents[1])
    core = Path(selection["active_root"])
    registry["verify"](core, selection["active_sha256"])
    return core


def deliver(policy: dict) -> int:
    command = policy["delivery_command_windows" if os.name == "nt" else "delivery_command"]
    challenge = os.environ.get("CODEX_GATE_CHALLENGE", "")
    if not challenge or os.environ.get("CODEX_GATE_POLICY_SHA256") != digest(policy) or os.environ.get("CODEX_GATE_COMMAND_SHA256") != digest(command):
        raise ValueError("missing or invalid managed challenge/policy/command binding")
    verify_qualification(policy)
    # Use the registered sealed runtime's own tree algorithm, not a copied or
    # historical implementation. Its launcher verifies the complete release.
    requirements = Path(os.environ.get("PROGRAMDATA", "C:/ProgramData")) / "OpenAI/Codex/requirements.toml"
    hooks = tomllib.loads(requirements.read_text(encoding="utf-8-sig"))["hooks"]
    runtime = registered_core(Path(
        hooks.get("windows_managed_dir") if os.name == "nt" else hooks.get("managed_dir")
    ))
    sys.dont_write_bytecode = True
    sys.path.insert(0, str(runtime))
    from gate_runtime.artifacts import artifact_hashes, artifact_tree
    from gate_runtime.runtime_release import verify
    verify(runtime)
    receipt = {
        "schema_version": 2, "status": "delivery-ready", "challenge": challenge,
        "validator_id": policy["validator_id"], "artifact_tree": artifact_tree(ROOT, policy),
        "artifact_hashes": artifact_hashes(ROOT, policy), "policy_sha256": digest(policy),
        "delivery_command_sha256": digest(command),
    }
    for key, required in (("claim_scope", "required_claim_scope"), ("goal_id", "required_goal_id")):
        if required in policy:
            receipt[key] = policy[required]
    atomic_json(ROOT / policy["ready_receipt"], receipt)
    print("delivery validated against full current qualification")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qualify", action="store_true")
    args = parser.parse_args()
    try:
        policy = json.loads((ROOT / ".codex/quality-gate.json").read_text(encoding="utf-8"))
        QUALIFICATION.parent.mkdir(parents=True, exist_ok=True)
        return qualify(policy) if args.qualify else deliver(policy)
    except (OSError, ValueError, KeyError, subprocess.SubprocessError) as error:
        print(f"delivery gate rejected: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
