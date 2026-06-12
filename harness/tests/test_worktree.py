from __future__ import annotations

import subprocess
import sys
import tempfile
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "harness" / "orchestrate_run.py"


class WorktreeLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.workspace = Path(self._tmpdir.name)
        self.repo = self.workspace / "repo"
        self.repo.mkdir()
        self._run_git(["init"], cwd=self.repo)
        self._run_git(["config", "user.email", "test@example.com"], cwd=self.repo)
        self._run_git(["config", "user.name", "Test User"], cwd=self.repo)
        (self.repo / "tracked.txt").write_text("base\n", encoding="utf-8")
        self._run_git(["add", "tracked.txt"], cwd=self.repo)
        self._run_git(["commit", "-m", "initial"], cwd=self.repo)
        self.addCleanup(self._tmpdir.cleanup)

    def _run_git(self, args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(["git", *args], capture_output=True, text=True, cwd=cwd)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def _run_cli(self, *args: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [sys.executable, str(SCRIPT), *args],
            capture_output=True,
            text=True,
            cwd=self.workspace,
        )

    def _create_worktree(self, run_id: str) -> Path:
        result = self._run_cli("worktree-create", "--repo", str(self.repo), "--run-id", run_id)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(result.stderr, "")
        lines = result.stdout.strip().splitlines()
        self.assertEqual(len(lines), 1, result.stdout)
        self.assertTrue(lines[0].startswith("WORKTREE "), result.stdout)
        worktree_path = Path(lines[0].removeprefix("WORKTREE ")).resolve()
        self.assertTrue(worktree_path.is_absolute())
        self.addCleanup(self._force_remove_worktree, worktree_path)
        return worktree_path

    def _force_remove_worktree(self, worktree_path: Path) -> None:
        if not worktree_path.exists():
            return

        subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "worktree-remove",
                "--repo",
                str(self.repo),
                "--worktree",
                str(worktree_path),
                "--force",
            ],
            capture_output=True,
            text=True,
            cwd=self.workspace,
        )

    def test_create_capture_and_remove_happy_path(self) -> None:
        worktree_path = self._create_worktree("happy-path")
        (worktree_path / "new-file.txt").write_text("hello from worktree\n", encoding="utf-8")

        capture_result = self._run_cli(
            "worktree-capture",
            "--repo",
            str(self.repo),
            "--worktree",
            str(worktree_path),
            "--run-id",
            "happy-path",
        )
        self.assertEqual(capture_result.returncode, 0, capture_result.stdout + capture_result.stderr)
        self.assertEqual(capture_result.stderr, "")
        self.assertIn("CAPTURED 1 files ->", capture_result.stdout)

        run_dir = self.repo / ".orchestrate" / "runs" / "happy-path"
        diff_path = run_dir / "diff.patch"
        touched_path = run_dir / "touched-files.txt"
        self.assertTrue(diff_path.exists(), diff_path)
        self.assertTrue(touched_path.exists(), touched_path)

        diff_text = diff_path.read_text(encoding="utf-8")
        touched_text = touched_path.read_text(encoding="utf-8")
        self.assertIn("new-file.txt", touched_text)
        self.assertIn("new-file.txt", diff_text)
        self.assertIn("new file mode", diff_text)

        remove_result = self._run_cli(
            "worktree-remove",
            "--repo",
            str(self.repo),
            "--worktree",
            str(worktree_path),
            "--force",
        )
        self.assertEqual(remove_result.returncode, 0, remove_result.stdout + remove_result.stderr)
        self.assertEqual(remove_result.stdout.strip(), f"REMOVED {worktree_path}")
        self.assertFalse(worktree_path.exists())

    def test_remove_without_capture_is_refused(self) -> None:
        worktree_path = self._create_worktree("remove-refused")
        (worktree_path / "uncaptured.txt").write_text("dirty\n", encoding="utf-8")

        result = self._run_cli(
            "worktree-remove",
            "--repo",
            str(self.repo),
            "--worktree",
            str(worktree_path),
        )
        self.assertEqual(result.returncode, 4, result.stdout + result.stderr)
        self.assertEqual(
            result.stdout.strip(),
            "ERROR worktree has uncaptured changes; run worktree-capture first or pass --force",
        )
        self.assertTrue(worktree_path.exists())

    def test_prune_skips_dirty_and_removes_clean(self) -> None:
        clean_worktree = self._create_worktree("prune-clean")
        dirty_worktree = self._create_worktree("prune-dirty")
        (dirty_worktree / "dirty.txt").write_text("needs capture\n", encoding="utf-8")

        result = self._run_cli("worktree-prune", "--repo", str(self.repo))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn(f"SKIPPED {dirty_worktree} (uncaptured changes)", result.stdout)
        self.assertIn("PRUNED 1 SKIPPED 1", result.stdout)
        self.assertFalse(clean_worktree.exists())
        self.assertTrue(dirty_worktree.exists())

    def test_capture_reports_isolation_breach_for_live_repo_changes(self) -> None:
        worktree_path = self._create_worktree("isolation-breach")
        (worktree_path / "shared.txt").write_text("worktree copy\n", encoding="utf-8")
        (self.repo / "shared.txt").write_text("live repo copy\n", encoding="utf-8")

        result = self._run_cli(
            "worktree-capture",
            "--repo",
            str(self.repo),
            "--worktree",
            str(worktree_path),
            "--run-id",
            "isolation-breach",
        )
        self.assertEqual(result.returncode, 3, result.stdout + result.stderr)
        self.assertIn("ISOLATION-BREACH shared.txt", result.stdout)

        run_dir = self.repo / ".orchestrate" / "runs" / "isolation-breach"
        self.assertTrue((run_dir / "diff.patch").exists())
        self.assertTrue((run_dir / "touched-files.txt").exists())


if __name__ == "__main__":
    unittest.main()
