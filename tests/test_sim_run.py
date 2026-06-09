from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

from automation.script.registry import clear_scripts

REPO = Path(__file__).resolve().parents[1]


class SimRunPluginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = str(REPO)
        if root not in sys.path:
            sys.path.insert(0, root)

    def setUp(self) -> None:
        clear_scripts()

    def test_format_command_substitutes_variables(self) -> None:
        from plugins.sim_run import format_command

        rendered = format_command(
            "make {project} {case} SEED={seed}",
            {
                "project": "chip_a",
                "module": "tb",
                "case": "smoke",
                "seed": "99",
            },
        )
        self.assertEqual(rendered, "make chip_a smoke SEED=99")

    def test_format_command_rejects_unknown_placeholder(self) -> None:
        from plugins.sim_run import format_command

        with self.assertRaises(ValueError):
            format_command("run {missing}", {"project": "a"})

    def test_evaluate_log_pass_fail_error(self) -> None:
        from plugins.sim_run import evaluate_log_result

        with tempfile.TemporaryDirectory() as tmp:
            log_file = Path(tmp) / "sim.log"
            log_file.write_text("ALL TESTS PASSED\n", encoding="utf-8")
            status, _ = evaluate_log_result(log_file, pass_regex=r"PASSED", fail_regex=r"FAIL")
            self.assertEqual(status, "PASS")

            log_file.write_text("SOMETHING BAD\n", encoding="utf-8")
            status, msg = evaluate_log_result(log_file, pass_regex=r"PASSED", fail_regex=r"BAD")
            self.assertEqual(status, "FAIL")
            self.assertIn("fail", msg)

            status, _ = evaluate_log_result(log_file, pass_regex=r"PASSED", fail_regex="")
            self.assertEqual(status, "FAIL")

            missing = Path(tmp) / "none.log"
            status, msg = evaluate_log_result(missing, pass_regex=r".")
            self.assertEqual(status, "ERROR")
            self.assertIn("不存在", msg)

    def test_execute_pass_writes_terminal_log_path(self) -> None:
        from plugins.sim_run import SimRunScript

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            log_name = "out.log"
            (work_dir / "write_log.py").write_text(
                "from pathlib import Path\n"
                f"Path({log_name!r}).write_text('SIMULATION PASSED\\n', encoding='utf-8')\n",
                encoding="utf-8",
            )
            shell_cmd = "python write_log.py"

            script = SimRunScript(
                name="sim-test",
                register=False,
                instance_id="sim-pass-1",
                project="p",
                module="m",
                case="c",
                seed="1",
                work_dir=str(work_dir),
                command=shell_cmd,
                pass_regex=r"PASSED",
                fail_regex=r"FAIL",
                log_path=log_name,
                result_status="—",
                formatted_command="",
                exit_code="—",
                duration="—",
                phase="待运行",
                log_tail="",
                error_message="",
                error_traceback="",
            )
            script.execute()

        desc = script.describe()
        self.assertEqual(script.variables.get("result_status"), "PASS")
        self.assertTrue(desc["terminal_log_path"])
        terminal_path = Path(desc["terminal_log_path"])
        self.assertTrue(terminal_path.is_file())
        self.assertEqual(
            desc["variables"].get("terminal_log_path"),
            str(terminal_path),
        )

    def test_execute_fail_when_log_not_pass(self) -> None:
        from plugins.sim_run import SimRunScript

        with tempfile.TemporaryDirectory() as tmp:
            work_dir = Path(tmp)
            (work_dir / "out.log").write_text("FAILED run\n", encoding="utf-8")
            (work_dir / "noop.py").write_text("print('done')\n", encoding="utf-8")
            shell_cmd = "python noop.py"

            script = SimRunScript(
                name="sim-fail",
                register=False,
                project="p",
                module="m",
                case="c",
                seed="1",
                work_dir=str(work_dir),
                command=shell_cmd,
                pass_regex=r"PASSED",
                fail_regex=r"FAILED",
                log_path="out.log",
                result_status="—",
                formatted_command="",
                exit_code="—",
                duration="—",
                phase="待运行",
                log_tail="",
                error_message="",
                error_traceback="",
            )
            with self.assertRaises(RuntimeError):
                script.execute()
            self.assertEqual(script.variables.get("result_status"), "FAIL")


if __name__ == "__main__":
    unittest.main()
