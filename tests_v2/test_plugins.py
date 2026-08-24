from pathlib import Path

import pytest

from localflow.plugins import PluginRegistry
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


def test_declarative_template_resolves_disk_config_and_run_override(root: Path) -> None:
    initialize_root(root)
    template = root / "config" / "templates" / "job.json"
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
        {"template_file": "job.json", "run_variables": {"message": "hello"}},
        {"root": str(root)},
    )[0]
    assert task.name == "configured-job"
    assert task.command == ["echo", "hello"]
    assert task.labels == ["nightly"]
    assert task.mutex_keys == ["license:nightly"]
    assert task.custom["report"] == "hello.txt"
    assert task.plugin_snapshot["name"] == "declarative"
