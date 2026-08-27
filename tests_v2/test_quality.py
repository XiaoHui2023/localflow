import fnmatch
import json
import subprocess
import sys
import tomllib
from pathlib import Path


def test_every_starter_resource_is_covered_by_package_data() -> None:
    root = Path(__file__).parents[1]
    starter = root / "src" / "localflow" / "starter_root"
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))
    patterns = project["tool"]["setuptools"]["package-data"][
        "localflow.starter_root"
    ]
    uncovered = []
    for resource in starter.rglob("*"):
        if (
            not resource.is_file()
            or resource == starter / "__init__.py"
            or "__pycache__" in resource.parts
        ):
            continue
        relative = resource.relative_to(starter).as_posix()
        if not any(fnmatch.fnmatchcase(relative, pattern) for pattern in patterns):
            uncovered.append(relative)
    assert uncovered == []


def test_release_workflow_tracks_the_current_starter_examples() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    for required in (
        "random-number.yaml",
        "verification-demo.yaml",
        "marker-warning.yaml",
        "interactive-shutdown.yaml",
        "random_number.py",
        "simulate.py",
        "marker_result.py",
        "interactive_shutdown.py",
    ):
        assert required in workflow
    assert "heartbeat.yaml" not in workflow
    assert "heartbeat.py" not in workflow
    assert "heartbeat.yaml" not in (root / "docs" / "configuration.md").read_text(
        encoding="utf-8"
    )


def test_release_keeps_staticx_inside_the_compatibility_baseline() -> None:
    root = Path(__file__).parents[1]
    workflow = (root / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    builder = (root / "tools" / "ci_pack_ubuntu16.sh").read_text(
        encoding="utf-8"
    )
    packer = (root / "tools" / "pack.sh").read_text(encoding="utf-8")
    compatibility = (root / "tools" / "check_linux_compatibility.sh").read_text(
        encoding="utf-8"
    )
    assert "PACK_DEFER_STATICX" not in workflow + builder + packer
    assert "PACK_STATICX_SOURCE_BUILD=1" in builder
    assert "--no-binary=staticx" in packer
    assert "mv dist/localflow dist/localflow.pyinstaller" in packer
    assert "finalize_release.sh dist/localflow.pyinstaller" in packer
    assert "tools/check_linux_compatibility.sh dist/localflow" in workflow
    for cpu in ("qemu64", "core2duo", "Opteron_G1"):
        assert cpu in compatibility


def test_release_bundle_preserves_secure_runtime_directory_modes() -> None:
    root = Path(__file__).parents[1]
    packer = (root / "tools" / "finalize_release.sh").read_text(encoding="utf-8")
    assert 'install -d -m 0700 "dist/$BUNDLE/secrets"' in packer
    assert 'install -d -m 0750 "dist/$BUNDLE"' in packer
    assert 'install -d -m 0750 "dist/$BUNDLE/deploy"' in packer
    assert '"dist/$BUNDLE/config"' in packer
    assert '"dist/$BUNDLE/runtime"' in packer
    assert '"dist/$BUNDLE/runtime/instances"' in packer
    assert 'mkdir -p "dist/$BUNDLE/deploy"' not in packer

    workflow = (root / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    assert 'stat -c \'%a\' "$bundle/config"' in workflow
    assert 'stat -c \'%a\' "$bundle/runtime"' in workflow
    assert 'stat -c \'%a\' "$bundle/runtime/instances"' in workflow


def test_operator_documentation_has_one_current_contract() -> None:
    root = Path(__file__).parents[1]
    assert not (root / "docs" / "configuration-plugin-contract.md").exists()
    readme = (root / "README.md").read_text(encoding="utf-8")
    architecture = (root / "docs" / "architecture.md").read_text(encoding="utf-8")
    security = (root / "docs" / "security.md").read_text(encoding="utf-8")
    assert "网页“配置”页" not in readme
    assert "普通打开地址、同机其他用户和远端只读访问者都不会" not in architecture
    assert "直接来自回环地址的网页" in architecture
    assert "直接访问回环地址的网页" in security


def test_agent_skills_are_release_safe_and_packaged() -> None:
    root = Path(__file__).parents[1]
    expected = {
        "localflow-project",
        "localflow-api",
        "localflow-configuration",
        "localflow-plugin-development",
        "localflow-operations",
    }
    for name in expected:
        source = root / "skills" / name / "SKILL.md"
        text = source.read_text(encoding="utf-8")
        assert text.startswith("---\nname: ")
        assert f"name: {name}\n" in text
        assert "C:\\Users\\" not in text
        assert "F:\\" not in text
        assert "127.0.0.1:29049" not in text
    packer = (root / "tools" / "finalize_release.sh").read_text(encoding="utf-8")
    workflow = (root / ".github" / "workflows" / "release.yml").read_text(
        encoding="utf-8"
    )
    assert 'cp -R skills/. "dist/$BUNDLE/skills/"' in packer
    for name in expected:
        assert f"skills/{name}/SKILL.md" in workflow


def test_repository_verification_plugin_keeps_runtime_seed_contract() -> None:
    root = Path(__file__).parents[1]
    source = (root / "plugins" / "verification.py").read_text(encoding="utf-8")
    packaged_source = (
        root / "src" / "localflow" / "builtin_plugins" / "verification.py.example"
    ).read_text(encoding="utf-8")
    assert source == packaged_source
    assert "import secrets" not in source
    assert 'seed = "${seed}" if automatic_seed' in source
    assert '"_runtime_seed": "unix"' in source
    assert "name=case_name" in source
    assert 'else {"seed": seed}' in source


def test_quality_trace_and_mutant(tmp_path: Path) -> None:
    root = Path(__file__).resolve().parents[1]
    assert (
        subprocess.run(
            [sys.executable, str(root / "tools" / "check_quality.py")], cwd=root
        ).returncode
        == 0
    )
    data = json.loads((root / "quality" / "traceability.json").read_text(encoding="utf-8"))
    data["metrics"] = [item for item in data["metrics"] if item["metric"] != "QM-016"]
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
    assert "RQ-115" in rejected.stderr

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

    receipt = json.loads(
        (root / "quality" / "evidence" / "browser" / "browser-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    receipt["assertions"].remove("verification-seed-task-detail")
    missing_interaction_assertion = tmp_path / "missing-seed-detail-assertion.json"
    missing_interaction_assertion.write_text(json.dumps(receipt), encoding="utf-8")
    escaped_oracle = subprocess.run(
        [
            sys.executable,
            str(root / "tools" / "check_quality.py"),
            str(root / "quality" / "traceability.json"),
            str(missing_interaction_assertion),
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert escaped_oracle.returncode == 1
    assert "browser receipt missing assertions" in escaped_oracle.stderr
    assert "verification-seed-task-detail" in escaped_oracle.stderr

    receipt = json.loads(
        (root / "quality" / "evidence" / "browser" / "browser-receipt.json").read_text(
            encoding="utf-8"
        )
    )
    receipt["resource_metrics"]["renderer_js_heap_mib"] = (
        receipt["resource_contract"]["limits"]["renderer_js_heap_mib"] + 1
    )
    over_budget_receipt = tmp_path / "over-budget-receipt.json"
    over_budget_receipt.write_text(json.dumps(receipt), encoding="utf-8")
    over_budget = subprocess.run(
        [
            sys.executable,
            str(root / "tools" / "check_quality.py"),
            str(root / "quality" / "traceability.json"),
            str(over_budget_receipt),
        ],
        cwd=root,
        capture_output=True,
        text=True,
    )
    assert over_budget.returncode == 1
    assert "browser resource budget exceeded" in over_budget.stderr
