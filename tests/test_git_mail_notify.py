from __future__ import annotations

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from automation import clear_instances
from automation.script.registry import clear_scripts

REPO = Path(__file__).resolve().parents[1]


def _clear_loaded_packages() -> None:
    for key in list(sys.modules):
        if key == "plugins" or key.startswith(("plugins.", "examples.")):
            del sys.modules[key]


class GitMailNotifyScriptTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = str(REPO)
        if root not in sys.path:
            sys.path.insert(0, root)

    def setUp(self) -> None:
        clear_instances()
        clear_scripts()
        _clear_loaded_packages()

    def _init_repo(self, repo: Path) -> None:
        subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.email", "t@example.com"], cwd=repo, check=True)
        subprocess.run(["git", "config", "user.name", "tester"], cwd=repo, check=True)
        (repo / "a.txt").write_text("1\n", encoding="utf-8")
        subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True)
        (repo / "a.txt").write_text("1\n2\n", encoding="utf-8")
        subprocess.run(["git", "add", "a.txt"], cwd=repo, check=True)
        subprocess.run(["git", "commit", "-m", "add line"], cwd=repo, check=True)

    @patch("plugins.git_mail_notify.script.send_mail")
    def test_run_sends_rendered_diff(self, mock_send: MagicMock) -> None:
        from plugins.git_mail_notify import GitMailNotifyScript

        mock_send.return_value = MagicMock(
            recipients=("ops@example.com",),
            message_id="<test@local>",
        )

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            self._init_repo(repo)
            script = GitMailNotifyScript(
                name="test-mail",
                register=False,
                repo_path=str(repo),
                subject_prefix="[CI]",
                smtp_host="smtp.example.com",
                smtp_port=587,
                mail_from_addr="bot@example.com",
                mail_to_addrs="ops@example.com",
                smtp_use_starttls=True,
                smtp_use_ssl=False,
            )
            script.run()

        mock_send.assert_called_once()
        kwargs = mock_send.call_args.kwargs
        self.assertIn("add line", kwargs["subject"])
        self.assertIn("a.txt", kwargs["body"])
        self.assertEqual(script.variables.get("mail_recipients"), "ops@example.com")

    def test_attach_registers_automation(self) -> None:
        from automation import all_instances
        from plugins.git_mail_notify import GitMailNotifyScript, attach_git_update_watch

        script = GitMailNotifyScript(name="wire-test", register=False, repo_path=".")
        automation = attach_git_update_watch(
            script,
            name="git_mail_test",
            repo_path=REPO,
            interval=30.0,
        )
        self.assertEqual(automation.name, "git_mail_test")
        names = [item.name for item in all_instances()]
        self.assertIn("git_mail_test", names)


if __name__ == "__main__":
    unittest.main()
