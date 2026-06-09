from __future__ import annotations

import sys
import tempfile
import unittest
from io import StringIO
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]

SAMPLE_DIFF = """\
diff --git a/a.txt b/a.txt
index 1111111..2222222 100644
--- a/a.txt
+++ b/a.txt
@@ -1,2 +1,3 @@
 keep
+added
 tail
"""


class DiffRenderPluginTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        root = str(REPO)
        if root not in sys.path:
            sys.path.insert(0, root)

    def test_render_diff_contains_content_and_color(self) -> None:
        from plugins.diff_render import render_diff

        text = render_diff(SAMPLE_DIFF)
        self.assertIn("added", text)
        self.assertIn("--- a/a.txt", text)
        self.assertIn("\x1b[", text)

    def test_render_diff_empty(self) -> None:
        from plugins.diff_render import render_diff

        text = render_diff("   \n")
        self.assertIn("无 diff", text)

    def test_print_diff_writes_to_stream(self) -> None:
        from plugins.diff_render import print_diff

        buf = StringIO()
        print_diff(SAMPLE_DIFF, file=buf)
        self.assertIn("added", buf.getvalue())

    def test_render_git_update(self) -> None:
        from plugins.diff_render import render_git_update
        from plugins.git_update import get_last_update

        with tempfile.TemporaryDirectory() as tmp:
            repo = Path(tmp)
            import subprocess

            subprocess.run(["git", "init", "-b", "main"], cwd=repo, check=True)
            subprocess.run(
                ["git", "config", "user.email", "t@example.com"],
                cwd=repo,
                check=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "tester"],
                cwd=repo,
                check=True,
            )
            (repo / "f.txt").write_text("a\n", encoding="utf-8")
            subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=repo, check=True)
            (repo / "f.txt").write_text("a\nb\n", encoding="utf-8")
            subprocess.run(["git", "add", "f.txt"], cwd=repo, check=True)
            subprocess.run(["git", "commit", "-m", "add b"], cwd=repo, check=True)

            update = get_last_update(repo)
            text = render_git_update(update)
            self.assertIn("add b", text)
            self.assertIn("f.txt", text)
            self.assertIn("\x1b[", text)
