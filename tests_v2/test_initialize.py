from pathlib import Path

from localflow.plugins import PluginRegistry
from localflow.settings import initialize_root


def test_initialize_installs_loadable_verification_plugin(root: Path) -> None:
    initialize_root(root)
    example = root / "plugins" / "verification.py"
    assert example.is_file()
    registry = PluginRegistry(root / "plugins")
    registry.load()
    assert {item["name"] for item in registry.describe()} == {"declarative", "verification"}
    hello = registry.expand(
        "declarative",
        {"template_file": "hello.yaml", "run_variables": {"message": "hello"}},
        {"root": str(root)},
    )[0]
    assert hello.name == "hello" and hello.working_directory == str(root)
    original = example.read_text(encoding="utf-8")
    example.write_text(original + "\n# user edit\n", encoding="utf-8")
    initialize_root(root)
    assert example.read_text(encoding="utf-8").endswith("# user edit\n")
