from pathlib import Path
from types import SimpleNamespace

import pytest

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
    nested.write_text("nested", encoding="utf-8")
    registry = PluginRegistry(root / "plugins")
    registry.load()
    verification = next(item for item in registry.describe() if item["name"] == "verification")
    assert verification["api"]["endpoint"] == "/api/v1/runs"
    assert verification["api"]["configuration_schema"] is not None
    schema = verification["api"]["configuration_schema"]
    assert {"plugin", "command", "case_directory", "case_runs"}.issubset(
        schema["properties"]
    )
    assert {"plugin", "command"}.issubset(schema["required"])
    assert schema["additionalProperties"] is False
    assert {
        "variables",
        "labels",
        "mutex_keys",
        "compile_logs",
        "run_logs",
        "runs",
        "case_runs",
        "seed",
    }.issubset(schema["properties"])
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
        "variables": {"cases_dir": "${root}/cases", "scripts_dir": "${root}/scripts"},
    }
    items = await registry.discover_config(document, {}, {"root": str(root)})
    assert items == ["case-a", "case-b", "smoke"]
    with pytest.raises(ValueError, match="at least one case"):
        registry.expand_config(document, {}, {"root": str(root)})
    task = registry.expand_config(
        document,
        {"cases": ["case-a"], "seed": ""},
        {"root": str(root)},
    )[0]
    assert task.name == "case-a"
    assert task.custom["_case"] == "case-a"
    assert task.custom["_runtime_seed"] == "unix"
    assert "seed" not in task.custom
    assert task.command.count("--case") == task.command.count("--seed") == 1
    assert task.command[task.command.index("--case") + 1] == "case-a"
    assert task.command[task.command.index("--seed") + 1] == "${seed}"
    assert "tag:nightly" in task.mutex_keys


def test_verification_result_uses_final_uvm_summary_and_existing_logs(root: Path) -> None:
    initialize_root(root)
    registry = PluginRegistry(root / "plugins")
    registry.load()
    plugin = registry.plugins["verification"].instance
    compile_log = root / "compile.log"
    compile_log.write_text("Error-[SYN] compile failed\n", encoding="utf-8")
    run_log = root / "run.log"
    task = SimpleNamespace(
        custom={"_compile_logs": [str(compile_log)], "_run_logs": [str(run_log)]},
        exit_code=0,
    )
    missing_run = plugin.evaluate_result(task, {"root": str(root)})
    assert missing_run == {
        "status": "compile_error",
        "custom": {"编译日志": [str(compile_log)]},
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
    assert result["custom"] == {"运行日志": [str(run_log)]}


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


def test_declarative_task_resolves_config_and_run_inputs(root: Path) -> None:
    initialize_root(root)
    template = root / "config" / "tasks" / "job.json"
    template.write_text(
        """{
          "name": "${name}",
          "working_directory": "${runtime_root}",
          "command": ["echo", "${message}"],
          "labels": ["${label}"],
          "mutex_keys": ["license:${label}"],
          "custom": {"report": "${message}.txt"},
          "project": "demo",
          "variables": {"name": "configured-job"}
        }""",
        encoding="utf-8",
    )
    (root / "config" / "variables.yaml").write_text(
        "global: {}\nprojects:\n  demo:\n    label: nightly\n", encoding="utf-8"
    )
    registry = PluginRegistry(root / "plugins")
    registry.load()
    assert "job.json" in registry.plugins["declarative"].instance.discover({})
    task = registry.expand(
        "declarative",
        {"task": "job.json", "inputs": {"message": "hello"}},
        {"root": str(root)},
    )[0]
    assert task.name == "configured-job"
    assert task.command == ["echo", "hello"]
    assert task.labels == ["nightly"]
    assert task.mutex_keys == ["license:nightly"]
    assert task.custom["report"] == "hello.txt"
    assert task.plugin_snapshot["name"] == "declarative"


def test_plugin_descriptions_have_user_facing_names(root: Path) -> None:
    initialize_root(root)
    registry = PluginRegistry(root / "plugins")
    registry.load()
    descriptions = {item["name"]: item for item in registry.describe()}
    assert descriptions["command"]["title"] == "命令"
    assert descriptions["verification"]["title"] == "验证仿真"
    assert descriptions["marker"]["statuses"]["warning"]["label"] == "需要关注"


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
