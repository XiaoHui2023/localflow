import shlex
from pathlib import Path
from types import SimpleNamespace

import pytest

from localflow.models import detected_login_shell
from localflow.plugins import PluginRegistry, run_field
from localflow.settings import initialize_root


def test_plugin_generation_keeps_diagnostic_boundary(root: Path) -> None:
    directory = root / "plugins"
    directory.mkdir(parents=True)
    good = directory / "good.py"
    good.write_text(
        "from localflow.plugins import plugin\n@plugin('demo')\nclass Demo:\n fields=[]\n def expand(self, values, context): return []\n",
        encoding="utf-8",
    )
    registry = PluginRegistry(directory)
    registry.load()
    assert registry.describe()[0]["name"] == "demo"
    (directory / "broken.py").write_text("raise RuntimeError('boom')\n", encoding="utf-8")
    registry.load()
    assert registry.describe()[0]["name"] == "demo"
    assert "RuntimeError: boom" in next(iter(registry.diagnostics.values()))


@pytest.mark.asyncio
async def test_plugin_discovery_is_dynamic_and_typed(root: Path) -> None:
    directory = root / "plugins"
    directory.mkdir(parents=True)
    plugin_file = directory / "discover.py"
    plugin_file.write_text(
        "from localflow.plugins import plugin\n"
        "@plugin('cases')\n"
        "class Cases:\n"
        " fields=[]\n"
        " def discover(self, values): return [values['prefix'] + '-a', values['prefix'] + '-b']\n"
        " def expand(self, values, context): return []\n",
        encoding="utf-8",
    )
    registry = PluginRegistry(directory)
    registry.load()
    assert await registry.discover("cases", {"prefix": "smoke"}) == [
        "smoke-a",
        "smoke-b",
    ]


@pytest.mark.asyncio
async def test_verification_config_discovers_one_level_files_and_directories(root: Path) -> None:
    initialize_root(root)
    nested = root / "cases" / "case-a" / "hidden-below.case"
    nested.parent.mkdir(parents=True)
    (root / "cases" / "case-b").mkdir()
    (root / "cases" / "smoke.case").write_text("smoke", encoding="utf-8")
    nested.write_text("nested", encoding="utf-8")
    registry = PluginRegistry(root / "plugins")
    registry.load()
    verification = next(item for item in registry.describe() if item["name"] == "verification")
    assert verification["api"]["endpoint"] == "/api/v1/runs"
    assert verification["api"]["configuration_schema"] is not None
    schema = verification["api"]["configuration_schema"]
    assert {"plugin", "command", "case_directory", "case_names"}.issubset(schema["properties"])
    assert {"plugin", "working_directory", "command"}.issubset(schema["required"])
    assert "compile_logs" not in schema["required"]
    assert "run_logs" not in schema["required"]
    assert schema["additionalProperties"] is True
    assert {
        "variables",
        "source",
        "labels",
        "mutex_keys",
        "compile_logs",
        "run_logs",
        "custom_texts",
    }.issubset(schema["properties"])
    input_schema = verification["api"]["input_schema"]
    assert {"cases", "runs", "case_runs", "seed"}.issubset(input_schema["properties"])
    assert input_schema["additionalProperties"] is False
    assert verification["api"]["example"]["configuration"]["plugin"] == "verification"
    assert verification["api"]["example"]["inputs"] == {
        "cases": ["case-a"],
        "case_runs": {"case-a": 1},
        "seed": None,
    }
    assert verification["statuses"]["error"]["label"] == "ERROR"
    assert "count" not in verification["statuses"]["error"]
    assert verification["api"]["input_fields"] == verification["fields"]
    case_field = verification["fields"][0]
    assert case_field["count_field"] == "case_runs"
    assert case_field["default_count_field"] == "runs"
    document = {
        "plugin": "verification",
        "case_directory": "${cases_dir}",
        "working_directory": ".",
        "command": [
            "python3",
            "-u",
            "${scripts_dir}/simulate.py",
            "--case",
            "${case}",
            "--seed",
            "${seed}",
        ],
        "labels": ["nightly"],
        "custom_texts": ["Case: ${case}", "Seed: ${seed}"],
        "variables": {"cases_dir": "cases", "scripts_dir": "scripts"},
    }
    items = await registry.discover_config(document, {}, {"root": str(root)})
    assert items == ["case-a", "case-b", "smoke"]
    generated = {
        "plugin": "verification",
        "case_names": ["generated-b", "generated-a", "generated-a"],
        "working_directory": ".",
        "command": "true",
    }
    assert await registry.discover_config(generated, {}, {"root": str(root)}) == [
        "generated-a",
        "generated-b",
    ]
    with pytest.raises(ValueError, match="alternative sources"):
        registry.expand_config(
            {**generated, "case_directory": "cases"},
            {"cases": ["generated-a"]},
            {"root": str(root)},
        )
    with pytest.raises(ValueError, match="at least one case"):
        registry.expand_config(document, {}, {"root": str(root)})
    task = registry.expand_config(
        document,
        {"cases": ["case-a"], "seed": ""},
        {"root": str(root)},
    )[0]
    assert task.name == "case-a"
    assert task.custom["_case"] == "case-a"
    assert task.custom["自定义文本"] == ["Case: case-a", "Seed: ${seed}"]
    assert "seed" not in task.custom
    assert task.deferred_values["seed"].source == "monotonic_unix"
    assert task.command.count("--case") == task.command.count("--seed") == 1
    assert task.command[task.command.index("--case") + 1] == "case-a"
    assert task.command[task.command.index("--seed") + 1] == "${seed}"
    assert any(key.startswith("verification:") for key in task.mutex_keys)

    make_task = registry.expand_config(
        {
            "plugin": "verification",
            "case_names": ["case-a"],
            "working_directory": str(root),
            "command": "make all CASE=${case} SEED=${seed}",
            "custom_texts": ["case=${case}", "seed=${seed}"],
        },
        {"cases": ["case-a"], "seed": 41},
        {"root": str(root)},
    )[0]
    assert make_task.command[:2] == [detected_login_shell(), "-ic"]
    assert make_task.command[-1].endswith("&& make all CASE=case-a SEED=41")
    assert make_task.custom["自定义文本"] == [
        "case=case-a",
        "seed=41",
    ]
    composed = {
        "plugin": "verification",
        "case_directory": str(root / "cases"),
        "working_directory": ".",
        "command": "${sim_command}",
        "variables": {"sim_command": "make all CASE=${case} SEED=${seed}"},
    }
    assert (
        registry.expand_config(composed, {"cases": ["case-a"], "seed": 42}, {"root": str(root)})[0]
        .command[-1]
        .endswith("&& make all CASE=case-a SEED=42")
    )


@pytest.mark.parametrize(
    ("command", "expected_tail"),
    [
        ("make all", "make all"),
        ("make all CASE=${case}", "make all CASE=case-a"),
        (["make", "all", "SEED=${seed}"], ["make", "all", "SEED=${seed}"]),
        (["make", "all"], ["make", "all"]),
    ],
)
def test_verification_command_uses_only_variables_explicitly_requested(
    root: Path, command, expected_tail: str | list[str]
) -> None:
    initialize_root(root)
    registry = PluginRegistry(root / "plugins")
    registry.load()
    task = registry.expand_config(
        {
            "plugin": "verification",
            "case_names": ["case-a"],
            "working_directory": ".",
            "command": command,
        },
        {"cases": ["case-a"]},
        {"root": str(root)},
    )[0]
    if isinstance(expected_tail, str):
        assert task.command[:2] == [detected_login_shell(), "-ic"]
        assert task.command[-1].endswith("&& " + expected_tail)
    else:
        assert task.command == expected_tail
    assert task.working_directory == str(root.resolve())
    assert "--case" not in task.command
    assert "--seed" not in task.command


@pytest.mark.parametrize("plugin_name", ["command", "verification"])
def test_every_command_plugin_receives_common_task_source(
    root: Path, plugin_name: str
) -> None:
    initialize_root(root)
    (root / "environment.csh").write_text(
        "setenv PROJECT_MODE regression\n", encoding="utf-8"
    )
    registry = PluginRegistry(root / "plugins")
    registry.load()
    configuration = {
        "plugin": plugin_name,
        "name": "sourced-command",
        "case_names": ["case-a"],
        "working_directory": ".",
        "shell": "/bin/tcsh",
        "source": "environment.csh",
        "command": "printf '%s' $PROJECT_MODE",
    }
    inputs = {"cases": ["case-a"]} if plugin_name == "verification" else {}
    task = registry.expand_config(configuration, inputs, {"root": str(root)})[0]
    command = task.command[-1]
    expected_source = shlex.quote(str((root / "environment.csh").resolve()))
    assert f"source {expected_source}\nif ( $status != 0 ) exit $status\n" in command
    assert f"cd {shlex.quote(str(root.resolve()))}\n" in command
    assert "# localflow:user-command\nprintf '%s' $PROJECT_MODE" in command
    assert command.endswith("printf '%s' $PROJECT_MODE")


def test_verification_queue_identity_requires_same_case_and_complete_label_set(
    root: Path,
) -> None:
    initialize_root(root)
    registry = PluginRegistry(root / "plugins")
    registry.load()

    def expand(case: str, labels: list[str]):
        return registry.expand_config(
            {
                "plugin": "verification",
                "case_names": ["case-a", "case-b"],
                "working_directory": ".",
                "command": "true",
                "labels": labels,
            },
            {"cases": [case]},
            {"root": str(root)},
        )[0]

    same_left = expand("case-a", ["nightly", "gpu"])
    same_reordered = expand("case-a", ["gpu", "nightly"])
    different_case = expand("case-b", ["nightly", "gpu"])
    partial_labels = expand("case-a", ["nightly"])
    assert same_left.mutex_keys == same_reordered.mutex_keys
    assert same_left.mutex_keys != different_case.mutex_keys
    assert same_left.mutex_keys != partial_labels.mutex_keys


def test_verification_resolves_yaml_root_variables_after_include(root: Path) -> None:
    initialize_root(root)
    included = root / "config" / "verification" / "included-values.yaml"
    included.write_text(
        "project:\n  command: make smoke\n  label: included\n",
        encoding="utf-8",
    )
    source = root / "config" / "verification" / "included-command.yaml"
    source.write_text(
        "!include included-values.yaml\n"
        "plugin: verification\n"
        "case_names: [case-a]\n"
        "working_directory: .\n"
        "command: ${project.command}\n"
        'labels: ["${project.label}"]\n',
        encoding="utf-8",
    )
    from localflow.config_repository import ConfigRepository

    document = ConfigRepository(root).parse("verification/included-command.yaml")
    registry = PluginRegistry(root / "plugins")
    registry.load()
    task = registry.expand_config(
        document,
        {"cases": ["case-a"]},
        {"root": str(root)},
    )[0]

    assert task.command[:2] == [detected_login_shell(), "-ic"]
    assert task.command[-1].endswith("&& make smoke")
    assert task.labels == ["included"]


def test_verification_only_exposes_case_and_seed_as_runtime_variables(root: Path) -> None:
    initialize_root(root)
    registry = PluginRegistry(root / "plugins")
    registry.load()
    base = {
        "plugin": "verification",
        "case_names": ["case-a"],
        "working_directory": ".",
    }

    for forbidden in ("root", "scripts_dir", "cases_dir", "run", "runs", "cases"):
        with pytest.raises(ValueError, match=f"unknown variable: {forbidden}"):
            registry.expand_config(
                {**base, "command": f"echo ${{{forbidden}}}"},
                {"cases": ["case-a"]},
                {"root": str(root)},
            )

    task = registry.expand_config(
        {**base, "command": "echo ${case} ${seed}"},
        {"cases": ["case-a"], "seed": 41},
        {"root": str(root)},
    )[0]
    assert task.command[-1].endswith("&& echo case-a 41")


def test_command_variables_come_only_from_the_merged_configuration(root: Path) -> None:
    initialize_root(root)
    registry = PluginRegistry(root / "plugins")
    registry.load()
    base = {
        "plugin": "command",
        "name": "site command",
        "working_directory": ".",
    }

    for implicit in ("root", "scripts_dir", "cases_dir"):
        with pytest.raises(ValueError, match=f"unknown variable: {implicit}"):
            registry.expand_config(
                {**base, "command": f"echo ${{{implicit}}}"},
                {},
                {"root": str(root)},
            )

    task = registry.expand_config(
        {
            **base,
            "command": "echo ${site_message} ${site_paths.logs}",
            "site_message": "configured",
            "site_paths": {"logs": "artifacts"},
        },
        {},
        {"root": str(root)},
    )[0]
    assert task.command[-1].endswith("&& echo configured artifacts")


def test_plugin_metadata_rejects_nonportable_deferred_variables(root: Path) -> None:
    directory = root / "plugins"
    directory.mkdir(parents=True)
    (directory / "deferred.py").write_text(
        "from localflow.plugins import plugin\n"
        "@plugin('deferred')\n"
        "class Deferred:\n"
        " run_fields=[]\n"
        " deferred_variables={'run'}\n"
        " def expand(self, values, context): return []\n",
        encoding="utf-8",
    )
    registry = PluginRegistry(directory)
    registry.load()
    assert not registry.plugins
    assert "unsupported deferred variables: ['run']" in next(iter(registry.diagnostics.values()))


def test_verification_rejects_an_implicit_controller_working_directory(root: Path) -> None:
    initialize_root(root)
    registry = PluginRegistry(root / "plugins")
    registry.load()
    with pytest.raises(ValueError, match="working_directory"):
        registry.expand_config(
            {
                "plugin": "verification",
                "case_directory": str(root / "cases"),
                "command": "make all",
            },
            {"cases": ["case-a"]},
            {"root": str(root)},
        )


def test_verification_result_uses_final_uvm_summary_and_existing_logs(root: Path) -> None:
    initialize_root(root)
    registry = PluginRegistry(root / "plugins")
    registry.load()
    plugin = registry.plugins["verification"].instance
    compile_log = root / "compile.log"
    compile_log.write_text("Error-[SYN] compile failed\n", encoding="utf-8")
    run_log = root / "run.log"
    task = SimpleNamespace(
        custom={
            "_compile_logs": [str(compile_log)],
            "_run_logs": [str(run_log)],
            "自定义文本": ["build=nightly", "owner=verification"],
        },
        exit_code=0,
    )
    missing_run = plugin.evaluate_result(task, {"root": str(root)})
    assert missing_run == {
        "status": "compile_error",
        "custom": {
            "自定义文本": ["build=nightly", "owner=verification"],
            "编译日志": [str(compile_log)],
        },
    }
    run_log.write_text(
        "UVM_ERROR old message\n"
        "--- UVM Report Summary ---\n"
        "UVM_INFO : 12\nUVM_WARNING : 0\nUVM_ERROR : 2\nUVM_FATAL : 0\n",
        encoding="utf-8",
    )
    result = plugin.evaluate_result(task, {"root": str(root)})
    assert result["status"] == "error"
    assert "label" not in result
    assert result["custom"] == {
        "自定义文本": ["build=nightly", "owner=verification"],
        "运行日志": [str(run_log)],
    }


@pytest.mark.parametrize("exit_code", [0, 7])
def test_verification_without_run_log_evidence_is_neutral(
    root: Path, exit_code: int
) -> None:
    initialize_root(root)
    registry = PluginRegistry(root / "plugins")
    registry.load()
    verification = registry.plugins["verification"].instance

    no_logs = SimpleNamespace(custom={"自定义文本": ["nightly"]}, exit_code=exit_code)
    assert verification.evaluate_result(no_logs, {"root": str(root)}) == {
        "status": "finished",
        "custom": {"自定义文本": ["nightly"]},
    }

    missing_run = SimpleNamespace(
        custom={"_run_logs": [str(root / "missing.run.log")]},
        exit_code=exit_code,
    )
    assert verification.evaluate_result(missing_run, {"root": str(root)}) == {
        "status": "finished",
        "custom": {},
    }


def test_verification_without_run_logs_preserves_existing_compile_details(
    root: Path,
) -> None:
    initialize_root(root)
    registry = PluginRegistry(root / "plugins")
    registry.load()
    verification = registry.plugins["verification"].instance
    compile_log = root / "compile.log"
    compile_log.write_text("compiler output\n", encoding="utf-8")
    task = SimpleNamespace(
        custom={"_compile_logs": [str(compile_log)], "_run_logs": []},
        exit_code=0,
    )

    assert verification.evaluate_result(task, {"root": str(root)}) == {
        "status": "finished",
        "custom": {"编译日志": [str(compile_log)]},
    }


def test_run_field_contract_is_simple_and_rejects_invalid_metadata(root: Path) -> None:
    assert run_field("seed", "seed", label="随机种子") == {
        "name": "seed",
        "type": "seed",
        "label": "随机种子",
    }
    directory = root / "plugins"
    directory.mkdir(parents=True)
    (directory / "bad_fields.py").write_text(
        "from localflow.plugins import plugin\n"
        "@plugin('bad-fields')\n"
        "class BadFields:\n"
        " run_fields=[{'name':'same','type':'string'}, {'name':'same','type':'mystery'}]\n"
        " def expand(self, values, context): return []\n",
        encoding="utf-8",
    )
    registry = PluginRegistry(directory)
    registry.load()
    assert not registry.plugins
    assert "Input should be" in next(iter(registry.diagnostics.values()))
    with pytest.raises(ValueError, match="count_field"):
        run_field("cases", "case-picker")


def test_plugin_schema_rejects_common_field_collision(root: Path) -> None:
    directory = root / "plugins"
    directory.mkdir(parents=True)
    (directory / "collision.py").write_text(
        "from pydantic import BaseModel\n"
        "from localflow.plugins import plugin\n"
        "class Config(BaseModel): name: str\n"
        "@plugin('collision')\n"
        "class Collision:\n"
        " config_model=Config\n"
        " run_fields=[]\n"
        " example={'plugin':'collision'}\n"
        " def expand(self, values, context): return []\n",
        encoding="utf-8",
    )
    registry = PluginRegistry(directory)
    registry.load()
    assert not registry.plugins
    assert "overlap common fields" in next(iter(registry.diagnostics.values()))


def test_command_task_resolves_config_variables(root: Path) -> None:
    initialize_root(root)
    registry = PluginRegistry(root / "plugins")
    registry.load()
    task = registry.expand_config(
        {
            "plugin": "command",
            "working_directory": ".",
            "command": ["echo", "${message}"],
            "labels": ["${label}"],
            "mutex_keys": ["license:${label}"],
            "name": "${job_name}",
            "job_name": "configured-job",
            "message": "hello",
            "label": "nightly",
            "site_owned": {"toolchain": "custom"},
        },
        {},
        {"root": str(root)},
    )[0]
    assert task.name == "configured-job"
    assert task.working_directory == str(root.resolve())
    assert task.command == ["echo", "hello"]
    assert task.labels == ["nightly"]
    assert task.mutex_keys == ["license:nightly"]
    assert task.plugin_snapshot["name"] == "command"


def test_every_plugin_configuration_schema_accepts_site_owned_keys(root: Path) -> None:
    initialize_root(root)
    registry = PluginRegistry(root / "plugins")
    registry.load()
    for description in registry.describe():
        api = description["api"]
        assert api["configuration_schema"]["additionalProperties"] is True
        assert api["plugin_fields_schema"]["additionalProperties"] is True
        assert api["input_schema"]["additionalProperties"] is False


def test_plugin_input_model_must_match_run_field_contract(root: Path) -> None:
    directory = root / "plugins"
    directory.mkdir(parents=True)
    (directory / "mismatch.py").write_text(
        "from pydantic import BaseModel, ConfigDict\n"
        "from localflow.plugins import plugin, run_field\n"
        "class Inputs(BaseModel):\n"
        " model_config=ConfigDict(extra='forbid')\n"
        " hidden: str = ''\n"
        "@plugin('mismatch')\n"
        "class Mismatch:\n"
        " input_model=Inputs\n"
        " run_fields=[run_field('visible','string')]\n"
        " example={'plugin':'mismatch'}\n"
        " def expand(self, values, context): return []\n",
        encoding="utf-8",
    )
    registry = PluginRegistry(directory)
    registry.load()
    assert not registry.plugins
    assert "input_model fields differ from run fields" in next(iter(registry.diagnostics.values()))


def test_plugin_descriptions_have_user_facing_names(root: Path) -> None:
    initialize_root(root)
    registry = PluginRegistry(root / "plugins")
    registry.load()
    descriptions = {item["name"]: item for item in registry.describe()}
    assert descriptions["command"]["title"] == "命令"
    assert descriptions["verification"]["title"] == "验证仿真"
    assert set(descriptions) == {"command", "verification"}


def test_every_builtin_plugin_publishes_a_runnable_api_example(root: Path) -> None:
    initialize_root(root)
    registry = PluginRegistry(root / "plugins")
    registry.load()
    for description in registry.describe():
        api = description["api"]
        assert api["endpoint"] == "/api/v1/runs"
        assert isinstance(api["configuration_schema"], dict)
        assert api["input_fields"] == description["fields"]
        example = api["example"]
        tasks = registry.expand_config(
            example["configuration"], example["inputs"], {"root": str(root)}
        )
        assert tasks, description["name"]
        assert all(task.plugin_snapshot["name"] == description["name"] for task in tasks)
