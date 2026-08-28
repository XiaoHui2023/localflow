from pathlib import Path

from localflow.plugins import PluginRegistry
from localflow.settings import initialize_root, load_settings


def test_initialize_installs_only_production_plugins_and_examples(root: Path) -> None:
    initialize_root(root)
    registry = PluginRegistry(root / "plugins")
    registry.load()
    assert {item["name"] for item in registry.describe()} == {"command", "verification"}
    assert (root / "localflow.yaml").is_file()
    assert load_settings(root).server.port == 0
    configs = {
        path.relative_to(root / "config").as_posix()
        for path in (root / "config").rglob("*.yaml")
    }
    assert configs == {"command/hello-world.yaml", "verification/demo.yaml"}
    assert (root / "scripts" / "simulate.py").is_file()
    assert not (root / "scripts" / "random_number.py").exists()
    assert not (root / "plugins" / "marker.py").exists()
    assert not (root / "plugins" / "interactive.py").exists()

    command = registry.expand_config(
        {
            "plugin": "command",
            "name": "hello-world",
            "working_directory": str(root),
            "command": ["sh", "-c", "printf 'hello world\\n' > hello-world.txt"],
        },
        {},
        {"root": str(root)},
    )[0]
    assert command.name == "hello-world"
    assert command.command[-1].endswith("hello-world.txt")


def test_initialize_preserves_user_files_and_migrates_legacy_server_config(root: Path) -> None:
    legacy = root / "config" / "server.yaml"
    legacy.parent.mkdir(parents=True)
    legacy.write_text("server:\n  port: 8123\n", encoding="utf-8")
    initialize_root(root)
    assert not legacy.exists()
    assert load_settings(root).server.port == 8123

    command = root / "plugins" / "command.py"
    original = command.read_text(encoding="utf-8")
    command.write_text(original + "\n# user edit\n", encoding="utf-8")
    initialize_root(root)
    assert command.read_text(encoding="utf-8").endswith("# user edit\n")
