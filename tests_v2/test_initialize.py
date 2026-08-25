import os
import signal
import subprocess
import sys
import time
from pathlib import Path

from localflow.plugins import PluginRegistry
from localflow.settings import initialize_root


def test_initialize_installs_loadable_verification_plugin(root: Path) -> None:
    initialize_root(root)
    example = root / "plugins" / "verification.py"
    assert example.is_file()
    registry = PluginRegistry(root / "plugins")
    registry.load()
    assert {item["name"] for item in registry.describe()} == {
        "command",
        "interactive",
        "marker",
        "verification",
    }
    assert (root / "scripts" / "random_number.py").is_file()
    assert (root / "scripts" / "interactive_shutdown.py").is_file()
    assert (root / "config" / "shared" / "task-defaults.yaml").is_file()
    assert {path.name for path in (root / "config" / "tasks").iterdir()} == {
        "interactive-shutdown.yaml",
        "marker-warning.yaml",
        "random-number.yaml",
        "verification-demo.yaml",
    }
    random_task = registry.expand(
        "command",
        {"task": "random-number.yaml", "inputs": {}},
        {"root": str(root)},
    )[0]
    assert random_task.name == "随机数"
    assert Path(random_task.working_directory) == root / "scripts"
    assert random_task.command == ["python3", "-u", "random_number.py"]
    assert random_task.custom["source"] == "starter"
    assert (root / "cases" / "case-a" / "README.txt").is_file()
    assert (root / "cases" / "smoke.case").is_file()
    assert (root / "scripts" / "marker_result.py").is_file()
    assert (root / "scripts" / "interactive_shutdown.py").is_file()
    assert (root / "plugins" / "README.md").is_file()
    plugin_readme = (root / "plugins" / "README.md").read_text(encoding="utf-8")
    assert "网页“插件”页" not in plugin_readme
    assert "修改 YAML" not in plugin_readme
    assert "configuration-plugin-contract.md" not in plugin_readme
    assert "GET /api/v1/plugins" in plugin_readme
    assert "HMAC" in plugin_readme
    original = example.read_text(encoding="utf-8")
    example.write_text(original + "\n# user edit\n", encoding="utf-8")
    initialize_root(root)
    assert example.read_text(encoding="utf-8").endswith("# user edit\n")


def test_starter_examples_run_once_and_interrupt_cleanly(root: Path) -> None:
    initialize_root(root)
    scripts = root / "scripts"
    once = subprocess.run(
        [sys.executable, "-u", scripts / "random_number.py"],
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=5,
    )
    assert "本次随机数：" in once.stdout

    windows = os.name == "nt"
    process = subprocess.Popen(
        [sys.executable, "-u", scripts / "interactive_shutdown.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if windows else 0,
        start_new_session=not windows,
    )
    try:
        time.sleep(0.08)
        if windows:
            process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGINT)
        output, _ = process.communicate("quit\n", timeout=5)
    finally:
        if process.poll() is None:
            process.kill()
            process.wait(timeout=5)
    assert process.returncode == 0
    assert "交互程序已启动" in output
    assert "保存完成，正常退出" in output

    eof_process = subprocess.Popen(
        [sys.executable, "-u", scripts / "interactive_shutdown.py"],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
    )
    assert eof_process.stdin is not None
    assert eof_process.stdout is not None
    eof_process.stdin.close()
    eof_output = eof_process.stdout.read()
    assert eof_process.wait(timeout=5) == 0
    assert "Ctrl+D" in eof_output
