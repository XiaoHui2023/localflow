from __future__ import annotations

import asyncio
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]


def _run_git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)


class GitUpdatePluginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = str(REPO)
        if root not in sys.path:
            sys.path.insert(0, root)

    def test_get_last_update_on_fresh_repo(self) -> None:
        from plugins.git_update import get_last_update

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _run_git(repo, "init", "-b", "main")
            _run_git(repo, "config", "user.email", "test@example.com")
            _run_git(repo, "config", "user.name", "tester")

            readme = repo / "README.md"
            readme.write_text("v1\n", encoding="utf-8")
            _run_git(repo, "add", "README.md")
            _run_git(repo, "commit", "-m", "init")

            readme.write_text("v1\nv2\n", encoding="utf-8")
            _run_git(repo, "add", "README.md")
            _run_git(repo, "commit", "-m", "add line")

            update = get_last_update(repo)

            self.assertEqual(update.repo_path, repo.resolve())
            self.assertEqual(update.branch, "main")
            self.assertEqual(update.commit.subject, "add line")
            self.assertEqual(len(update.commit.parents), 1)
            self.assertEqual(update.stats.files_changed, 1)
            self.assertEqual(update.stats.insertions, 1)
            self.assertEqual(update.stats.deletions, 0)
            self.assertEqual(len(update.files), 1)
            self.assertEqual(update.files[0].path, "README.md")
            self.assertEqual(update.files[0].status, "M")
            self.assertIn("README.md", update.diff)

    def test_non_repo_raises(self) -> None:
        from plugins.git_update import get_last_update

        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(ValueError):
                get_last_update(Path(tmp))

    def test_get_head_hash(self) -> None:
        from plugins.git_update import get_head_hash

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _run_git(repo, "init", "-b", "main")
            _run_git(repo, "config", "user.email", "test@example.com")
            _run_git(repo, "config", "user.name", "tester")
            (repo / "a.txt").write_text("x\n", encoding="utf-8")
            _run_git(repo, "add", "a.txt")
            _run_git(repo, "commit", "-m", "one")

            head = get_head_hash(repo)
            self.assertEqual(len(head), 40)


class GitUpdateAutomationTest(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = str(REPO)
        if root not in sys.path:
            sys.path.insert(0, root)

    async def test_on_tick_fires_after_new_commit(self) -> None:
        from automation.context import Context

        from plugins.git_update import GitRepoUpdatePayload, GitUpdateAutomation

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            _run_git(repo, "init", "-b", "main")
            _run_git(repo, "config", "user.email", "test@example.com")
            _run_git(repo, "config", "user.name", "tester")
            (repo / "a.txt").write_text("v1\n", encoding="utf-8")
            _run_git(repo, "add", "a.txt")
            _run_git(repo, "commit", "-m", "first")
            first_head = subprocess.check_output(
                ["git", "rev-parse", "HEAD"],
                cwd=repo,
                text=True,
            ).strip()

            automation = GitUpdateAutomation(name="watch", repo_path=repo, interval=1.0)
            received: list[GitRepoUpdatePayload] = []

            @automation.register
            async def on_update(payload: GitRepoUpdatePayload) -> None:
                received.append(payload)

            ctx = Context()
            ctx.stop_event = asyncio.Event()
            automation.ctx = ctx

            await automation.on_tick()
            self.assertEqual(received, [])

            (repo / "a.txt").write_text("v1\nv2\n", encoding="utf-8")
            _run_git(repo, "add", "a.txt")
            _run_git(repo, "commit", "-m", "second")

            await automation.on_tick()
            self.assertEqual(len(received), 1)
            self.assertEqual(received[0].previous_hash, first_head)
            self.assertEqual(received[0].update.commit.subject, "second")
